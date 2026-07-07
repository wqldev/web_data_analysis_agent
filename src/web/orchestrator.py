"""Web 端 agent-loop 编排器：planner → builder → verifier。"""

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
from core import sqlite_client  # noqa: E402
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


def _fmt_num(value: Any) -> str:
    if value is None:
        return "-"
    try:
        num = float(value)
        if abs(num) >= 1000:
            return f"{num:,.2f}"
        return f"{num:.2f}"
    except (TypeError, ValueError):
        return str(value)


def _pct_change(current: float, previous: float) -> str:
    if previous == 0:
        return "N/A"
    change = (current - previous) / previous * 100
    sign = "+" if change >= 0 else ""
    return f"{sign}{change:.1f}%"


class AgentLoopOrchestrator:
    def __init__(self, on_progress: Callable[[str, str, dict[str, Any]], None] | None = None):
        self.on_progress = on_progress or (lambda *_: None)

    def _emit(self, board_id: str, phase: str, detail: str = "", extra: dict | None = None):
        self.on_progress(phase, detail, {"board_id": board_id, **(extra or {})})

    def run(self, requirement: str, board_id: str | None = None) -> dict[str, Any]:
        analysis_type, type_label = classify_intent(requirement)

        self._emit("", "planning", "planner-agent 正在拆解任务…")
        plan = self._run_planner(requirement, analysis_type, type_label, board_id)
        board_id = plan["board_id"]

        self._emit(board_id, "building", "builder-agent 正在探库取数…")
        build_result = self._run_builder(board_id, requirement, analysis_type, type_label, plan)

        self._emit(board_id, "verifying", "verifier-agent 正在验收…")
        verify_result = self._run_verifier(board_id, build_result["report"])

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

        tasks_spec = [
            {
                "task_id": "T1",
                "title": "确认数据源与字段",
                "description": "list_tables，选定目标表，确认日期、金额、去重字段",
                "acceptance_criteria": [
                    "明确写出目标表名",
                    "明确时间范围口径",
                    "明确金额字段与订单去重字段",
                ],
                "assignee": "builder-agent",
            },
            {
                "task_id": "T2",
                "title": "执行汇总 SQL",
                "description": f"按 {type_label} 编写只读 SQL，产出第 3、4 节所需数据",
                "acceptance_criteria": [
                    "SQL 仅只读（SELECT），时间范围与 T1 口径一致",
                    "产出关键指标（第 3 节）所需汇总结果",
                    "产出详细分析（第 4 节）所需至少 1 张维度/趋势表",
                ],
                "assignee": "builder-agent",
            },
            {
                "task_id": "T3",
                "title": "撰写分析报告",
                "description": "严格按 report-template.md 六节撰写中文报告",
                "acceptance_criteria": [
                    "第 1 节 分析概要：含用户问题、分析类型、时间口径、数据来源",
                    "第 2 节 核心结论：3~5 条 bullet",
                    "第 3 节 关键指标：至少 3 项 KPI 表格",
                    "第 4 节 详细分析：至少 1 张表 + 解读",
                    "第 5 节 业务建议：2~4 条可执行建议",
                    "第 6 节 数据说明与局限：含时间范围、口径、外推限制",
                ],
                "assignee": "builder-agent",
            },
            {
                "task_id": "T4",
                "title": "验收分析交付物",
                "acceptance_criteria": [
                    "对照 T1~T3 acceptance_criteria 逐项核对",
                    "对照 report-template.md 六节完整性",
                ],
                "assignee": "verifier-agent",
            },
        ]

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
        tables = sqlite_client.list_tables()
        t1_content = self._build_t1(tables, analysis_type)
        board.append_result(board_id, "T1", "builder-agent", t1_content, set_status="completed")
        board.complete_task(board_id, "T1")

        t2_data, t2_content = self._build_t2(analysis_type, tables)
        board.append_result(board_id, "T2", "builder-agent", t2_content, set_status="completed")
        board.complete_task(board_id, "T2")

        report = self._build_t3(requirement, type_label, analysis_type, t1_content, t2_data)
        board.append_result(board_id, "T3", "builder-agent", report, set_status="completed")
        board.complete_task(board_id, "T3")

        return {"report": report, "t2_data": t2_data}

    def _build_t1(self, tables: list[str], analysis_type: AnalysisType) -> str:
        schema_notes = []
        for table in tables[:6]:
            try:
                cols = sqlite_client.describe_table(table)
                col_names = [c["Field"] for c in cols]
                schema_notes.append(f"- `{table}`: {', '.join(col_names[:8])}{'…' if len(col_names) > 8 else ''}")
            except Exception:
                schema_notes.append(f"- `{table}`: （结构读取失败）")

        has_orders = "orders" in tables
        has_items = "order_items" in tables
        has_products = "products" in tables
        has_customers = "customers" in tables

        if analysis_type == "segment" and has_customers and has_orders:
            target = "`customers` ⋈ `orders`" + (" ⋈ `order_items`" if has_items else "")
            date_field = "orders.order_date"
            amount_expr = (
                "SUM(order_items.quantity * order_items.unit_price * (1 - order_items.discount))"
                if has_items
                else "COUNT(DISTINCT orders.order_id)"
            )
            order_key = "COUNT(DISTINCT orders.order_id)"
            time_note = "以库内最晚订单日为基准，计算客户末单间隔（Recency）与近 3 月活跃度"
        elif has_orders and has_items:
            target = "`orders` ⋈ `order_items`" + (" ⋈ `products`" if has_products else "")
            date_field = "orders.order_date"
            amount_expr = "SUM(order_items.quantity * order_items.unit_price * (1 - order_items.discount))"
            order_key = "COUNT(DISTINCT orders.order_id)"
            time_note = "以库内最晚订单日回溯最近 6 个月"
        else:
            target = f"`{tables[0]}`" if tables else "（无可用表）"
            date_field = "（待确认）"
            amount_expr = "SUM(amount)"
            order_key = "COUNT(*)"
            time_note = "待探库确认"

        return (
            f"【T1 数据源与字段确认】\n\n"
            f"**探库结果**：共 {len(tables)} 张表\n"
            + "\n".join(schema_notes)
            + f"\n\n**目标表**：{target}\n"
            f"**时间范围口径**：{time_note}\n"
            f"**日期字段**：{date_field}\n"
            f"**金额/价值计算**：{amount_expr}\n"
            f"**订单去重**：{order_key}\n"
            f"**分析类型**：{analysis_type}"
        )

    def _get_date_range(self) -> tuple[str, str]:
        rows = sqlite_client.execute_query(
            "SELECT MIN(order_date) AS min_date, MAX(order_date) AS max_date "
            "FROM orders WHERE order_status = 'Completed'"
        )
        if not rows or not rows[0].get("max_date"):
            today = datetime.now().strftime("%Y-%m-%d")
            return today, today
        max_date = str(rows[0]["max_date"])[:10]
        # 用 Python 计算 6 个月前（替代 MySQL DATE_SUB + DATE_FORMAT）
        dt = datetime.strptime(max_date, "%Y-%m-%d")
        month = dt.month - 6
        year = dt.year
        if month <= 0:
            month += 12
            year -= 1
        start_date = datetime(year, month, dt.day).strftime("%Y-%m-%d")
        return start_date, max_date

    def _build_t2(self, analysis_type: AnalysisType, tables: list[str]) -> tuple[dict[str, Any], str]:
        if "orders" not in tables:
            return {"error": "缺少 orders 表", "analysis_type": analysis_type}, "【T2】数据库缺少订单表。"

        builders = {
            "segment": self._build_t2_segment,
            "attribution": self._build_t2_attribution,
            "compare": self._build_t2_compare,
            "hypothesis": self._build_t2_hypothesis,
        }
        builder = builders.get(analysis_type, self._build_t2_trend)
        return builder(tables)

    def _build_t2_trend(self, tables: list[str]) -> tuple[dict[str, Any], str]:
        if "order_items" not in tables:
            return {"error": "缺少 order_items 表", "analysis_type": "trend"}, "【T2】缺少 order_items 表。"

        start_date, end_date = self._get_date_range()
        base_filter = (
            f"o.order_date >= '{start_date}' AND o.order_date <= '{end_date}' "
            "AND o.order_status = 'Completed'"
        )

        kpi_sql = f"""
        SELECT
          COUNT(DISTINCT o.order_id) AS order_count,
          COALESCE(SUM(oi.quantity * oi.unit_price * (1 - oi.discount)), 0) AS total_sales,
          COALESCE(SUM(oi.quantity), 0) AS total_qty
        FROM orders o
        JOIN order_items oi ON o.order_id = oi.order_id
        WHERE {base_filter}
        """
        kpi_rows = sqlite_client.execute_query(kpi_sql)
        kpi = kpi_rows[0] if kpi_rows else {}

        detail_sql = f"""
        SELECT strftime('%Y-%m', o.order_date) AS month,
          COUNT(DISTINCT o.order_id) AS order_count,
          COALESCE(SUM(oi.quantity * oi.unit_price * (1 - oi.discount)), 0) AS sales_amt
        FROM orders o
        JOIN order_items oi ON o.order_id = oi.order_id
        WHERE {base_filter}
        GROUP BY strftime('%Y-%m', o.order_date)
        ORDER BY month
        """
        detail_rows = sqlite_client.execute_query(detail_sql)
        detail_label = "月度趋势"

        # 用 Python 计算去年同期
        dt = datetime.strptime(start_date, "%Y-%m-%d")
        month = dt.month - 6
        year = dt.year
        if month <= 0:
            month += 12
            year -= 1
        try:
            prev_start = datetime(year, month, dt.day).strftime("%Y-%m-%d")
        except ValueError:
            prev_start = datetime(year, month, 1).strftime("%Y-%m-%d")
        prev_sql = f"""
        SELECT COALESCE(SUM(oi.quantity * oi.unit_price * (1 - oi.discount)), 0) AS prev_sales,
          COUNT(DISTINCT o.order_id) AS prev_orders
        FROM orders o
        JOIN order_items oi ON o.order_id = oi.order_id
        WHERE o.order_date >= '{prev_start}' AND o.order_date < '{start_date}'
          AND o.order_status = 'Completed'
        """
        prev_rows = sqlite_client.execute_query(prev_sql)
        prev = prev_rows[0] if prev_rows else {"prev_sales": 0, "prev_orders": 0}

        data = {
            "start_date": start_date,
            "end_date": end_date,
            "kpi": kpi,
            "detail_rows": detail_rows,
            "detail_label": detail_label,
            "prev": prev,
            "analysis_type": "trend",
        }

        detail_lines = [
            f"| {row['month']} | {_fmt_num(row.get('order_count'))} | {_fmt_num(row.get('sales_amt'))} |"
            for row in detail_rows[:12]
        ]
        detail_table = "| 月份 | 订单数 | 销售额 |\n|------|--------|--------|\n"
        detail_table += "\n".join(detail_lines) if detail_lines else "| （无数据） | - | - |"

        content = (
            f"【T2 汇总 SQL 结果】\n\n"
            f"**时间范围**：{start_date} ~ {end_date}\n"
            f"**总销售额**：{_fmt_num(kpi.get('total_sales'))} 元\n"
            f"**总订单数**：{_fmt_num(kpi.get('order_count'))} 笔\n"
            f"**环比变化**：{_pct_change(float(kpi.get('total_sales') or 0), float(prev.get('prev_sales') or 0))}\n\n"
            f"**{detail_label}表**：\n{detail_table}"
        )
        return data, content

    def _build_t2_compare(self, tables: list[str]) -> tuple[dict[str, Any], str]:
        if "order_items" not in tables or "products" not in tables:
            return self._build_t2_trend(tables)

        start_date, end_date = self._get_date_range()
        base_filter = (
            f"o.order_date >= '{start_date}' AND o.order_date <= '{end_date}' "
            "AND o.order_status = 'Completed'"
        )

        kpi_sql = f"""
        SELECT COUNT(DISTINCT o.order_id) AS order_count,
          COALESCE(SUM(oi.quantity * oi.unit_price * (1 - oi.discount)), 0) AS total_sales
        FROM orders o JOIN order_items oi ON o.order_id = oi.order_id
        WHERE {base_filter}
        """
        kpi = sqlite_client.execute_query(kpi_sql)[0]

        detail_sql = f"""
        SELECT p.category,
          COUNT(DISTINCT o.order_id) AS order_count,
          COALESCE(SUM(oi.quantity * oi.unit_price * (1 - oi.discount)), 0) AS sales_amt,
          COALESCE(SUM(oi.quantity), 0) AS total_qty
        FROM orders o
        JOIN order_items oi ON o.order_id = oi.order_id
        JOIN products p ON oi.product_id = p.product_id
        WHERE {base_filter}
        GROUP BY p.category
        ORDER BY sales_amt DESC
        """
        detail_rows = sqlite_client.execute_query(detail_sql)

        data = {
            "start_date": start_date,
            "end_date": end_date,
            "kpi": kpi,
            "detail_rows": detail_rows,
            "detail_label": "品类对比",
            "prev": {},
            "analysis_type": "compare",
        }
        detail_table = "| 品类 | 订单数 | 销售额 | 销量 |\n|------|--------|--------|------|\n"
        detail_table += "\n".join(
            f"| {r['category']} | {r.get('order_count')} | {_fmt_num(r.get('sales_amt'))} | {r.get('total_qty')} |"
            for r in detail_rows
        )
        content = f"【T2 对比汇总】\n\n**时间范围**：{start_date} ~ {end_date}\n\n{detail_table}"
        return data, content

    def _build_t2_segment(self, tables: list[str]) -> tuple[dict[str, Any], str]:
        if "customers" not in tables:
            return {"error": "缺少 customers 表", "analysis_type": "segment"}, "【T2】缺少 customers 表，无法做客户分群/流失分析。"

        has_items = "order_items" in tables
        ltv_expr = (
            "COALESCE(SUM(oi.quantity * oi.unit_price * (1 - oi.discount)), 0)"
            if has_items
            else "0"
        )
        join_items = "LEFT JOIN order_items oi ON o.order_id = oi.order_id" if has_items else ""

        churn_sql = f"""
        WITH ref AS (
          SELECT MAX(order_date) AS max_dt FROM orders WHERE order_status = 'Completed'
        ),
        cust AS (
          SELECT c.customer_id, c.customer_name, c.region, c.industry,
            COUNT(DISTINCT o.order_id) AS total_orders,
            MAX(o.order_date) AS last_order_date,
            CAST(julianday(r.max_dt) - julianday(MAX(o.order_date)) AS INTEGER) AS days_since_last,
            {ltv_expr} AS lifetime_value,
            SUM(CASE WHEN o.order_date >= date(r.max_dt, '-3 months') THEN 1 ELSE 0 END) AS orders_last_3m
          FROM customers c
          CROSS JOIN ref r
          LEFT JOIN orders o ON c.customer_id = o.customer_id AND o.order_status = 'Completed'
          {join_items}
          GROUP BY c.customer_id, c.customer_name, c.region, c.industry, r.max_dt
        )
        SELECT customer_id, customer_name, region, industry,
          total_orders, last_order_date, days_since_last,
          ROUND(lifetime_value, 2) AS lifetime_value, orders_last_3m,
          CASE
            WHEN total_orders = 0 THEN '从未下单'
            WHEN days_since_last >= 90 AND orders_last_3m = 0 THEN '高流失风险'
            WHEN days_since_last >= 60 THEN '中流失风险'
            ELSE '活跃'
          END AS churn_risk
        FROM cust
        ORDER BY
          CASE churn_risk WHEN '高流失风险' THEN 1 WHEN '中流失风险' THEN 2 WHEN '从未下单' THEN 3 ELSE 4 END,
          days_since_last DESC
        """
        customer_rows = sqlite_client.execute_query(churn_sql)

        region_sql = f"""
        WITH ref AS (SELECT MAX(order_date) AS max_dt FROM orders WHERE order_status = 'Completed'),
        cust AS (
          SELECT c.region,
            COUNT(*) AS customer_count,
            SUM(CASE WHEN COALESCE(CAST(julianday(r.max_dt) - julianday(MAX(o.order_date)) AS INTEGER), 999) >= 90
              AND SUM(CASE WHEN o.order_date >= date(r.max_dt, '-3 months') THEN 1 ELSE 0 END) = 0
              AND COUNT(DISTINCT o.order_id) > 0 THEN 1 ELSE 0 END) AS high_risk_count
          FROM customers c
          CROSS JOIN ref r
          LEFT JOIN orders o ON c.customer_id = o.customer_id AND o.order_status = 'Completed'
          GROUP BY c.customer_id, c.region, r.max_dt
        )
        SELECT region, COUNT(*) AS customers, SUM(high_risk_count) AS high_risk
        FROM cust GROUP BY region ORDER BY high_risk DESC
        """
        try:
            region_rows = sqlite_client.execute_query(region_sql)
        except Exception:
            region_rows = []

        ref_rows = sqlite_client.execute_query(
            "SELECT MAX(order_date) AS max_dt, MIN(order_date) AS min_dt "
            "FROM orders WHERE order_status = 'Completed'"
        )
        ref = ref_rows[0] if ref_rows else {}
        max_dt = str(ref.get("max_dt") or "")[:10]

        risk_counts: dict[str, int] = {}
        for row in customer_rows:
            risk = row.get("churn_risk") or "未知"
            risk_counts[risk] = risk_counts.get(risk, 0) + 1

        high_risk = [r for r in customer_rows if r.get("churn_risk") == "高流失风险"][:10]
        medium_risk = [r for r in customer_rows if r.get("churn_risk") == "中流失风险"][:5]

        data = {
            "analysis_type": "segment",
            "ref_date": max_dt,
            "risk_counts": risk_counts,
            "customer_rows": customer_rows,
            "high_risk_rows": high_risk,
            "medium_risk_rows": medium_risk,
            "region_rows": region_rows,
            "total_customers": len(customer_rows),
        }

        cust_table = "| 客户 | 区域 | 行业 | 历史订单 | 末单间隔(天) | 生命周期价值 | 风险等级 |\n"
        cust_table += "|------|------|------|----------|--------------|--------------|----------|\n"
        for r in (high_risk + medium_risk)[:12]:
            cust_table += (
                f"| {r.get('customer_name')} | {r.get('region')} | {r.get('industry')} | "
                f"{r.get('total_orders')} | {r.get('days_since_last') or '-'} | "
                f"{_fmt_num(r.get('lifetime_value'))} | {r.get('churn_risk')} |\n"
            )

        content = (
            f"【T2 客户流失风险分析】\n\n"
            f"**基准日**：{max_dt}（库内最晚完成订单日）\n"
            f"**客户总数**：{len(customer_rows)}\n"
            f"**高流失风险**：{risk_counts.get('高流失风险', 0)} 人（≥90 天未下单且近 3 月无订单）\n"
            f"**中流失风险**：{risk_counts.get('中流失风险', 0)} 人（≥60 天未下单）\n"
            f"**活跃客户**：{risk_counts.get('活跃', 0)} 人\n\n"
            f"**高风险/中风险客户清单**：\n{cust_table}"
        )
        return data, content

    def _build_t2_attribution(self, tables: list[str]) -> tuple[dict[str, Any], str]:
        if "order_items" not in tables:
            return self._build_t2_trend(tables)

        start_date, end_date = self._get_date_range()
        dt = datetime.strptime(start_date, "%Y-%m-%d")
        prev_months = 6
        prev_month = dt.month - prev_months
        prev_year = dt.year
        if prev_month <= 0:
            prev_month += 12
            prev_year -= 1
        try:
            prev_start = datetime(prev_year, prev_month, dt.day).strftime("%Y-%m-%d")
        except ValueError:
            prev_start = datetime(prev_year, prev_month, 1).strftime("%Y-%m-%d")

        period_sql = f"""
        SELECT
          SUM(CASE WHEN o.order_date >= '{start_date}' THEN oi.quantity * oi.unit_price * (1 - oi.discount) ELSE 0 END) AS curr_sales,
          SUM(CASE WHEN o.order_date >= '{prev_start}' AND o.order_date < '{start_date}' THEN oi.quantity * oi.unit_price * (1 - oi.discount) ELSE 0 END) AS prev_sales
        FROM orders o JOIN order_items oi ON o.order_id = oi.order_id
        WHERE o.order_status = 'Completed'
          AND o.order_date >= '{prev_start}' AND o.order_date <= '{end_date}'
        """
        period = sqlite_client.execute_query(period_sql)[0]

        dim_sql = "p.category"
        join_products = ""
        if "products" in tables:
            join_products = "JOIN products p ON oi.product_id = p.product_id"
        elif "customers" in tables:
            dim_sql = "c.region"
            join_products = "JOIN customers c ON o.customer_id = c.customer_id"
        else:
            dim_sql = "'整体'"

        contrib_sql = f"""
        SELECT {dim_sql} AS dimension,
          COALESCE(SUM(CASE WHEN o.order_date >= '{start_date}' THEN oi.quantity * oi.unit_price * (1 - oi.discount) ELSE 0 END), 0) AS curr_sales,
          COALESCE(SUM(CASE WHEN o.order_date >= '{prev_start}' AND o.order_date < '{start_date}' THEN oi.quantity * oi.unit_price * (1 - oi.discount) ELSE 0 END), 0) AS prev_sales
        FROM orders o
        JOIN order_items oi ON o.order_id = oi.order_id
        {join_products}
        WHERE o.order_status = 'Completed'
          AND o.order_date >= '{prev_start}' AND o.order_date <= '{end_date}'
        GROUP BY {dim_sql}
        ORDER BY (curr_sales - prev_sales) ASC
        """
        detail_rows = sqlite_client.execute_query(contrib_sql)
        for row in detail_rows:
            row["delta"] = float(row.get("curr_sales") or 0) - float(row.get("prev_sales") or 0)

        data = {
            "analysis_type": "attribution",
            "start_date": start_date,
            "end_date": end_date,
            "prev_start": prev_start,
            "period": period,
            "detail_rows": detail_rows,
            "detail_label": "维度贡献",
        }

        detail_table = "| 维度 | 近6月销售额 | 前6月销售额 | 变化额 |\n|------|------------|------------|--------|\n"
        detail_table += "\n".join(
            f"| {r.get('dimension')} | {_fmt_num(r.get('curr_sales'))} | {_fmt_num(r.get('prev_sales'))} | {_fmt_num(r.get('delta'))} |"
            for r in detail_rows[:12]
        )
        content = (
            f"【T2 归因拆解】\n\n"
            f"**近6月**：{start_date} ~ {end_date}\n"
            f"**前6月**：{prev_start} ~ {start_date}\n"
            f"**整体变化**：{_fmt_num(period.get('curr_sales'))} vs {_fmt_num(period.get('prev_sales'))} "
            f"（{_pct_change(float(period.get('curr_sales') or 0), float(period.get('prev_sales') or 0))}）\n\n"
            f"{detail_table}"
        )
        return data, content

    def _build_t2_hypothesis(self, tables: list[str]) -> tuple[dict[str, Any], str]:
        data, content = self._build_t2_trend(tables)
        data["analysis_type"] = "hypothesis"
        data["hypothesis_note"] = "假设型分析需结合具体场景参数，当前输出基准趋势供参考。"
        content = "【T2 假设分析基准数据】\n\n" + content + "\n\n*完整假设测算需明确调价/活动幅度等参数。*"
        return data, content

    def _build_t3(
        self,
        requirement: str,
        type_label: str,
        analysis_type: AnalysisType,
        t1_content: str,
        t2_data: dict[str, Any],
    ) -> str:
        if t2_data.get("error"):
            return (
                "## 1. 分析概要\n\n"
                f"- **用户问题**：{requirement}\n"
                f"- **分析类型**：{type_label}\n"
                "- **状态**：数据探查失败，缺少必要表结构\n\n"
                "## 2. 核心结论\n\n"
                f"- 当前数据库缺少必要表，无法完成{type_label}分析。\n\n"
                "## 3. 关键指标\n\n| 指标 | 数值 | 说明 |\n|------|------|------|\n| - | - | 无数据 |\n\n"
                "## 4. 详细分析\n\n无可用数据。\n\n"
                "## 5. 业务建议\n\n1. 请管理员检查 MySQL 连接与数据库表结构。\n\n"
                "## 6. 数据说明与局限\n\n数据库结构不满足分析前提。"
            )

        report_type = t2_data.get("analysis_type", analysis_type)
        if report_type == "segment":
            return self._build_t3_segment(requirement, type_label, t2_data)
        if report_type == "attribution":
            return self._build_t3_attribution(requirement, type_label, t2_data)
        if report_type == "compare":
            return self._build_t3_compare(requirement, type_label, t2_data)
        return self._build_t3_trend(requirement, type_label, t2_data)

    def _build_t3_segment(self, requirement: str, type_label: str, t2_data: dict[str, Any]) -> str:
        risk_counts = t2_data.get("risk_counts", {})
        high_risk = t2_data.get("high_risk_rows", [])
        medium_risk = t2_data.get("medium_risk_rows", [])
        ref_date = t2_data.get("ref_date", "")
        total = t2_data.get("total_customers", 0)
        high_n = risk_counts.get("高流失风险", 0)
        med_n = risk_counts.get("中流失风险", 0)
        active_n = risk_counts.get("活跃", 0)

        top_names = [r.get("customer_name") for r in high_risk[:5] if r.get("customer_name")]
        top_list = "、".join(top_names) if top_names else "（暂无）"

        conclusions = [
            f"共 **{total}** 名客户中，**{high_n}** 人处于高流失风险（≥90 天未下单且近 3 月无订单），占比 **{high_n/total*100:.1f}%**。" if total else "客户样本为空。",
            f"**{med_n}** 人为中流失风险（≥60 天未下单），需纳入重点关怀名单。",
            f"最容易流失的客户包括：**{top_list}**（按末单间隔与近 3 月活跃度综合判定）。",
        ]
        if high_risk:
            avg_gap = sum(int(r.get("days_since_last") or 0) for r in high_risk) / len(high_risk)
            conclusions.append(
                f"高风险客户平均末单间隔 **{avg_gap:.0f}** 天，显著高于活跃客户。"
            )
        while len(conclusions) < 3:
            conclusions.append("建议结合行业属性与历史客单价制定差异化挽留策略。")

        detail_section = "### 4.1 高/中流失风险客户清单\n\n"
        detail_section += "| 客户 | 区域 | 行业 | 历史订单 | 末单间隔(天) | 生命周期价值(元) | 风险等级 |\n"
        detail_section += "|------|------|------|----------|--------------|------------------|----------|\n"
        for r in (high_risk + medium_risk)[:12]:
            detail_section += (
                f"| {r.get('customer_name')} | {r.get('region')} | {r.get('industry')} | "
                f"{r.get('total_orders')} | {r.get('days_since_last') or '-'} | "
                f"{_fmt_num(r.get('lifetime_value'))} | {r.get('churn_risk')} |\n"
            )
        detail_section += (
            "\n**解读**：末单间隔长且近 3 月零订单的客户，复购概率最低；"
            "生命周期价值高者流失对 GMV 伤害更大，应优先挽回。"
        )

        region_rows = t2_data.get("region_rows") or []
        if region_rows:
            detail_section += "\n\n### 4.2 区域风险分布\n\n| 区域 | 客户数 | 高风险人数 |\n|------|--------|------------|\n"
            for r in region_rows[:8]:
                detail_section += f"| {r.get('region')} | {r.get('customers')} | {r.get('high_risk')} |\n"

        suggestions = [
            f"对 {top_list} 等高风险客户启动 1v1 回访，了解未续购原因并提供专属优惠。",
            "建立「末单间隔 >60 天」自动预警，触发关怀短信或销售跟进任务。",
            "对高生命周期价值但高风险的 VIP 客户，安排客户经理专项挽留。",
            "按区域/行业聚类分析流失共性，优化对应产品线或渠道策略。",
        ]

        bullets = "\n".join(f"- {c}" for c in conclusions[:5])
        sugg = "\n".join(f"{i+1}. {s}" for i, s in enumerate(suggestions[:4]))

        kpi_rows = (
            f"| 客户总数 | {total} 人 | customers 表全量 |\n"
            f"| 高流失风险 | {high_n} 人 | ≥90 天未下单且近 3 月无订单 |\n"
            f"| 中流失风险 | {med_n} 人 | ≥60 天未下单 |\n"
            f"| 活跃客户 | {active_n} 人 | 近 60 天内有订单 |\n"
        )
        if total:
            kpi_rows += f"| 高风险占比 | {high_n/total*100:.1f}% | 高流失/总客户 |\n"
        kpi_rows += f"| 从未下单 | {risk_counts.get('从未下单', 0)} 人 | 注册但无 Completed 订单 |\n"

        return (
            f"## 1. 分析概要\n\n"
            f"- **用户问题**：{requirement}\n"
            f"- **分析类型**：{type_label}（客户流失风险分群）\n"
            f"- **时间口径**：以 **{ref_date}** 为基准日，Recency=末单距今天数；近 3 月=基准日前 90 天\n"
            f"- **数据来源**：`customers` ⋈ `orders` ⋈ `order_items`；仅 Completed 订单\n\n"
            f"## 2. 核心结论\n\n{bullets}\n\n"
            f"## 3. 关键指标\n\n"
            f"| 指标 | 数值 | 说明 |\n|------|------|------|\n"
            f"{kpi_rows}\n"
            f"## 4. 详细分析\n\n{detail_section}\n\n"
            f"## 5. 业务建议\n\n{sugg}\n\n"
            f"## 6. 数据说明与局限\n\n"
            f"- **流失定义**：基于 Recency（末单间隔）+ 近 3 月订单数，非真实 churn 标签。\n"
            f"- **基准日**：{ref_date}；不含进行中的 Pending/Cancelled 订单。\n"
            f"- **局限**：样本 {total} 人，未纳入客服工单/满意度等外源信号；"
            f"行业差异大时阈值（60/90 天）需按业务调整。"
        )

    def _build_t3_attribution(self, requirement: str, type_label: str, t2_data: dict[str, Any]) -> str:
        period = t2_data.get("period", {})
        detail_rows = t2_data.get("detail_rows", [])
        start_date = t2_data.get("start_date", "")
        end_date = t2_data.get("end_date", "")
        prev_start = t2_data.get("prev_start", "")
        curr = float(period.get("curr_sales") or 0)
        prev = float(period.get("prev_sales") or 0)
        change = _pct_change(curr, prev)

        worst = detail_rows[0] if detail_rows else {}
        best = detail_rows[-1] if detail_rows else {}

        conclusions = [
            f"近 6 月（{start_date}~{end_date}）销售额 **{_fmt_num(curr)}** 元，"
            f"较前 6 月 **{change}**（{_fmt_num(prev)} → {_fmt_num(curr)}）。",
        ]
        if worst.get("dimension"):
            conclusions.append(
                f"拖累最大的维度为 **{worst.get('dimension')}**，变化额 **{_fmt_num(worst.get('delta'))}** 元。"
            )
        if best.get("dimension") and best is not worst:
            conclusions.append(
                f"正向拉动最大的维度为 **{best.get('dimension')}**，变化额 **{_fmt_num(best.get('delta'))}** 元。"
            )
        while len(conclusions) < 3:
            conclusions.append("建议对负向贡献维度做下钻，定位具体 SKU 或客户群。")

        detail_section = "### 4.1 各维度销售额变化贡献\n\n"
        detail_section += "| 维度 | 近6月(元) | 前6月(元) | 变化额(元) |\n|------|----------|----------|------------|\n"
        for r in detail_rows:
            detail_section += (
                f"| {r.get('dimension')} | {_fmt_num(r.get('curr_sales'))} | "
                f"{_fmt_num(r.get('prev_sales'))} | {_fmt_num(r.get('delta'))} |\n"
            )
        detail_section += "\n**解读**：变化额最负的维度是首要归因对象；需结合大单/季节因素排除偶然波动。"

        bullets = "\n".join(f"- {c}" for c in conclusions[:5])
        sugg = "\n".join(
            f"{i+1}. {s}"
            for i, s in enumerate([
                f"针对 {worst.get('dimension', '主要负向维度')} 做 SKU 级下钻，确认是量跌还是价跌。",
                "对比同期市场/竞品，区分外部环境 vs 内部运营因素。",
                "对正向维度复制成功策略，对负向维度制定专项改善计划。",
            ])
        )

        return (
            f"## 1. 分析概要\n\n"
            f"- **用户问题**：{requirement}\n"
            f"- **分析类型**：{type_label}\n"
            f"- **时间口径**：近 6 月 {start_date}~{end_date} vs 前 6 月 {prev_start}~{start_date}\n"
            f"- **数据来源**：`orders` ⋈ `order_items` ⋈ 维度表（品类/区域）\n\n"
            f"## 2. 核心结论\n\n{bullets}\n\n"
            f"## 3. 关键指标\n\n"
            f"| 指标 | 数值 | 说明 |\n|------|------|------|\n"
            f"| 近6月销售额 | {_fmt_num(curr)} 元 | 当前周期 GMV |\n"
            f"| 前6月销售额 | {_fmt_num(prev)} 元 | 对比基准 |\n"
            f"| 整体变化 | {change} | 环比周期对比 |\n"
            f"| 最大负向维度 | {worst.get('dimension', '-')} | 变化额 {_fmt_num(worst.get('delta'))} 元 |\n"
            f"| 分析维度数 | {len(detail_rows)} 个 | 按品类或区域拆解 |\n\n"
            f"## 4. 详细分析\n\n{detail_section}\n\n"
            f"## 5. 业务建议\n\n{sugg}\n\n"
            f"## 6. 数据说明与局限\n\n"
            f"- **归因方法**：维度级销售额差额拆解，非因果推断。\n"
            f"- **局限**：未控制促销/节假日混杂；多维度交叉需进一步 OLAP 下钻。"
        )

    def _build_t3_compare(self, requirement: str, type_label: str, t2_data: dict[str, Any]) -> str:
        kpi = t2_data.get("kpi", {})
        detail_rows = t2_data.get("detail_rows", [])
        start_date = t2_data.get("start_date", "")
        end_date = t2_data.get("end_date", "")
        sales = float(kpi.get("total_sales") or 0)
        top = detail_rows[0] if detail_rows else {}

        conclusions = [
            f"近 6 月总销售额 **{_fmt_num(sales)}** 元，共 **{kpi.get('order_count', 0)}** 笔订单。",
            f"销售额最高品类为 **{top.get('category', '-')}**（{_fmt_num(top.get('sales_amt'))} 元）。",
        ]
        if len(detail_rows) > 1 and sales:
            share = float(top.get("sales_amt") or 0) / sales * 100
            conclusions.append(f"头部品类占总额 **{share:.1f}%**。")
        while len(conclusions) < 3:
            conclusions.append("长尾品类可评估 ROI 与库存周转。")

        detail_section = "### 4.1 品类销售对比\n\n| 品类 | 订单数 | 销售额(元) | 销量 |\n|------|--------|------------|------|\n"
        for row in detail_rows:
            detail_section += (
                f"| {row.get('category')} | {row.get('order_count')} | "
                f"{_fmt_num(row.get('sales_amt'))} | {row.get('total_qty')} |\n"
            )

        bullets = "\n".join(f"- {c}" for c in conclusions[:5])
        return (
            f"## 1. 分析概要\n\n"
            f"- **用户问题**：{requirement}\n"
            f"- **分析类型**：{type_label}\n"
            f"- **时间口径**：{start_date} ~ {end_date}\n"
            f"- **数据来源**：`orders` ⋈ `order_items` ⋈ `products`\n\n"
            f"## 2. 核心结论\n\n{bullets}\n\n"
            f"## 3. 关键指标\n\n"
            f"| 指标 | 数值 | 说明 |\n|------|------|------|\n"
            f"| 总销售额 | {_fmt_num(sales)} 元 | 近 6 月 GMV |\n"
            f"| 品类数 | {len(detail_rows)} 个 | 有效品类计数 |\n"
            f"| 头部品类 | {top.get('category', '-')} | 销售额最高 |\n"
            f"| 头部品类销售额 | {_fmt_num(top.get('sales_amt'))} 元 | Top1 GMV |\n\n"
            f"## 4. 详细分析\n\n{detail_section}\n\n"
            f"## 5. 业务建议\n\n"
            f"1. 巩固头部品类份额，评估配套交叉销售。\n"
            f"2. 对尾部品类做 SKU 精简或促销清仓。\n"
            f"3. 按品类设定独立 KPI 与库存策略。\n\n"
            f"## 6. 数据说明与局限\n\n"
            f"- **时间范围**：{start_date} ~ {end_date}；仅 Completed 订单。\n"
            f"- **局限**：品类级对比未细分到 SKU/客户群。"
        )

    def _build_t3_trend(self, requirement: str, type_label: str, t2_data: dict[str, Any]) -> str:
        kpi = t2_data.get("kpi", {})
        prev = t2_data.get("prev", {})
        detail_rows = t2_data.get("detail_rows", [])
        start_date = t2_data.get("start_date", "")
        end_date = t2_data.get("end_date", "")
        sales = float(kpi.get("total_sales") or 0)
        orders = int(kpi.get("order_count") or 0)
        qty = int(kpi.get("total_qty") or 0)
        prev_sales = float(prev.get("prev_sales") or 0)
        change = _pct_change(sales, prev_sales)
        avg_order = sales / orders if orders else 0

        conclusions = [
            f"近 6 月（{start_date} ~ {end_date}）完成订单 **{orders}** 笔，销售额 **{_fmt_num(sales)}** 元，"
            f"较前一周期 **{change}**。",
            f"总销量 **{qty}** 件，客单价约 **{_fmt_num(avg_order)}** 元/单。",
        ]
        if detail_rows:
            best_month = max(detail_rows, key=lambda r: float(r.get("sales_amt") or 0))
            worst_month = min(detail_rows, key=lambda r: float(r.get("sales_amt") or 0))
            conclusions.append(
                f"销售额最高月份为 **{best_month.get('month')}**，最低为 **{worst_month.get('month')}**。"
            )
            if len(detail_rows) >= 2:
                first = float(detail_rows[0].get("sales_amt") or 0)
                last = float(detail_rows[-1].get("sales_amt") or 0)
                trend = "上升" if last > first else "下降" if last < first else "持平"
                conclusions.append(f"从首月到末月，销售额整体呈 **{trend}** 走势。")
        while len(conclusions) < 3:
            conclusions.append("建议结合业务日历与促销活动进一步解读波动原因。")

        detail_section = "### 4.1 月度销售趋势\n\n| 月份 | 订单数 | 销售额(元) |\n|------|--------|------------|\n"
        for row in detail_rows:
            detail_section += (
                f"| {row.get('month')} | {row.get('order_count')} | {_fmt_num(row.get('sales_amt'))} |\n"
            )
        detail_section += "\n**解读**：观察月度订单数与销售额的同步/背离，可识别大单驱动月份与淡季。"

        bullets = "\n".join(f"- {c}" for c in conclusions[:5])
        sugg = "\n".join(
            f"{i+1}. {s}"
            for i, s in enumerate([
                "建立月度销售仪表盘，跟踪销售额、订单数、客单价三指标联动。",
                "对波动超过 30% 的月份做活动/大单归因。",
                "若连续两个月下滑，提前启动客户回访或促销预案。",
            ])
        )

        return (
            f"## 1. 分析概要\n\n"
            f"- **用户问题**：{requirement}\n"
            f"- **分析类型**：{type_label}\n"
            f"- **时间口径**：{start_date} 至 {end_date}（以库内最晚完成订单日回溯 6 个月）\n"
            f"- **数据来源**：`orders` ⋈ `order_items`；仅 Completed 订单\n\n"
            f"## 2. 核心结论\n\n{bullets}\n\n"
            f"## 3. 关键指标\n\n"
            f"| 指标 | 数值 | 说明 |\n|------|------|------|\n"
            f"| 总销售额 | {_fmt_num(sales)} 元 | 近 6 月 GMV |\n"
            f"| 总订单数 | {orders} 笔 | COUNT(DISTINCT order_id) |\n"
            f"| 总销量 | {qty} 件 | 订单行数量合计 |\n"
            f"| 客单价 | {_fmt_num(avg_order)} 元 | 销售额 / 订单数 |\n"
            f"| 环比销售额变化 | {change} | 对比前一等长 6 个月周期 |\n"
            f"| 前一周期销售额 | {_fmt_num(prev_sales)} 元 | 基准对比口径 |\n\n"
            f"## 4. 详细分析\n\n{detail_section}\n\n"
            f"## 5. 业务建议\n\n{sugg}\n\n"
            f"## 6. 数据说明与局限\n\n"
            f"- **时间范围**：{start_date} ~ {end_date}。\n"
            f"- **金额口径**：SUM(quantity × unit_price × (1−discount))。\n"
            f"- **局限**：样本量 {orders} 笔，不宜外推至全市场。"
        )

    def _run_verifier(self, board_id: str, report: str) -> dict[str, Any]:
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

        result_payload = {
            "passed": passed,
            "summary": summary,
            "rework_rounds_used": 0,
            "structure_checks": structure_checks,
            "fix_items": fix_items,
            "report_task_id": "T3",
        }

        board.assign_task(board_id, "T4", "verifier-agent")
        board.append_result(
            board_id,
            "T4",
            "verifier-agent",
            json.dumps(result_payload, ensure_ascii=False),
            set_status="completed" if passed else "blocked",
        )
        board.complete_task(board_id, "T4")

        if not passed:
            raw = board._load_board(board_id)  # type: ignore[attr-defined]
            raw["status"] = "blocked"
            board._save_board(raw)  # type: ignore[attr-defined]

        return result_payload
