"""task-board MCP 单元测试。"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src" / "mcp"))

import task_board_server as tbs  # noqa: E402


class TaskBoardServerTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.env_patcher = patch.dict(
            os.environ,
            {"TASK_BOARD_DIR": self.temp_dir.name},
            clear=False,
        )
        self.env_patcher.start()
        tbs._boards_dir = lambda: Path(self.temp_dir.name)  # type: ignore[method-assign]

    def tearDown(self) -> None:
        self.env_patcher.stop()
        self.temp_dir.cleanup()

    def test_create_assign_append_complete_flow(self) -> None:
        created = json.loads(
            tbs.create_task(
                title="实现登录接口",
                description="提供 POST /login",
                acceptance_criteria=["返回 JWT", "密码错误返回 401"],
                requirement="用户认证模块",
            )
        )
        board_id = created["board_id"]
        task_id = created["task"]["task_id"]

        assigned = json.loads(
            tbs.assign_task(board_id=board_id, task_id=task_id, assignee="builder-agent")
        )
        self.assertEqual(assigned["assignee"], "builder-agent")

        appended = json.loads(
            tbs.append_result(
                board_id=board_id,
                task_id=task_id,
                agent="builder-agent",
                content="已新增 src/auth/login.py",
            )
        )
        self.assertEqual(appended["status"], "in_progress")

        completed = json.loads(tbs.complete_task(board_id=board_id, task_id=task_id))
        self.assertEqual(completed["remaining_tasks"], 0)
        self.assertEqual(completed["board_status"], "done")

        listed = json.loads(tbs.list_tasks(board_id=board_id))
        self.assertEqual(listed["count"], 1)
        self.assertEqual(listed["tasks"][0]["status"], "completed")

    def test_list_all_boards(self) -> None:
        tbs.create_task(title="任务A")
        tbs.create_task(title="任务B")
        summary = json.loads(tbs.list_tasks())
        self.assertEqual(summary["count"], 2)

    def test_request_rework_flow(self) -> None:
        created = json.loads(
            tbs.create_task(
                title="分析报告",
                requirement="销售趋势",
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
            )
            tbs.assign_task(board_id=board_id, task_id=tid, assignee=assignee)

        tbs.append_result(
            board_id=board_id,
            task_id="T3",
            agent="builder-agent",
            content="缺第2节",
        )
        tbs.complete_task(board_id=board_id, task_id="T3")

        rework = json.loads(
            tbs.request_rework(
                board_id=board_id,
                fix_items=["补全第2节核心结论 3~5 条"],
                note="结构不完整",
            )
        )
        self.assertTrue(rework["rework_allowed"])
        self.assertEqual(rework["rework_round"], 1)

        listed = json.loads(tbs.list_tasks(board_id=board_id))
        self.assertEqual(listed["rework_rounds"], 1)
        self.assertIsNotNone(listed["latest_rework"])
        t3 = next(t for t in listed["tasks"] if t["task_id"] == "T3")
        self.assertEqual(t3["status"], "in_progress")

        rework2 = json.loads(
            tbs.request_rework(
                board_id=board_id,
                fix_items=["仍缺指标"],
            )
        )
        self.assertTrue(rework2["rework_allowed"])
        self.assertEqual(rework2["rework_round"], 2)

        blocked = json.loads(
            tbs.request_rework(
                board_id=board_id,
                fix_items=["第三次打回"],
            )
        )
        self.assertFalse(blocked["rework_allowed"])
        self.assertEqual(blocked["rework_round"], 3)


if __name__ == "__main__":
    unittest.main()
