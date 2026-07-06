"""基于 Cursor SDK 的 agent-loop 编排器（与 IDE 内行为一致）。"""

from __future__ import annotations

import json
import os
import re
import sys
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

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

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src" / "mcp"))
sys.path.insert(0, str(ROOT / "src"))

from core.config_store import apply_config, load_config as load_mysql_config  # noqa: E402
from core.cursor_config import get_api_key, get_model  # noqa: E402
from web.orchestrator import (  # noqa: E402
    PHASE_LABELS,
    derive_phase,
    extract_report,
)
import task_board_server as board  # noqa: E402

PYTHON_EXE = ROOT / ".venv" / "Scripts" / "python.exe"
if not PYTHON_EXE.exists():
    PYTHON_EXE = ROOT / ".venv" / "bin" / "python"
LAUNCHER = ROOT / "src" / "mcp" / "launcher.py"

MAIN_PROMPT = """你是 agent-loop 主调度 Agent。用户数据分析需求：

「{requirement}」

看板已创建，board_id = `{board_id}`。

必须严格按 `.cursor/skills/agent-loop/SKILL.md` 执行完整闭环：

1. **不要**再 create_task 新建看板，直接在 board_id `{board_id}` 上操作
2. 委派 **planner-agent**：在该看板上创建 T1~T4、assign_task、append_result 规划 JSON
3. 委派 **builder-agent**：mysql-local 探库/SQL/撰写六节报告，每步 append_result + complete_task
4. 委派 **verifier-agent**：独立验收；失败时 verifier 内部 request_rework 并再次 Task(builder-agent)（最多 2 轮）
5. verifier 返回 passed:true 后，从 T3 的 builder-agent results 提取**完整六节 Markdown 报告**

硬性约束：
- 主 Agent **禁止**直接调用 mysql-local
- 报告结构见 `.cursor/skills/agent-loop/report-template.md` 六节，不得增删
- 全部使用中文
- 最终回复必须包含 T3 完整六节报告正文（## 1. 分析概要 起）
"""


def _build_mcp_servers(mysql_cfg: dict[str, Any]) -> dict[str, Any]:
    py = str(PYTHON_EXE)
    launcher = str(LAUNCHER)
    boards_dir = str(ROOT / "boards")
    return {
        "mysql-local": {
            "type": "stdio",
            "command": py,
            "args": [launcher, "server.py"],
            "env": {
                "MYSQL_HOST": str(mysql_cfg["host"]),
                "MYSQL_PORT": str(mysql_cfg["port"]),
                "MYSQL_USER": str(mysql_cfg["user"]),
                "MYSQL_PASSWORD": str(mysql_cfg.get("password", "")),
                "MYSQL_DATABASE": str(mysql_cfg["database"]),
                "MYSQL_ALLOW_WRITES": "true" if mysql_cfg.get("allow_writes") else "false",
                "PYTHONUTF8": "1",
                "PYTHONIOENCODING": "utf-8",
            },
        },
        "task-board": {
            "type": "stdio",
            "command": py,
            "args": [launcher, "task_board_server.py"],
            "env": {
                "TASK_BOARD_DIR": boards_dir,
                "PYTHONUTF8": "1",
                "PYTHONIOENCODING": "utf-8",
            },
        },
    }


def _extract_report_from_text(text: str) -> str | None:
    if not text:
        return None
    match = re.search(r"(##\s*1\.\s*分析概要[\s\S]+)", text)
    return match.group(1).strip() if match else None


def _infer_phase_from_step(step: Any) -> str | None:
    blob = str(step).lower()
    if "verifier-agent" in blob or "verifier" in blob and "agent" in blob:
        return "verifying"
    if "builder-agent" in blob or "execute_query" in blob or "list_tables" in blob:
        return "building"
    if "planner-agent" in blob or "create_task" in blob or "assign_task" in blob:
        return "planning"
    return None


