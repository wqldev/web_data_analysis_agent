"""Task Board MCP 服务：支持 Agent 协作闭环的任务看板。"""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("task-board")

VALID_STATUSES = {"pending", "assigned", "in_progress", "completed", "blocked"}
VALID_ASSIGNEES = {"planner-agent", "builder-agent", "verifier-agent"}
MAX_REWORK_ROUNDS = 2


def _boards_dir() -> Path:
    env_dir = os.getenv("TASK_BOARD_DIR")
    if env_dir:
        return Path(env_dir)
    return Path(__file__).resolve().parents[2] / "boards"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _board_path(board_id: str) -> Path:
    if not board_id or "/" in board_id or "\\" in board_id:
        raise ValueError("board_id 无效")
    return _boards_dir() / f"{board_id}.json"


def _load_board(board_id: str) -> dict[str, Any]:
    path = _board_path(board_id)
    if not path.exists():
        raise ValueError(f"看板不存在: {board_id}")
    return json.loads(path.read_text(encoding="utf-8"))


def _save_board(board: dict[str, Any]) -> None:
    board_dir = _boards_dir()
    board_dir.mkdir(parents=True, exist_ok=True)
    path = _board_path(board["board_id"])
    path.write_text(json.dumps(board, ensure_ascii=False, indent=2), encoding="utf-8")


def _find_task(board: dict[str, Any], task_id: str) -> dict[str, Any]:
    for task in board["tasks"]:
        if task["task_id"] == task_id:
            return task
    raise ValueError(f"任务不存在: {task_id}")


def _ensure_rework_fields(board: dict[str, Any]) -> None:
    board.setdefault("rework_rounds", 0)
    board.setdefault("rework_history", [])


def _latest_rework(board: dict[str, Any]) -> dict[str, Any] | None:
    history = board.get("rework_history") or []
    return history[-1] if history else None


def _find_verifier_task(board: dict[str, Any]) -> dict[str, Any] | None:
    for task in board["tasks"]:
        if task.get("assignee") == "verifier-agent":
            return task
    for task in board["tasks"]:
        if task["task_id"] == "T4":
            return task
    return None


def _format_board(board: dict[str, Any]) -> str:
    return json.dumps(board, ensure_ascii=False, indent=2)


@mcp.tool()
def create_task(
    title: str,
    description: str = "",
    acceptance_criteria: list[str] | None = None,
    board_id: str = "",
    requirement: str = "",
    task_id: str = "",
) -> str:
    """在看板上创建任务。若 board_id 为空则新建看板。"""
    if not title.strip():
        raise ValueError("title 不能为空")

    if board_id:
        board = _load_board(board_id)
    else:
        board_id = str(uuid.uuid4())
        board = {
            "board_id": board_id,
            "requirement": requirement or title,
            "status": "planning",
            "created_at": _now_iso(),
            "updated_at": _now_iso(),
            "rework_rounds": 0,
            "rework_history": [],
            "tasks": [],
        }

    existing_ids = {t["task_id"] for t in board["tasks"]}
    if not task_id:
        index = len(board["tasks"]) + 1
        task_id = f"T{index}"
        while task_id in existing_ids:
            index += 1
            task_id = f"T{index}"
    elif task_id in existing_ids:
        raise ValueError(f"任务 ID 已存在: {task_id}")

    task = {
        "task_id": task_id,
        "title": title.strip(),
        "description": description.strip(),
        "acceptance_criteria": acceptance_criteria or [],
        "status": "pending",
        "assignee": None,
        "results": [],
        "created_at": _now_iso(),
        "updated_at": _now_iso(),
    }
    board["tasks"].append(task)
    board["updated_at"] = _now_iso()
    _save_board(board)

    return json.dumps(
        {
            "message": "任务已创建",
            "board_id": board_id,
            "task": task,
        },
        ensure_ascii=False,
        indent=2,
    )


@mcp.tool()
def assign_task(board_id: str, task_id: str, assignee: str) -> str:
    """将任务分配给指定 subagent。"""
    if assignee not in VALID_ASSIGNEES:
        raise ValueError(f"assignee 必须是: {', '.join(sorted(VALID_ASSIGNEES))}")

    board = _load_board(board_id)
    task = _find_task(board, task_id)
    task["assignee"] = assignee
    task["status"] = "assigned"
    task["updated_at"] = _now_iso()
    board["updated_at"] = _now_iso()
    _save_board(board)

    return json.dumps(
        {
            "message": "任务已分配",
            "board_id": board_id,
            "task_id": task_id,
            "assignee": assignee,
            "status": task["status"],
        },
        ensure_ascii=False,
        indent=2,
    )


@mcp.tool()
def append_result(
    board_id: str,
    task_id: str,
    agent: str,
    content: str,
    set_status: str = "",
) -> str:
    """向任务追加执行结果。可选 set_status 同步更新任务状态。"""
    if not content.strip():
        raise ValueError("content 不能为空")
    if set_status and set_status not in VALID_STATUSES:
        raise ValueError(f"set_status 必须是: {', '.join(sorted(VALID_STATUSES))}")

    board = _load_board(board_id)
    task = _find_task(board, task_id)
    entry = {
        "agent": agent,
        "timestamp": _now_iso(),
        "content": content.strip(),
    }
    task["results"].append(entry)
    if set_status:
        task["status"] = set_status
    elif task["status"] == "assigned":
        task["status"] = "in_progress"
    task["updated_at"] = _now_iso()
    board["updated_at"] = _now_iso()
    _save_board(board)

    return json.dumps(
        {
            "message": "结果已追加",
            "board_id": board_id,
            "task_id": task_id,
            "result_count": len(task["results"]),
            "status": task["status"],
        },
        ensure_ascii=False,
        indent=2,
    )


