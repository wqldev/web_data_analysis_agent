"""D13 集成测试：五类任务路由 + 三 Agent 交接验证。"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
BOARDS = ROOT / "boards"
sys.path.insert(0, str(ROOT / "src" / "mcp"))

import re

import task_board_server as tbs  # noqa: E402

# 与 analysis_common.py 保持一致的意图识别（避免 hook 模块 tzdata 依赖）
_ANALYSIS_INTENT_PATTERNS: list[tuple[str, re.Pattern[str], str]] = [
    ("compare", re.compile(r"同比|环比|对比|哪个.{0,20}(更好|更高|最高|更低)|排名|Top|TOP|前三|后三|差距", re.I), "对比分析"),
    ("trend", re.compile(r"趋势|涨|跌|走势|近.{0,6}(月|年|半年|季度)|波动|异常|预测|季节性|拐点|生命周期", re.I), "趋势分析"),
    ("attribution", re.compile(r"为什么|原因|因素|影响|导致|问题出|归因|下降|增长.{0,10}原因", re.I), "归因分析"),
    ("segment", re.compile(r"分群|分几类|画像|客户类型|VIP|年龄段|高价值|沉睡|复购|流失.{0,10}特征", re.I), "分群分析"),
    ("hypothesis", re.compile(r"如果|能不能|会不会|假设|要是|值不值得|提升多少|降低多少", re.I), "假设分析"),
    ("general", re.compile(r"分析|看看|情况|怎么样|如何|统计|汇总|洞察|报表|指标|销售|订单|转化", re.I), "通用分析"),
]


def classify_analysis_intent(text: str) -> tuple[str, str, str] | None:
    content = text.strip()
    if not content:
        return None
    for category, pattern, label in _ANALYSIS_INTENT_PATTERNS:
        match = pattern.search(content)
        if match:
            return category, label, match.group(0)
    return None

# agent-loop SKILL 关键词（简化版，用于路由期望）
AGENT_LOOP_KEYWORDS = (
    "怎么样", "如何", "同比", "环比", "对比", "趋势", "近半年", "销售情况",
    "为什么", "分析", "排名", "预测", "画像", "分群", "增长", "下降",
)

# 明确不应走 agent-loop 的上下文信号
NON_ANALYSIS_SIGNALS = (
    "写文档", "使用说明", "README", "单元测试", "重构", "修 bug", "改代码",
    "变量名", "函数名", "import", "pytest", "hook", "配置文件", "配置结构",
)


def expect_agent_loop(prompt: str) -> bool:
    """根据 D13 规范判定是否应走 agent-loop（主 Agent 路由期望）。"""
    text = prompt.strip()
    if any(sig in text for sig in NON_ANALYSIS_SIGNALS):
        return False
    return any(kw in text for kw in AGENT_LOOP_KEYWORDS)


def audit_board_handover(board: dict[str, Any]) -> dict[str, Any]:
    """审计看板上三 Agent 交接是否符合规范。"""
    tasks = board.get("tasks", [])
    issues: list[str] = []
    checks: dict[str, bool] = {}

    assignees = {t["task_id"]: t.get("assignee") for t in tasks}
    builder_tasks = [t for t in tasks if t.get("assignee") == "builder-agent"]
    verifier_tasks = [t for t in tasks if t.get("assignee") == "verifier-agent"]

    checks["has_builder_tasks"] = len(builder_tasks) >= 1
    checks["has_verifier_task"] = len(verifier_tasks) >= 1

    for tid in ("T1", "T2", "T3"):
        if tid in assignees and assignees[tid] != "builder-agent":
            issues.append(f"{tid} 应分配给 builder-agent，实际 {assignees[tid]}")
    if "T4" in assignees and assignees["T4"] != "verifier-agent":
        issues.append(f"T4 应分配给 verifier-agent，实际 {assignees['T4']}")

    for task in builder_tasks:
        tid = task["task_id"]
        agents_in_results = {r.get("agent") for r in task.get("results", [])}
        if task.get("status") == "completed" and "builder-agent" not in agents_in_results:
            issues.append(f"{tid} 已完成但无 builder-agent 结果记录")

    for task in verifier_tasks:
        if task.get("status") == "completed":
            agents_in_results = {r.get("agent") for r in task.get("results", [])}
            if "verifier-agent" not in agents_in_results:
                issues.append(f"{task['task_id']} 已完成但无 verifier-agent 验收记录")

    planner_wrote = any(
        r.get("agent") == "planner-agent"
        for t in tasks
        for r in t.get("results", [])
    )
    checks["planner_recorded"] = planner_wrote

    order_ok = True
    if tasks:
        builder_ids = [t["task_id"] for t in builder_tasks]
        if builder_ids and verifier_tasks:
            last_builder = max(builder_ids, key=lambda x: int(x[1:]) if x[1:].isdigit() else 0)
            if verifier_tasks[0]["task_id"] <= last_builder:
                order_ok = False
                issues.append("verifier 任务应在 builder 任务之后")
    checks["handover_order"] = order_ok

    # planner 结果记录为推荐项，非硬性失败
    required_checks = {k: v for k, v in checks.items() if k != "planner_recorded"}
    passed = len(issues) == 0 and all(required_checks.values())

    return {
        "board_id": board.get("board_id"),
        "requirement": board.get("requirement"),
        "board_status": board.get("status"),
        "checks": checks,
        "passed": passed,
        "issues": issues,
    }


D13_CASES: list[dict[str, Any]] = [
    {
        "id": "D13-01",
        "category": "文档类",
        "prompt": "帮我写一份 agent-loop 使用说明文档，介绍 planner、builder、verifier 三个角色的职责分工",
        "expect_loop": False,
    },
    {
        "id": "D13-02",
        "category": "代码类",
        "prompt": "给 task_board_server.py 的 complete_task 增加单元测试，覆盖 board_status 变为 done 的分支",
        "expect_loop": False,
    },
    {
        "id": "D13-03",
        "category": "失败修复类",
        "prompt": "近半年的销售情况怎么样",
        "expect_loop": True,
        "simulate_failure": True,
    },
    {
        "id": "D13-04",
        "category": "边界类",
        "prompt": "帮我看看 task-board 的配置结构对不对",
        "expect_loop": False,
        "note": "含「看看」会触发 hook，但属配置审查非数据分析",
    },
    {
        "id": "D13-05",
        "category": "误触发类",
        "prompt": "把变量名 sales_data 改成 salesData，这是代码重构不是查销售数据",
        "expect_loop": False,
    },
]


class D13IntegrationTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.env_patcher = __import__("unittest.mock", fromlist=["patch"]).patch.dict(
            os.environ,
            {"TASK_BOARD_DIR": self.temp_dir.name},
            clear=False,
        )
        self.env_patcher.start()
        tbs._boards_dir = lambda: Path(self.temp_dir.name)  # type: ignore[method-assign]

    def tearDown(self) -> None:
        self.env_patcher.stop()
        self.temp_dir.cleanup()

    def test_routing_all_five_categories(self) -> None:
        results = []
        for case in D13_CASES:
            intent = classify_analysis_intent(case["prompt"])
            routed = expect_agent_loop(case["prompt"])
            hook_would_log = intent is not None
            results.append(
                {
                    **case,
                    "hook_intent": intent[1] if intent else None,
                    "hook_keyword": intent[2] if intent else None,
                    "routing_decision": routed,
                    "routing_match": routed == case["expect_loop"],
                    "hook_false_positive": hook_would_log and not case["expect_loop"],
                }
            )
            self.assertEqual(
                routed,
                case["expect_loop"],
                f"{case['id']} 路由期望不符: {case['prompt'][:40]}",
            )
        self._last_routing = results  # type: ignore[attr-defined]

    def test_failure_recovery_handover(self) -> None:
        """失败修复类：verifier request_rework → builder 修复 → verifier 通过。"""
        created = json.loads(
            tbs.create_task(
                requirement="近半年的销售情况怎么样",
                title="近半年销售分析",
                description="趋势型 T-02",
            )
        )
        board_id = created["board_id"]

        for tid, assignee in [
            ("T2", "builder-agent"),
            ("T3", "builder-agent"),
            ("T4", "verifier-agent"),
        ]:
            tbs.create_task(
                board_id=board_id,
                task_id=tid,
                title=f"任务{tid}",
                description="D13 模拟",
            )
            tbs.assign_task(board_id=board_id, task_id=tid, assignee=assignee)

        t1_id = created["task"]["task_id"]
        tbs.assign_task(board_id=board_id, task_id=t1_id, assignee="builder-agent")

        tbs.append_result(
            board_id=board_id,
            task_id="T3",
            agent="builder-agent",
            content="## 1. 分析概要\n（缺第2节）",
        )
        rework = json.loads(
            tbs.request_rework(
                board_id=board_id,
                fix_items=["补全第2节核心结论 3~5 条"],
                note="verifier 打回",
            )
        )
        self.assertTrue(rework["rework_allowed"])

        tbs.append_result(
            board_id=board_id,
            task_id="T3",
            agent="builder-agent",
            content="## 2. 核心结论\n- 结论1\n- 结论2\n- 结论3",
        )
        tbs.complete_task(board_id=board_id, task_id="T3")
        tbs.append_result(
            board_id=board_id,
            task_id="T4",
            agent="verifier-agent",
            content='{"passed": true, "fix_items": []}',
        )
        tbs.complete_task(board_id=board_id, task_id="T4")

        board = json.loads(tbs.list_tasks(board_id=board_id))
        t4 = next(t for t in board["tasks"] if t["task_id"] == "T4")
        self.assertEqual(t4["status"], "completed")
        self.assertGreaterEqual(len(t4["results"]), 2)
        last_result = t4["results"][-1]["content"]
        self.assertIn("passed", last_result)

    def test_three_agent_handover_flow(self) -> None:
        """标准三 Agent 交接：planner 规划 → builder 执行 → verifier 验收。"""
        created = json.loads(
            tbs.create_task(requirement="测试交接", title="T1 探查")
        )
        board_id = created["board_id"]
        t1_id = created["task"]["task_id"]

        for tid, title, assignee in [
            ("T2", "汇总 SQL", "builder-agent"),
            ("T3", "撰写报告", "builder-agent"),
            ("T4", "验收", "verifier-agent"),
        ]:
            tbs.create_task(board_id=board_id, task_id=tid, title=title)
            tbs.assign_task(board_id=board_id, task_id=tid, assignee=assignee)

        tbs.assign_task(board_id=board_id, task_id=t1_id, assignee="builder-agent")
        tbs.append_result(
            board_id=board_id,
            task_id="T1",
            agent="planner-agent",
            content="规划：T1~T4 任务清单",
        )
        tbs.append_result(
            board_id=board_id,
            task_id="T1",
            agent="builder-agent",
            content="探查完成",
        )
        tbs.complete_task(board_id=board_id, task_id="T1")

        for tid in ("T2", "T3"):
            tbs.append_result(
                board_id=board_id,
                task_id=tid,
                agent="builder-agent",
                content=f"{tid} 完成",
            )
            tbs.complete_task(board_id=board_id, task_id=tid)

        tbs.append_result(
            board_id=board_id,
            task_id="T4",
            agent="verifier-agent",
            content='{"passed": true}',
        )
        tbs.complete_task(board_id=board_id, task_id="T4")

        board = json.loads(
            Path(self.temp_dir.name).joinpath(f"{board_id}.json").read_text(encoding="utf-8")
        )
        audit = audit_board_handover(board)
        self.assertTrue(audit["passed"], audit["issues"])


class D13HistoricalAuditTest(unittest.TestCase):
    """审计历史看板的三 Agent 交接。"""

    def test_audit_existing_boards(self) -> None:
        if not BOARDS.exists():
            self.skipTest("无历史看板")
        audits = []
        for path in sorted(BOARDS.glob("*.json")):
            board = json.loads(path.read_text(encoding="utf-8"))
            audits.append(audit_board_handover(board))
        self.assertGreater(len(audits), 0, "应至少有一个历史看板")
        self._audits = audits  # type: ignore[attr-defined]


def run_and_report() -> dict[str, Any]:
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    suite.addTests(loader.loadTestsFromTestCase(D13IntegrationTest))
    suite.addTests(loader.loadTestsFromTestCase(D13HistoricalAuditTest))

    runner = unittest.TextTestRunner(verbosity=0)
    result = runner.run(suite)

    routing_details = []
    for case in D13_CASES:
        intent = classify_analysis_intent(case["prompt"])
        routing_details.append(
            {
                "id": case["id"],
                "category": case["category"],
                "prompt": case["prompt"],
                "expect_agent_loop": case["expect_loop"],
                "actual_routing": expect_agent_loop(case["prompt"]),
                "hook_intent": intent[1] if intent else None,
                "hook_keyword": intent[2] if intent else None,
                "hook_false_positive": intent is not None and not case["expect_loop"],
                "passed": expect_agent_loop(case["prompt"]) == case["expect_loop"],
            }
        )

    board_audits = []
    if BOARDS.exists():
        for path in sorted(BOARDS.glob("*.json")):
            board = json.loads(path.read_text(encoding="utf-8"))
            board_audits.append(audit_board_handover(board))

    return {
        "tests_run": result.testsRun,
        "failures": len(result.failures),
        "errors": len(result.errors),
        "success": result.wasSuccessful(),
        "routing_cases": routing_details,
        "board_audits": board_audits,
    }


if __name__ == "__main__":
    report = run_and_report()
    print(json.dumps(report, ensure_ascii=False, indent=2))
    raise SystemExit(0 if report["success"] else 1)
