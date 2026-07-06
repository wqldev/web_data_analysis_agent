"""Builder-agent: 用户流失分析 T1~T3 执行脚本。"""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "src" / "mcp"))

from core.config_store import apply_config, load_config  # noqa: E402
from core import mysql_client  # noqa: E402
import task_board_server as tb  # noqa: E402

BOARD_ID = "3eae0b1b-1757-4d5b-8e05-ad0b52ddf524"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def fmt_num(v) -> str:
    if v is None:
        return "-"
    try:
        f = float(v)
        if f == int(f):
            return f"{int(f):,}"
        return f"{f:,.2f}"
    except (TypeError, ValueError):
        return str(v)


def ensure_tasks() -> None:
    board = tb._load_board(BOARD_ID)
    if board.get("tasks"):
        return
    planner_tasks = [
        {
            "task_id": "T1",
            "title": "确认数据源与字段",
            "description": "list_tables，确认 customers/orders/order_items，基准日与流失分层口径",
            "acceptance_criteria": ["明确目标表名", "明确基准日与流失分层", "明确 LTV 计算口径"],
            "assignee": "builder-agent",
        },
        {
            "task_id": "T2",
            "title": "执行流失分群 SQL",
            "description": "客户级 churn_risk + region/industry 归因 + Top 客户明细",
            "acceptance_criteria": ["仅 SELECT", "churn_risk 分层正确", "产出 KPI 与归因表"],
            "assignee": "builder-agent",
        },
        {
            "task_id": "T3",
            "title": "撰写分析报告",
            "description": "严格按 report-template.md 六节",
            "acceptance_criteria": ["六节完整", "数字来自 T2", "分群+归因型"],
            "assignee": "builder-agent",
        },
        {
            "task_id": "T4",
            "title": "验收分析交付物",
            "description": "",
            "acceptance_criteria": ["对照 T1~T3", "六节完整性"],
            "assignee": "verifier-agent",
        },
    ]
    for t in planner_tasks:
        board["tasks"].append(
            {
                **t,
                "status": "assigned",
                "results": [],
                "created_at": now_iso(),
                "updated_at": now_iso(),
            }
        )
    board["updated_at"] = now_iso()
    tb._save_board(board)


def run_t1() -> tuple[str, str]:
    tables = mysql_client.list_tables()
    ref_rows = mysql_client.execute_query(
        "SELECT MAX(order_date) AS max_dt, MIN(order_date) AS min_dt "
        "FROM orders WHERE order_status = 'Completed'"
    )
    ref = ref_rows[0] if ref_rows else {}
    max_dt = str(ref.get("max_dt") or "")[:10]

    def cols(table: str) -> str:
        return ", ".join(c["Field"] for c in mysql_client.describe_table(table))

    content = (
        "【T1 数据源与字段确认】\n\n"
        f"**探库结果**：共 {len(tables)} 张表\n"
        f"- `customers`: {cols('customers')}\n"
        f"- `orders`: {cols('orders')}\n"
        f"- `order_items`: {cols('order_items')}\n\n"
        "**目标表**：`customers` ⋈ `orders` ⋈ `order_items`\n"
        f"**基准日**：{max_dt}（MAX(Completed order_date)）\n"
        "**流失风险分层**：\n"
        "- 高流失风险：末单间隔 ≥90 天 且 近 3 月订单数 = 0（曾有 Completed 订单）\n"
        "- 中流失风险：末单间隔 ≥60 天（且不满足高风险条件）\n"
        "- 活跃：末单间隔 <60 天\n"
        "- 从未下单：无 Completed 订单\n"
        "**LTV 口径**：SUM(order_items.quantity * order_items.unit_price * (1 - order_items.discount))\n"
        "**订单口径**：仅 order_status='Completed'\n"
        "**分析类型**：分群+归因型（A-10 / S-07）"
    )
    tb.append_result(BOARD_ID, "T1", "builder-agent", content)
    tb.complete_task(BOARD_ID, "T1")
    return content, max_dt