@mcp.tool()
def list_tasks(
    board_id: str = "",
    status: str = "",
    assignee: str = "",
) -> str:
    """列出看板任务，可按 status / assignee 过滤。board_id 为空时列出所有看板摘要。"""
    board_dir = _boards_dir()
    if not board_dir.exists():
        return json.dumps({"boards": [], "count": 0}, ensure_ascii=False, indent=2)

    if not board_id:
        summaries = []
        for path in sorted(board_dir.glob("*.json")):
            if path.name.endswith("_builder_out.json"):
                continue
            board = json.loads(path.read_text(encoding="utf-8"))
            if "board_id" not in board:
                continue
            summaries.append(
                {
                    "board_id": board["board_id"],
                    "requirement": board.get("requirement", ""),
                    "status": board.get("status", ""),
                    "task_count": len(board.get("tasks", [])),
                    "updated_at": board.get("updated_at", ""),
                }
            )
        return json.dumps({"boards": summaries, "count": len(summaries)}, ensure_ascii=False, indent=2)

    board = _load_board(board_id)
    _ensure_rework_fields(board)
    tasks = board.get("tasks", [])
    if status:
        tasks = [t for t in tasks if t.get("status") == status]
    if assignee:
        tasks = [t for t in tasks if t.get("assignee") == assignee]

    payload: dict[str, Any] = {
        "board_id": board_id,
        "requirement": board.get("requirement", ""),
        "board_status": board.get("status", ""),
        "rework_rounds": board.get("rework_rounds", 0),
        "max_rework_rounds": MAX_REWORK_ROUNDS,
        "latest_rework": _latest_rework(board),
        "tasks": tasks,
        "count": len(tasks),
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


@mcp.tool()
def request_rework(
    board_id: str,
    fix_items: list[str],
    note: str = "",
) -> str:
    """verifier 打回 builder 修复：记录 fix_items、递增回修轮次，并标记 builder 任务待修复。"""
    cleaned = [item.strip() for item in fix_items if item and item.strip()]
    if not cleaned:
        raise ValueError("fix_items 不能为空")

    board = _load_board(board_id)
    _ensure_rework_fields(board)
    board["rework_rounds"] = int(board.get("rework_rounds", 0)) + 1
    allowed = board["rework_rounds"] <= MAX_REWORK_ROUNDS

    entry = {
        "round": board["rework_rounds"],
        "fix_items": cleaned,
        "note": note.strip(),
        "timestamp": _now_iso(),
        "allowed": allowed,
        "triggered_by": "verifier-agent",
    }
    board["rework_history"].append(entry)

    for task in board["tasks"]:
        if task.get("assignee") != "builder-agent":
            continue
        if task["task_id"] in {"T2", "T3"} and task.get("status") == "completed":
            task["status"] = "in_progress"
            task["updated_at"] = _now_iso()

    verifier_task = _find_verifier_task(board)
    if verifier_task:
        verifier_task["results"].append(
            {
                "agent": "verifier-agent",
                "timestamp": _now_iso(),
                "content": json.dumps(
                    {
                        "passed": False,
                        "fix_items": cleaned,
                        "rework_round": board["rework_rounds"],
                        "rework_allowed": allowed,
                        "note": note.strip(),
                    },
                    ensure_ascii=False,
                ),
            }
        )
        verifier_task["status"] = "blocked" if not allowed else "in_progress"
        verifier_task["updated_at"] = _now_iso()

    board["status"] = "rework" if allowed else "blocked"
    board["updated_at"] = _now_iso()
    _save_board(board)

    return json.dumps(
        {
            "message": "已记录回修请求",
            "board_id": board_id,
            "rework_round": board["rework_rounds"],
            "max_rework_rounds": MAX_REWORK_ROUNDS,
            "rework_allowed": allowed,
            "fix_items": cleaned,
            "next_action": (
                "Task(builder-agent) 并传入 board_id 与 fix_items"
                if allowed
                else "回修轮次已用尽，向主 Agent 返回最终 failed 结论"
            ),
        },
        ensure_ascii=False,
        indent=2,
    )


@mcp.tool()
def complete_task(board_id: str, task_id: str) -> str:
    """将任务标记为 completed。"""
    board = _load_board(board_id)
    task = _find_task(board, task_id)
    task["status"] = "completed"
    task["updated_at"] = _now_iso()
    board["updated_at"] = _now_iso()

    pending = [t for t in board["tasks"] if t["status"] != "completed"]
    if not pending:
        board["status"] = "done"

    _save_board(board)

    return json.dumps(
        {
            "message": "任务已完成",
            "board_id": board_id,
            "task_id": task_id,
            "board_status": board["status"],
            "remaining_tasks": len(pending),
        },
        ensure_ascii=False,
        indent=2,
    )


if __name__ == "__main__":
    mcp.run(transport="stdio")