class CursorAgentLoopOrchestrator:
    """通过 Cursor SDK 本地 Agent 运行 planner → builder → verifier。"""

    def __init__(self, on_progress: Callable[[str, str, dict[str, Any]], None] | None = None):
        self.on_progress = on_progress or (lambda *_: None)

    def _emit(self, board_id: str, phase: str, detail: str = "", extra: dict | None = None):
        self.on_progress(phase, detail, {"board_id": board_id, **(extra or {})})

    def run(self, requirement: str, board_id: str | None = None) -> dict[str, Any]:
        api_key = get_api_key()
        if not api_key:
            raise RuntimeError(
                "未配置 CURSOR_API_KEY。请在 Web 管理员配置中填写 Cursor API Key，"
                "或设置环境变量 CURSOR_API_KEY。"
            )

        apply_config(load_mysql_config())
        mysql_cfg = load_mysql_config()

        if board_id:
            try:
                board._load_board(board_id)  # type: ignore[attr-defined]
            except ValueError:
                empty_board = {
                    "board_id": board_id,
                    "requirement": requirement,
                    "status": "planning",
                    "created_at": datetime.now(timezone.utc).isoformat(),
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                    "rework_rounds": 0,
                    "rework_history": [],
                    "tasks": [],
                }
                board._save_board(empty_board)  # type: ignore[attr-defined]
        else:
            board_id = str(uuid.uuid4())
            empty_board = {
                "board_id": board_id,
                "requirement": requirement,
                "status": "planning",
                "created_at": datetime.now(timezone.utc).isoformat(),
                "updated_at": datetime.now(timezone.utc).isoformat(),
                "rework_rounds": 0,
                "rework_history": [],
                "tasks": [],
            }
            board._save_board(empty_board)  # type: ignore[attr-defined]

        self._emit(board_id, "planning", "主 Agent 启动 agent-loop…")

        try:
            from cursor_sdk import Agent, AgentOptions, LocalAgentOptions, SendOptions
        except ImportError as exc:
            raise RuntimeError("缺少 cursor-sdk，请运行 pip install cursor-sdk") from exc

        stop_poll = threading.Event()
        final_text_holder: dict[str, str] = {"text": ""}

        def poll_board():
            last_phase = ""
            while not stop_poll.is_set():
                try:
                    raw = json.loads(board.list_tasks(board_id=board_id))
                    phase = derive_phase({**raw, "status": raw.get("board_status")})
                    if phase != last_phase:
                        last_phase = phase
                        if phase in ("planning", "building", "verifying", "rework"):
                            self._emit(board_id, phase, PHASE_LABELS.get(phase, phase))
                except Exception:
                    pass
                time.sleep(2)

        poll_thread = threading.Thread(target=poll_board, daemon=True)
        poll_thread.start()

        def on_step(step: Any) -> None:
            phase = _infer_phase_from_step(step)
            if phase:
                self._emit(board_id, phase, str(getattr(step, "type", phase)))

        prompt = MAIN_PROMPT.format(requirement=requirement, board_id=board_id)
        mcp_servers = _build_mcp_servers(mysql_cfg)

        try:
            with Agent.create(
                AgentOptions(
                    api_key=api_key,
                    model=get_model(),
                    local=LocalAgentOptions(
                        cwd=str(ROOT),
                        setting_sources=["project"],
                    ),
                    mcp_servers=mcp_servers,
                )
            ) as agent:
                run = agent.send(
                    prompt,
                    SendOptions(mcp_servers=mcp_servers, on_step=on_step),
                )
                for message in run.messages():
                    if getattr(message, "type", "") == "assistant":
                        for block in getattr(message.message, "content", []):
                            if getattr(block, "type", "") == "text":
                                final_text_holder["text"] += getattr(block, "text", "")
                result = run.wait()
                if result.status == "error":
                    raise RuntimeError(f"Cursor Agent 执行失败: run_id={result.id}")
        finally:
            stop_poll.set()
            poll_thread.join(timeout=3)

        board_data = json.loads(board.list_tasks(board_id=board_id))
        report = extract_report(board_data) or _extract_report_from_text(final_text_holder["text"])
        phase = derive_phase({**board_data, "status": board_data.get("board_status")})

        passed = board_data.get("board_status") == "done" and bool(report)
        verify_summary = "验收通过，报告已生成。" if passed else "分析已完成，请查看报告或看板状态。"
        fix_items: list[str] = []

        if board_data.get("board_status") == "blocked":
            passed = False
            verify_summary = "验收未通过或回修轮次用尽。"
            latest = board_data.get("latest_rework") or {}
            fix_items = latest.get("fix_items", [])

        if not report:
            passed = False
            verify_summary = "未找到六节报告，请检查 builder-agent 是否写入 T3。"

        return {
            "board_id": board_id,
            "phase": "done" if passed else ("failed" if phase == "failed" else phase),
            "phase_label": PHASE_LABELS.get("done" if passed else phase, phase),
            "passed": passed,
            "report": report,
            "verify_summary": verify_summary,
            "fix_items": fix_items,
        }
