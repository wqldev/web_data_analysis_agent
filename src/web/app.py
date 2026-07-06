"""Agent-Loop Web 产品 FastAPI 后端。"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Python 3.11 兼容：cursor-sdk 需要 os.get_blocking (3.12+)
if not hasattr(os, "get_blocking"):

    def _get_blocking(fd: int) -> bool:
        try:
            import msvcrt  # Windows
            return bool(msvcrt.get_osfhandle(fd))
        except ImportError:
            import fcntl  # Unix
            return not bool(fcntl.fcntl(fd, fcntl.F_GETFL) & os.O_NONBLOCK)
        except Exception:
            return True

    os.get_blocking = _get_blocking  # type: ignore[attr-defined]

if not hasattr(os, "set_blocking"):
    os.set_blocking = lambda fd, blocking: None  # type: ignore[attr-defined]

from fastapi import BackgroundTasks, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

ROOT = Path(__file__).resolve().parents[2]
BOARDS_DIR = Path(os.environ.get("TASK_BOARD_DIR", str(ROOT / "boards")))
os.environ["TASK_BOARD_DIR"] = str(BOARDS_DIR)
sys.path.insert(0, str(ROOT / "src" / "mcp"))
sys.path.insert(0, str(ROOT / "src"))

from core.config_store import apply_config, load_config, public_config, save_config  # noqa: E402
from core.cursor_config import (  # noqa: E402
    get_api_key,
    public_config as public_cursor_config,
    save_config as save_cursor_config,
)
from core.intent import (  # noqa: E402
    DDL_BLOCKED_MESSAGE,
    classify_info_query,
    classify_intent,
    is_ddl_request,
)
from core import mysql_client  # noqa: E402
from web.cursor_orchestrator import CursorAgentLoopOrchestrator  # noqa: E402
from web.orchestrator import PHASE_LABELS, derive_phase, extract_report  # noqa: E402
import task_board_server as board  # noqa: E402

STATIC_DIR = ROOT / "web" / "static"
apply_config(load_config())

app = FastAPI(title="Agent-Loop 数据分析", version="0.2.1")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

_jobs: dict[str, dict[str, Any]] = {}
_jobs_lock = threading.Lock()


class AnalyzeRequest(BaseModel):
    question: str = Field(..., min_length=2, max_length=500)


class MysqlConfigRequest(BaseModel):
    host: str = "localhost"
    port: int = 3306
    user: str = "root"
    password: str = ""
    database: str = "mysql_dataset_test"
    allow_writes: bool = False


class CursorConfigRequest(BaseModel):
    api_key: str = ""
    model: str = "composer-2.5"


def _board_path(board_id: str) -> Path:
    return BOARDS_DIR / f"{board_id}.json"


def _read_board_file(board_id: str) -> dict[str, Any] | None:
    path = _board_path(board_id)
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _write_board_file(board: dict[str, Any]) -> None:
    BOARDS_DIR.mkdir(parents=True, exist_ok=True)
    path = _board_path(board["board_id"])
    path.write_text(json.dumps(board, ensure_ascii=False, indent=2), encoding="utf-8")


def _set_job(board_id: str, **kwargs: Any) -> None:
    with _jobs_lock:
        _jobs.setdefault(board_id, {})
        _jobs[board_id].update(kwargs)
    board_data = _read_board_file(board_id)
    if board_data is not None:
        board_data["web_job"] = {**board_data.get("web_job", {}), **kwargs}
        board_data["updated_at"] = datetime.now(timezone.utc).isoformat()
        _write_board_file(board_data)


def _get_job(board_id: str) -> dict[str, Any] | None:
    with _jobs_lock:
        if board_id in _jobs:
            return dict(_jobs[board_id])
    board_data = _read_board_file(board_id)
    if board_data and board_data.get("web_job"):
        return dict(board_data["web_job"])
    return None


def _find_job(board_id: str) -> dict[str, Any] | None:
    direct = _get_job(board_id)
    if direct:
        return direct
    with _jobs_lock:
        for job in _jobs.values():
            if job.get("board_id") == board_id:
                return dict(job)
    return None


def _create_board(requirement: str, board_id: str | None = None) -> str:
    bid = board_id or str(uuid.uuid4())
    empty_board = {
        "board_id": bid,
        "requirement": requirement,
        "status": "planning",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "rework_rounds": 0,
        "rework_history": [],
        "tasks": [],
        "web_job": {
            "status": "running",
            "phase": "planning",
            "phase_label": PHASE_LABELS["planning"],
            "detail": "看板已创建，等待 Agent 启动…",
        },
    }
    _write_board_file(empty_board)
    board._save_board(empty_board)  # type: ignore[attr-defined]
    return bid


def _load_board(board_id: str) -> dict[str, Any] | None:
    raw = _read_board_file(board_id)
    if raw is None:
        return None
    try:
        return json.loads(board.list_tasks(board_id=board_id))
    except ValueError:
        return raw


def _run_info_query(question: str, board_id: str) -> dict[str, Any]:
    """直接执行数据库信息查询，不走 agent-loop，返回立即结果的 report 字典。"""
    info_type, table_name = classify_info_query(question)
    try:
        if info_type == "list_tables":
            tables = mysql_client.list_tables()
            lines = "\n".join(f"- `{t}`" for t in tables)
            report = (
                f"## 1. 分析概要\n\n"
                f"当前数据库共有 **{len(tables)}** 张表。\n\n"
                f"## 2. 表列表\n\n{lines}\n\n"
                f"## 3. 说明\n\n如需查看某张表的字段结构，请输入「XX表有哪些字段」。"
            )
        elif info_type == "describe_table":
            columns = mysql_client.describe_table(table_name)
            header = "| 字段名 | 类型 | 是否可空 | 键 | 默认值 | 额外信息 |"
            sep = "|------|------|--------|---|------|--------|"
            rows = "\n".join(
                f"| {c['Field']} | {c['Type']} | {c['Null']} | {c['Key']} | "
                f"{c['Default'] or ''} | {c.get('Extra', '')} |"
                for c in columns
            )
            report = (
                f"## 1. 分析概要\n\n"
                f"表 **`{table_name}`** 共有 **{len(columns)}** 个字段。\n\n"
                f"## 2. 字段结构\n\n{header}\n{sep}\n{rows}\n"
            )
        else:
            raise ValueError(f"未知的信息查询类型: {info_type}")
    except Exception as exc:
        return {
            "board_id": board_id,
            "phase": "failed",
            "phase_label": "失败",
            "passed": False,
            "report": f"## 查询失败\n\n{exc}",
            "verify_summary": str(exc),
        }

    return {
        "board_id": board_id,
        "phase": "done",
        "phase_label": "已完成",
        "passed": True,
        "report": report,
        "verify_summary": "信息查询已完成。",
    }


def _run_general_chat(question: str) -> str:
    """调用 Cursor SDK 通用模型回答非分析类问题（阻塞调用，需在线程中执行）。"""
    from cursor_sdk import Agent, AgentOptions, LocalAgentOptions, SendOptions
    from core.cursor_config import get_api_key, get_model
    api_key = get_api_key()
    if not api_key:
        return "当前未配置 Cursor API Key，无法回答通用问题。请先在管理员配置中填写。"
    prompt = (
        "你是数据分析助手。用户提出以下问题（非数据分析类），请用中文给出简洁、友好的回答。\n\n"
        f"用户问题：{question}"
    )
    with Agent.create(
        AgentOptions(
            api_key=api_key,
            model=get_model(),
            local=LocalAgentOptions(cwd=str(ROOT)),
        )
    ) as agent:
        result = agent.send(prompt, SendOptions())
        text = ""
        for msg in result.messages():
            if getattr(msg, "type", "") == "assistant":
                for block in getattr(msg.message, "content", []):
                    if getattr(block, "type", "") == "text":
                        text += getattr(block, "text", "")
        return text.strip() or "抱歉，暂时无法回答这个问题。"


def _run_analysis(board_id: str, question: str) -> None:
    def on_progress(phase: str, detail: str, extra: dict[str, Any]) -> None:
        _set_job(
            board_id,
            requirement=question,
            phase=phase,
            phase_label=PHASE_LABELS.get(phase, phase),
            detail=detail,
            status="running",
        )

    try:
        if not get_api_key():
            raise RuntimeError("未配置 CURSOR_API_KEY。请在管理员配置中填写 Cursor API Key。")
        orchestrator = CursorAgentLoopOrchestrator(on_progress=on_progress)
        result = orchestrator.run(question, board_id=board_id)
        _set_job(
            board_id,
            requirement=question,
            phase=result["phase"],
            phase_label=result["phase_label"],
            status="done" if result["passed"] else "failed",
            report=result.get("report"),
            passed=result["passed"],
            verify_summary=result.get("verify_summary"),
            fix_items=result.get("fix_items", []),
            detail=result.get("verify_summary") or "分析完成",
        )
    except Exception as exc:
        _set_job(
            board_id,
            requirement=question,
            phase="failed",
            phase_label=PHASE_LABELS["failed"],
            status="failed",
            detail=str(exc),
            error=str(exc),
            passed=False,
        )


@app.get("/")
async def index():
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/api/health")
async def health():
    return {
        "status": "ok",
        "service": "agent-loop-web",
        "cursor_api_key_set": bool(get_api_key()),
        "engine": "cursor-sdk",
        "boards_dir": str(BOARDS_DIR),
    }


@app.post("/api/analyze")
async def start_analyze(req: AnalyzeRequest, background_tasks: BackgroundTasks):
    question = req.question.strip()
    if not question:
        raise HTTPException(400, "问题不能为空")

    # ── DDL / 写操作：固定拒绝，禁止调用 Agent 或模型 ──
    if is_ddl_request(question):
        board_id = _create_board(question)
        _set_job(
            board_id,
            requirement=question,
            phase="done",
            phase_label="禁止操作",
            status="done",
            report=DDL_BLOCKED_MESSAGE,
            passed=False,
            verify_summary=DDL_BLOCKED_MESSAGE,
            detail=DDL_BLOCKED_MESSAGE,
        )
        return {
            "board_id": board_id,
            "status": "done",
            "direct": True,
            "blocked": True,
            "phase": "done",
            "phase_label": "禁止操作",
            "passed": False,
            "report": DDL_BLOCKED_MESSAGE,
            "verify_summary": DDL_BLOCKED_MESSAGE,
        }

    # ── 信息查询：直连 MySQL，不走 agent-loop ──
    info_type, table_name = classify_info_query(question)
    if info_type:
        apply_config(load_config())
        board_id = _create_board(question)
        result = _run_info_query(question, board_id)
        _set_job(
            board_id,
            requirement=question,
            phase=result["phase"],
            phase_label=result["phase_label"],
            status="done" if result["passed"] else "failed",
            report=result.get("report"),
            passed=result["passed"],
            verify_summary=result.get("verify_summary"),
            detail=result.get("verify_summary") or "查询完成",
        )
        return {
            "board_id": board_id,
            "status": "done",
            "direct": True,
            **result,
        }

    # ── 非分析类问题：调用 Cursor SDK 通用回答（不走 agent-loop） ──
    analysis_type = classify_intent(question)
    if analysis_type is None:
        board_id = _create_board(question)
        try:
            loop = asyncio.get_event_loop()
            reply = await loop.run_in_executor(None, _run_general_chat, question)
            report = f"## 回答\n\n{reply}"
        except Exception as exc:
            report = (
                f"## 抱歉\n\n无法获取回答：{exc}\n\n"
                "温馨提示：当前系统专注于 **数据分析类问题**，"
                "如「近半年销售情况怎么样」「分析用户流失」「对比订单增长」等。"
            )
        _set_job(board_id, requirement=question, phase="done", phase_label="已回答",
                 status="done", report=report, passed=True,
                 verify_summary="通用问题已回答。",
                 detail="通用问题已回答。")
        return {"board_id": board_id, "status": "done", "direct": True,
                "phase": "done", "phase_label": "已回答", "passed": True,
                "report": report, "verify_summary": "通用问题已回答。"}

    if not get_api_key():
        raise HTTPException(
            400,
            "未配置 CURSOR_API_KEY。请点击右上角「管理员配置」填写 Cursor API Key。",
        )

    board_id = _create_board(question)
    _set_job(
        board_id,
        requirement=question,
        phase="planning",
        phase_label=PHASE_LABELS["planning"],
        status="running",
        detail="正在启动 Cursor Agent…",
    )
    background_tasks.add_task(_run_analysis, board_id, question)

    return {
        "board_id": board_id,
        "status": "started",
        "message": "分析已启动",
    }


@app.post("/api/analyze/sync")
async def analyze_sync(req: AnalyzeRequest):
    question = req.question.strip()
    if not question:
        raise HTTPException(400, "问题不能为空")

    if is_ddl_request(question):
        board_id = _create_board(question)
        return {
            "board_id": board_id,
            "direct": True,
            "blocked": True,
            "phase": "done",
            "phase_label": "禁止操作",
            "passed": False,
            "report": DDL_BLOCKED_MESSAGE,
            "verify_summary": DDL_BLOCKED_MESSAGE,
        }

    # ── 信息查询：直连 MySQL，不走 agent-loop ──
    info_type, table_name = classify_info_query(question)
    if info_type:
        apply_config(load_config())
        board_id = _create_board(question)
        result = _run_info_query(question, board_id)
        return {"board_id": board_id, "direct": True, **result}

    analysis_type = classify_intent(question)
    if analysis_type is None:
        board_id = _create_board(question)
        try:
            reply = await asyncio.get_event_loop().run_in_executor(
                None, _run_general_chat, question
            )
            report = f"## 回答\n\n{reply}"
        except Exception as exc:
            report = f"## 抱歉\n\n无法获取回答：{exc}"
        return {"board_id": board_id, "direct": True,
                "phase": "done", "phase_label": "已回答", "passed": True,
                "report": report, "verify_summary": "通用问题已回答。"}

    if not get_api_key():
        raise HTTPException(400, "未配置 CURSOR_API_KEY")

    board_id = _create_board(question)
    loop = asyncio.get_event_loop()
    try:
        result = await loop.run_in_executor(
            None,
            lambda: CursorAgentLoopOrchestrator().run(question, board_id=board_id),
        )
    except RuntimeError as exc:
        raise HTTPException(400, str(exc)) from exc

    return {
        "board_id": result["board_id"],
        "phase": result["phase"],
        "phase_label": result["phase_label"],
        "passed": result["passed"],
        "report": result.get("report"),
        "verify_summary": result.get("verify_summary"),
        "fix_items": result.get("fix_items", []),
    }


@app.get("/api/analyze/{board_id}/status")
async def analyze_status(board_id: str):
    job = _find_job(board_id)
    board_file = _read_board_file(board_id)
    board_data = _load_board(board_id)

    if board_file is None and job is None:
        raise HTTPException(404, f"看板不存在: {board_id}")

    if board_data is None and board_file is not None:
        board_data = board_file

    if board_data is None:
        return {
            "board_id": board_id,
            "requirement": job.get("requirement", "") if job else "",
            **(job or {}),
        }

    phase = derive_phase({**board_data, "status": board_data.get("board_status")})
    report = extract_report(board_data)

    payload: dict[str, Any] = {
        "board_id": board_id,
        "requirement": board_data.get("requirement", ""),
        "phase": phase,
        "phase_label": PHASE_LABELS.get(phase, phase),
        "board_status": board_data.get("board_status", ""),
        "report": report,
        "updated_at": board_data.get("updated_at", ""),
    }
    if job:
        payload.update(job)
        if job.get("status") in ("done", "failed"):
            payload["report"] = job.get("report") or report
    return payload


@app.get("/api/analyze/{board_id}/report")
async def get_report(board_id: str):
    job = _find_job(board_id)
    board_file = _read_board_file(board_id)
    board_data = _load_board(board_id)

    if board_file is None and job is None:
        raise HTTPException(404, f"看板不存在: {board_id}")

    if board_data is None and board_file is not None:
        board_data = board_file

    if board_data is None and job and job.get("report"):
        return {
            "board_id": board_id,
            "requirement": job.get("requirement", ""),
            "report": job["report"],
            "phase": job.get("phase", "done"),
            "phase_label": job.get("phase_label", ""),
        }

    if board_data is None:
        raise HTTPException(404, f"看板不存在: {board_id}")

    report = extract_report(board_data) or (job.get("report") if job else None)
    if not report:
        raise HTTPException(404, "任务失败，请确认问题描述是否符合分析类范畴。失败后请重新描述问题并提交。")
    return {
        "board_id": board_id,
        "requirement": board_data.get("requirement", ""),
        "report": report,
        "phase": derive_phase({**board_data, "status": board_data.get("board_status")}),
        "phase_label": job.get("phase_label", "") if job else "",
    }


@app.get("/api/history")
async def list_history():
    raw = json.loads(board.list_tasks())
    items = []
    for item in sorted(raw.get("boards", []), key=lambda x: x.get("updated_at", ""), reverse=True):
        bid = item.get("board_id", "")
        if not bid:
            continue
        detail = _load_board(bid)
        if detail is None:
            continue
        items.append({
            "board_id": bid,
            "requirement": item.get("requirement", ""),
            "status": item.get("status", ""),
            "phase": derive_phase(detail),
            "phase_label": PHASE_LABELS.get(derive_phase(detail), ""),
            "updated_at": item.get("updated_at", ""),
            "has_report": bool(extract_report(detail)),
        })
    return {"items": items, "count": len(items)}


@app.delete("/api/analyze/{board_id}")
async def delete_analysis(board_id: str):
    board_path = _board_path(board_id)
    if board_path.exists():
        board_path.unlink()
    with _jobs_lock:
        _jobs.pop(board_id, None)
    return {"message": "已删除", "board_id": board_id}


@app.get("/api/admin/mysql-config")
async def get_mysql_config():
    return public_config()


@app.put("/api/admin/mysql-config")
async def update_mysql_config(req: MysqlConfigRequest):
    saved = save_config(req.model_dump())
    return {"message": "MySQL 配置已保存", "config": public_config(saved)}


@app.post("/api/admin/test-connection")
async def test_mysql_connection(req: MysqlConfigRequest | None = None):
    if req:
        save_config(req.model_dump())
    else:
        apply_config(load_config())
    try:
        return mysql_client.test_connection()
    except Exception as exc:
        raise HTTPException(400, f"连接失败: {exc}") from exc


@app.get("/api/admin/cursor-config")
async def get_cursor_config():
    return public_cursor_config()


@app.put("/api/admin/cursor-config")
async def update_cursor_config(req: CursorConfigRequest):
    saved = save_cursor_config(req.model_dump())
    return {"message": "Cursor 配置已保存", "config": public_cursor_config(saved)}


@app.post("/api/admin/test-cursor-key")
async def test_cursor_key(req: CursorConfigRequest | None = None):
    """测试 Cursor API Key 是否有效。"""
    if req and req.api_key:
        save_cursor_config(req.model_dump())
    from core.cursor_config import get_api_key, get_model
    key = get_api_key()
    if not key:
        raise HTTPException(400, "未配置 API Key")
    try:
        from cursor_sdk import Cursor
        models = Cursor.models.list() if hasattr(Cursor, "models") else []
        return {"status": "ok", "message": f"API Key 有效（{len(models)} 个模型可用）", "model_count": len(models)}
    except Exception as exc:
        raise HTTPException(400, f"API Key 无效或连接失败: {exc}") from exc


if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