def run_t2(max_dt: str) -> tuple[dict, str]:
    churn_sql = """
    WITH ref AS (
      SELECT MAX(order_date) AS max_dt FROM orders WHERE order_status = 'Completed'
    ),
    cust AS (
      SELECT c.customer_id, c.customer_name, c.region, c.industry,
        COUNT(DISTINCT o.order_id) AS total_orders,
        MAX(o.order_date) AS last_order_date,
        DATEDIFF(r.max_dt, MAX(o.order_date)) AS days_since_last,
        COALESCE(SUM(oi.quantity * oi.unit_price * (1 - oi.discount)), 0) AS lifetime_value,
        SUM(CASE WHEN o.order_date >= DATE_SUB(r.max_dt, INTERVAL 3 MONTH) THEN 1 ELSE 0 END) AS orders_last_3m
      FROM customers c
      CROSS JOIN ref r
      LEFT JOIN orders o ON c.customer_id = o.customer_id AND o.order_status = 'Completed'
      LEFT JOIN order_items oi ON o.order_id = oi.order_id
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
    customer_rows = mysql_client.execute_query(churn_sql)

    risk_counts: dict[str, int] = {}
    for row in customer_rows:
        risk = row.get("churn_risk") or "未知"
        risk_counts[risk] = risk_counts.get(risk, 0) + 1

    region_agg: dict[str, dict[str, int]] = {}
    industry_agg: dict[str, dict[str, int]] = {}
    for row in customer_rows:
        region = row.get("region") or "未知"
        industry = row.get("industry") or "未知"
        region_agg.setdefault(region, {"customers": 0, "high_risk": 0})
        industry_agg.setdefault(industry, {"customers": 0, "high_risk": 0})
        region_agg[region]["customers"] += 1
        industry_agg[industry]["customers"] += 1
        if row.get("churn_risk") == "高流失风险":
            region_agg[region]["high_risk"] += 1
            industry_agg[industry]["high_risk"] += 1

    region_rows = [
        {"region": k, "customers": v["customers"], "high_risk": v["high_risk"]}
        for k, v in sorted(region_agg.items(), key=lambda x: (-x[1]["high_risk"], -x[1]["customers"]))
    ]
    industry_rows = [
        {"industry": k, "customers": v["customers"], "high_risk": v["high_risk"]}
        for k, v in sorted(industry_agg.items(), key=lambda x: (-x[1]["high_risk"], -x[1]["customers"]))
    ]

    high_risk = [r for r in customer_rows if r.get("churn_risk") == "高流失风险"][:10]
    medium_risk = [r for r in customer_rows if r.get("churn_risk") == "中流失风险"][:5]
    total = len(customer_rows)
    high_n = risk_counts.get("高流失风险", 0)
    med_n = risk_counts.get("中流失风险", 0)
    active_n = risk_counts.get("活跃", 0)
    never_n = risk_counts.get("从未下单", 0)

    cust_table = (
        "| 客户 | 区域 | 行业 | 历史订单 | 末单间隔(天) | 生命周期价值 | 风险等级 |\n"
        "|------|------|------|----------|--------------|--------------|----------|\n"
    )
    for r in high_risk + medium_risk:
        cust_table += (
            f"| {r.get('customer_name')} | {r.get('region')} | {r.get('industry')} | "
            f"{r.get('total_orders')} | {r.get('days_since_last') or '-'} | "
            f"{fmt_num(r.get('lifetime_value'))} | {r.get('churn_risk')} |\n"
        )

    region_table = "| 区域 | 客户数 | 高风险人数 |\n|------|--------|------------|\n"
    for r in region_rows:
        region_table += f"| {r.get('region')} | {r.get('customers')} | {r.get('high_risk')} |\n"

    industry_table = "| 行业 | 客户数 | 高风险人数 |\n|------|--------|------------|\n"
    for r in industry_rows:
        industry_table += f"| {r.get('industry')} | {r.get('customers')} | {r.get('high_risk')} |\n"

    t2_content = (
        "【T2 客户流失风险分析】\n\n"
        f"**基准日**：{max_dt}（库内最晚完成订单日）\n"
        f"**客户总数**：{total}\n"
        f"**高流失风险**：{high_n} 人（≥90 天未下单且近 3 月无订单）\n"
        f"**中流失风险**：{med_n} 人（≥60 天未下单）\n"
        f"**活跃客户**：{active_n} 人\n"
        f"**从未下单**：{never_n} 人\n\n"
        "**风险分布 KPI**：\n"
        "| 风险等级 | 人数 | 占比 |\n|----------|------|------|\n"
        f"| 高流失风险 | {high_n} | {high_n / total * 100:.1f}% |\n"
        f"| 中流失风险 | {med_n} | {med_n / total * 100:.1f}% |\n"
        f"| 活跃 | {active_n} | {active_n / total * 100:.1f}% |\n"
        f"| 从未下单 | {never_n} | {never_n / total * 100:.1f}% |\n\n"
        f"**区域归因表**：\n{region_table}\n"
        f"**行业归因表**：\n{industry_table}\n"
        f"**Top10 高风险 + Top5 中风险客户明细**：\n{cust_table}"
    )
    tb.append_result(BOARD_ID, "T2", "builder-agent", t2_content)
    tb.complete_task(BOARD_ID, "T2")

    data = {
        "ref_date": max_dt,
        "total": total,
        "high_n": high_n,
        "med_n": med_n,
        "active_n": active_n,
        "never_n": never_n,
        "high_risk": high_risk,
        "medium_risk": medium_risk,
        "region_rows": region_rows,
        "industry_rows": industry_rows,
    }
    return data, t2_content


def run_t3(data: dict) -> str:
    max_dt = data["ref_date"]
    total = data["total"]
    high_n = data["high_n"]
    med_n = data["med_n"]
    active_n = data["active_n"]
    never_n = data["never_n"]
    high_risk = data["high_risk"]
    medium_risk = data["medium_risk"]
    region_rows = data["region_rows"]
    industry_rows = data["industry_rows"]

    top_names = [r.get("customer_name") for r in high_risk[:5] if r.get("customer_name")]
    top_list = "、".join(top_names) if top_names else "（暂无）"
    avg_gap = (
        sum(int(r.get("days_since_last") or 0) for r in high_risk) / len(high_risk)
        if high_risk
        else 0
    )

    detail_section = "### 4.1 高/中流失风险客户清单\n\n"
    detail_section += (
        "| 客户 | 区域 | 行业 | 历史订单 | 末单间隔(天) | 生命周期价值(元) | 风险等级 |\n"
        "|------|------|------|----------|--------------|------------------|----------|\n"
    )
    for r in high_risk + medium_risk:
        detail_section += (
            f"| {r.get('customer_name')} | {r.get('region')} | {r.get('industry')} | "
            f"{r.get('total_orders')} | {r.get('days_since_last') or '-'} | "
            f"{fmt_num(r.get('lifetime_value'))} | {r.get('churn_risk')} |\n"
        )
    detail_section += (
        "\n**解读**：末单间隔长且近 3 月零订单的客户，复购概率最低；"
        "生命周期价值高者流失对 GMV 伤害更大，应优先挽回。"
    )

    detail_section += (
        "\n\n### 4.2 区域风险分布\n\n"
        "| 区域 | 客户数 | 高风险人数 | 高风险占比 |\n"
        "|------|--------|------------|------------|\n"
    )
    for r in region_rows:
        c = int(r.get("customers") or 0)
        h = int(r.get("high_risk") or 0)
        pct = f"{h / c * 100:.1f}%" if c else "-"
        detail_section += f"| {r.get('region')} | {c} | {h} | {pct} |\n"

    detail_section += (
        "\n\n### 4.3 行业风险分布\n\n"
        "| 行业 | 客户数 | 高风险人数 | 高风险占比 |\n"
        "|------|--------|------------|------------|\n"
    )
    for r in industry_rows:
        c = int(r.get("customers") or 0)
        h = int(r.get("high_risk") or 0)
        pct = f"{h / c * 100:.1f}%" if c else "-"
        detail_section += f"| {r.get('industry')} | {c} | {h} | {pct} |\n"

    top_region = region_rows[0] if region_rows else {}
    top_industry = industry_rows[0] if industry_rows else {}

    vip = next((r for r in high_risk if float(r.get("lifetime_value") or 0) >= 80000), high_risk[0] if high_risk else None)
    vip_name = vip.get("customer_name") if vip else "高 LTV 客户"
    vip_ltv = fmt_num(vip.get("lifetime_value")) if vip else "-"

    report = (
        f"## 1. 分析概要\n\n"
        f"- **用户问题**：分析哪些用户最容易流失\n"
        f"- **分析类型**：分群+归因型（A-10 / S-07，客户流失风险分群与区域/行业归因）\n"
        f"- **时间口径**：以 **{max_dt}** 为基准日，Recency=末单距今天数；近 3 月=基准日前 90 天\n"
        f"- **数据来源**：`customers` ⋈ `orders` ⋈ `order_items`；仅 Completed 订单\n\n"
        f"## 2. 核心结论\n\n"
        f"- 共 **{total}** 名客户中，**{high_n}** 人处于高流失风险（≥90 天未下单且近 3 月无订单），占比 **{high_n / total * 100:.1f}%**。\n"
        f"- **{med_n}** 人为中流失风险（≥60 天未下单），需纳入重点关怀名单。\n"
        f"- 最容易流失的客户包括：**{top_list}**（按末单间隔与近 3 月活跃度综合判定）。\n"
        f"- 高风险客户平均末单间隔 **{avg_gap:.0f}** 天，显著高于活跃客户（近 60 天内有单）。\n"
        f"- 区域维度上，**{top_region.get('region', '-')}** 高风险客户最多（{top_region.get('high_risk', 0)} 人）；"
        f"行业维度上，**{top_industry.get('industry', '-')}** 高风险集中度最高（{top_industry.get('high_risk', 0)} 人）。\n\n"
        f"## 3. 关键指标\n\n"
        f"| 指标 | 数值 | 说明 |\n|------|------|------|\n"
        f"| 客户总数 | {total} 人 | customers 表全量 |\n"
        f"| 高流失风险 | {high_n} 人 | ≥90 天未下单且近 3 月无订单 |\n"
        f"| 中流失风险 | {med_n} 人 | ≥60 天未下单 |\n"
        f"| 活跃客户 | {active_n} 人 | 近 60 天内有订单 |\n"
        f"| 高风险占比 | {high_n / total * 100:.1f}% | 高流失/总客户 |\n"
        f"| 从未下单 | {never_n} 人 | 注册但无 Completed 订单 |\n"
        f"| 高风险平均末单间隔 | {avg_gap:.0f} 天 | Top10 高风险客户均值 |\n\n"
        f"## 4. 详细分析\n\n{detail_section}\n\n"
        f"## 5. 业务建议\n\n"
        f"1. 对 {top_list} 等高风险客户启动 1v1 回访，了解未续购原因并提供专属优惠。\n"
        f"2. 建立「末单间隔 >60 天」自动预警，触发关怀短信或销售跟进任务。\n"
        f"3. 对高生命周期价值但高风险的 VIP 客户（如 {vip_name} LTV {vip_ltv} 元），安排客户经理专项挽留。\n"
        f"4. 针对 **{top_region.get('region', '-')}** 区域与 **{top_industry.get('industry', '-')}** 行业制定差异化留存策略，优化对应产品线或渠道触达。\n\n"
        f"## 6. 数据说明与局限\n\n"
        f"- **流失定义**：基于 Recency（末单间隔）+ 近 3 月订单数，非真实 churn 标签。\n"
        f"- **基准日**：{max_dt}；不含进行中的 Pending/Cancelled 订单。\n"
        f"- **LTV 口径**：SUM(quantity × unit_price × (1−discount))，仅 Completed 订单。\n"
        f"- **局限**：样本 {total} 人，未纳入客服工单/满意度等外源信号；行业差异大时阈值（60/90 天）需按业务调整；"
        f"区域/行业归因为静态快照，未控制客户规模差异。"
    )
    tb.append_result(BOARD_ID, "T3", "builder-agent", report)
    tb.complete_task(BOARD_ID, "T3")
    return report


def main() -> None:
    apply_config(load_config())
    ensure_tasks()
    board = tb._load_board(BOARD_ID)
    task_status = {t["task_id"]: t["status"] for t in board["tasks"]}

    if task_status.get("T1") != "completed":
        _, max_dt = run_t1()
    else:
        ref_rows = mysql_client.execute_query(
            "SELECT MAX(order_date) AS max_dt FROM orders WHERE order_status = 'Completed'"
        )
        max_dt = str(ref_rows[0].get("max_dt") or "")[:10]

    if task_status.get("T2") != "completed":
        data, _ = run_t2(max_dt)
    else:
        data, _ = run_t2(max_dt)

    if task_status.get("T3") != "completed":
        report = run_t3(data)
    else:
        t3 = next(t for t in board["tasks"] if t["task_id"] == "T3")
        report = t3["results"][-1]["content"] if t3.get("results") else run_t3(data)

    print("---REPORT---")
    print(report)


if __name__ == "__main__":
    main()
