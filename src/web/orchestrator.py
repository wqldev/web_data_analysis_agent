"""Web 端 agent-loop 编排器：planner → builder → verifier（LLM 驱动）。"""

from __future__ import annotations

import json
import re
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src" / "mcp"))
sys.path.insert(0, str(ROOT / "src"))

from core.intent import AnalysisType, classify_intent  # noqa: E402
from web import llm_agents  # noqa: E402
import task_board_server as board  # noqa: E402

PHASE_LABELS = {
    "planning": "规划中",
    "building": "取数中",
    "verifying": "验收中",
    "done": "已完成",
    "failed": "失败",
    "rework": "取数中（回修）",
}

REPORT_SECTIONS = [
    "1. 分析概要",
    "2. 核心结论",
    "3. 关键指标",
    "4. 详细分析",
    "5. 业务建议",
    "6. 数据说明与局限",
]


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def derive_phase(board_data: dict[str, Any]) -> str:
    status = board_data.get("status") or board_data.get("board_status", "planning")
    if status == "done":
        return "done"
    if status in ("blocked",):
        return "failed"
    if status == "rework":
        return "rework"

    tasks = board_data.get("tasks", [])
    verifier = next((t for t in tasks if t.get("assignee") == "verifier-agent"), None)
    builder_pending = any(
        t.get("assignee") == "builder-agent" and t.get("status") != "completed"
        for t in tasks
    )

    if verifier and verifier.get("status") in ("assigned", "in_progress", "blocked"):
        return "verifying"
    if builder_pending or status == "building":
        return "building"
    if status == "planning" or not tasks:
        return "planning"
    return "building"


def extract_report(board_data: dict[str, Any]) -> str | None:
    for task in board_data.get("tasks", []):
        if task.get("task_id") != "T3":
            continue
        for result in reversed(task.get("results", [])):
            if result.get("agent") == "builder-agent":
                content = result.get("content", "")
                if "## 1." in content or "## 1 " in content:
                    return content
    return None


class AgentLoopOrchestrator:
    def __init__(
        self,
        on_progress: Callable[[str, str, dict[str, Any]], None] | None = None,
    ):
        self.on_progress = on_progress or (lambda *_: None)

    def _emit(self, board_id: str, phase: str, detail: str = "", extra: dict | None = None):
        self.on_progress(phase, detail, {"board_id": board_id, **(extra or {})})

    def run(self, requirement: str, board_id: str | None = None) -> dict[str, Any]:
        analysis_type, type_label = classify_intent(requirement)

        self._emit("", "planning", f"planner-agent 正在拆解任务…（{llm_agents.llm_status_line()}）")
        plan = self._run_planner(requirement, analysis_type, type_label, board_id)
        board_id = plan["board_id"]

        self._emit(board_id, "building", "builder-agent 正在探库取数…")
        build_result = self._run_builder(board_id, requirement, analysis_type, type_label, plan)

        self._emit(board_id, "verifying", "verifier-agent 正在验收…")
        verify_result = self._run_verifier(board_id, build_result["report"], plan, requirement)

        board_data = json.loads(board.list_tasks(board_id=board_id))
        phase = derive_phase({**board_data, "status": board_data.get("board_status")})
        report = extract_report(board_data)

        return {
            "board_id": board_id,
            "phase": phase,
            "phase_label": PHASE_LABELS.get(phase, phase),
            "passed": verify_result["passed"],
            "report": report,
            "verify_summary": verify_result.get("summary", ""),
            "fix_items": verify_result.get("fix_items", []),
        }

    def _run_planner(
        self,
        requirement: str,
        analysis_type: AnalysisType,
        type_label: str,
        existing_board_id: str | None = None,
    ) -> dict[str, Any]:
        board_id = existing_board_id or str(uuid.uuid4())
        empty_board = {
            "board_id": board_id,
            "requirement": requirement,
            "status": "planning",
            "created_at": _now_iso(),
            "updated_at": _now_iso(),
            "rework_rounds": 0,
            "rework_history": [],
            "tasks": [],
        }
        board._save_board(empty_board)  # type: ignore[attr-defined]

        try:
            schema_context = llm_agents.gather_schema_context()
            llm_plan = llm_agents.planner_plan(
                requirement, analysis_type, type_label, schema_context
            )
            tasks_spec = llm_plan["tasks"]
            plan_notes = llm_plan.get("analysis_notes", "")
        except Exception as exc:
            tasks_spec = llm_agents.default_tasks_spec(type_label)
            plan_notes = f"LLM 规划失败，使用默认任务拆分: {exc}"

        for spec in tasks_spec:
            board.create_task(
                title=spec["title"],
                description=spec.get("description", ""),
                acceptance_criteria=spec.get("acceptance_criteria"),
                board_id=board_id,
                task_id=spec["task_id"],
            )
            board.assign_task(board_id, spec["task_id"], spec["assignee"])

        plan = {
            "board_id": board_id,
            "project": requirement,
            "analysis_type": type_label,
            "analysis_category": analysis_type,
            "analysis_notes": plan_notes,
            "tasks": tasks_spec,
        }
        board.append_result(
            board_id,
            "T1",
            "planner-agent",
            json.dumps(plan, ensure_ascii=False),
            set_status="assigned",
        )

        raw = board._load_board(board_id)  # type: ignore[attr-defined]
        raw["status"] = "building"
        board._save_board(raw)  # type: ignore[attr-defined]
        return plan

    def _run_builder(
        self,
        board_id: str,
        requirement: str,
        analysis_type: AnalysisType,
        type_label: str,
        plan: dict[str, Any],
    ) -> dict[str, Any]:
        schema_context = llm_agents.gather_schema_context()
        plan_notes = plan.get("analysis_notes", "")

        self._emit(board_id, "building", "builder-agent：LLM 探库中…")
        t1_content = llm_agents.builder_explore(
            requirement, type_label, schema_context, plan_notes
        )
        board.append_result(board_id, "T1", "builder-agent", t1_content, set_status="completed")
        board.complete_task(board_id, "T1")

        self._emit(board_id, "building", "builder-agent：LLM 生成 SQL…")
        queries = llm_agents.builder_queries(
            requirement, analysis_type, type_label, t1_content, schema_context
        )

        self._emit(board_id, "building", "builder-agent：执行查询…")
        t2_data, t2_content = llm_agents.execute_queries(queries)
        t2_data["analysis_type"] = analysis_type
        board.append_result(board_id, "T2", "builder-agent", t2_content, set_status="completed")
        board.complete_task(board_id, "T2")

        self._emit(board_id, "building", "builder-agent：LLM 撰写报告…")
        report = llm_agents.builder_report(
            requirement,
            type_label,
            analysis_type,
            t1_content,
            t2_content,
            t2_data,
            plan_notes,
        )
        board.append_result(board_id, "T3", "builder-agent", report, set_status="completed")
        board.complete_task(board_id, "T3")

        return {"report": report, "t2_data": t2_data}

    def _run_verifier(
        self,
        board_id: str,
        report: str,
        plan: dict[str, Any],
        requirement: str,
    ) -> dict[str, Any]:
        try:
            self._emit(board_id, "verifying", "verifier-agent：LLM 验收中…")
            result_payload = llm_agents.verifier_check(requirement, report, plan)
        except Exception as exc:
            self._emit(board_id, "verifying", f"LLM 验收失败，回退规则验收: {exc}")
            result_payload = self._verify_report_rules(report)

        board.assign_task(board_id, "T4", "verifier-agent")
        board.append_result(
            board_id,
            "T4",
            "verifier-agent",
            json.dumps(result_payload, ensure_ascii=False),
            set_status="completed" if result_payload["passed"] else "blocked",
        )
        board.complete_task(board_id, "T4")

        if not result_payload["passed"]:
            raw = board._load_board(board_id)  # type: ignore[attr-defined]
            raw["status"] = "blocked"
            board._save_board(raw)  # type: ignore[attr-defined]

        return result_payload

    def _verify_report_rules(self, report: str) -> dict[str, Any]:
        fix_items: list[str] = []
        structure_checks = []

        for section in REPORT_SECTIONS:
            pattern = section.replace(".", r"\.").replace(" ", r"\s*")
            passed = bool(re.search(rf"##\s*{pattern}", report, re.I))
            structure_checks.append({"section": section, "passed": passed})
            if not passed:
                fix_items.append(f"缺少 {section}")

        kpi_ok = "| 指标 |" in report and report.count("|") >= 12
        if not kpi_ok:
            fix_items.append("第 3 节关键指标表格不完整")

        bullet_count = len(re.findall(r"^-\s+", report, re.M))
        if bullet_count < 3:
            fix_items.append("第 2 节核心结论不足 3 条")

        passed = len(fix_items) == 0
        summary = "六节结构齐全，关键指标与结论数量达标。" if passed else f"验收未通过：{'; '.join(fix_items)}"

        return {
            "passed": passed,
            "summary": summary,
            "rework_rounds_used": 0,
            "structure_checks": structure_checks,
            "fix_items": fix_items,
            "report_task_id": "T3",
        }
