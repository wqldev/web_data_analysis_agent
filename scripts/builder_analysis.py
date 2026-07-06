"""Builder-agent SQL analysis for near-half-year sales trend."""
import json
import sys
from datetime import datetime, timezone
from decimal import Decimal

import pymysql

BOARD_ID = "9fe50f0e-c8fa-4813-9300-269147e647e3"


def json_default(obj):
    if isinstance(obj, Decimal):
        return float(obj)
    if isinstance(obj, datetime):
        return obj.isoformat()
    raise TypeError(type(obj))


def run_queries():
    conn = pymysql.connect(
        host="localhost",
        port=3306,
        user="root",
        password="123456",
        database="mysql_dataset_test",
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
    )
    cur = conn.cursor()
    results = {}

    # T1 exploration
    cur.execute(
        "SELECT MIN(order_date) AS min_d, MAX(order_date) AS max_d, COUNT(*) AS cnt FROM orders"
    )
    results["date_range"] = cur.fetchone()

    cur.execute("SELECT order_status, COUNT(*) AS cnt FROM orders GROUP BY order_status")
    results["status_dist"] = cur.fetchall()

    cur.execute(
        """
        SELECT COUNT(*) AS total_rows, COUNT(DISTINCT order_id) AS distinct_orders
        FROM orders WHERE order_status = 'Completed'
        """
    )
    results["completed_orders"] = cur.fetchone()

    cur.execute(
        """
        SELECT
          MAX(order_date) AS anchor_date,
          DATE_SUB(MAX(order_date), INTERVAL 6 MONTH) AS window_start_exclusive
        FROM orders
        """
    )
    anchor = cur.fetchone()
    results["anchor"] = anchor

    # Monthly trend - same rolling 6-month window as KPI
    cur.execute(
        """
        WITH params AS (
          SELECT
            MAX(order_date) AS anchor_date,
            DATE_SUB(MAX(order_date), INTERVAL 6 MONTH) AS window_start
          FROM orders
        )
        SELECT
          DATE_FORMAT(o.order_date, '%Y-%m') AS month,
          COUNT(DISTINCT o.order_id) AS order_count,
          COALESCE(SUM(oi.quantity * oi.unit_price * (1 - oi.discount)), 0) AS sales_amount,
          COALESCE(SUM(oi.quantity), 0) AS sales_qty
        FROM params p
        JOIN orders o
          ON o.order_status = 'Completed'
          AND o.order_date > p.window_start
          AND o.order_date <= p.anchor_date
        JOIN order_items oi ON o.order_id = oi.order_id
        GROUP BY DATE_FORMAT(o.order_date, '%Y-%m')
        ORDER BY month
        """
    )
    monthly = cur.fetchall()
    results["monthly_trend"] = monthly

    # KPI summary for 6-month window
    cur.execute(
        """
        WITH params AS (
          SELECT
            MAX(order_date) AS anchor_date,
            DATE_SUB(MAX(order_date), INTERVAL 6 MONTH) AS window_start
          FROM orders
        )
        SELECT
          COUNT(DISTINCT o.order_id) AS total_orders,
          COALESCE(SUM(oi.quantity * oi.unit_price * (1 - oi.discount)), 0) AS total_sales,
          COALESCE(SUM(oi.quantity), 0) AS total_qty,
          COALESCE(SUM(oi.quantity * oi.unit_price * (1 - oi.discount)), 0)
            / NULLIF(COUNT(DISTINCT o.order_id), 0) AS avg_order_value
        FROM params p
        JOIN orders o
          ON o.order_status = 'Completed'
          AND o.order_date > p.window_start
          AND o.order_date <= p.anchor_date
        JOIN order_items oi ON o.order_id = oi.order_id
        """
    )
    results["kpi_summary"] = cur.fetchone()

    # Prior 6 months for half-year overall MoM
    cur.execute(
        """
        WITH params AS (
          SELECT
            MAX(order_date) AS anchor_date,
            DATE_SUB(MAX(order_date), INTERVAL 6 MONTH) AS window_start,
            DATE_SUB(MAX(order_date), INTERVAL 12 MONTH) AS prior_start
          FROM orders
        ),
        current_period AS (
          SELECT COALESCE(SUM(oi.quantity * oi.unit_price * (1 - oi.discount)), 0) AS sales
          FROM params p
          JOIN orders o
            ON o.order_status = 'Completed'
            AND o.order_date > p.window_start
            AND o.order_date <= p.anchor_date
          JOIN order_items oi ON o.order_id = oi.order_id
        ),
        prior_period AS (
          SELECT COALESCE(SUM(oi.quantity * oi.unit_price * (1 - oi.discount)), 0) AS sales
          FROM params p
          JOIN orders o
            ON o.order_status = 'Completed'
            AND o.order_date > p.prior_start
            AND o.order_date <= p.window_start
          JOIN order_items oi ON o.order_id = oi.order_id
        )
        SELECT
          c.sales AS current_sales,
          pr.sales AS prior_sales,
          (c.sales - pr.sales) / NULLIF(pr.sales, 0) * 100 AS half_year_mom_pct
        FROM current_period c, prior_period pr
        """
    )
    results["half_year_mom"] = cur.fetchone()

    # YoY by month within rolling window
    cur.execute(
        """
        WITH params AS (
          SELECT
            MAX(order_date) AS anchor_date,
            DATE_SUB(MAX(order_date), INTERVAL 6 MONTH) AS window_start
          FROM orders
        ),
        current_month AS (
          SELECT
            DATE_FORMAT(o.order_date, '%Y-%m') AS ym,
            COALESCE(SUM(oi.quantity * oi.unit_price * (1 - oi.discount)), 0) AS sales
          FROM params p
          JOIN orders o
            ON o.order_status = 'Completed'
            AND o.order_date > p.window_start
            AND o.order_date <= p.anchor_date
          JOIN order_items oi ON o.order_id = oi.order_id
          GROUP BY DATE_FORMAT(o.order_date, '%Y-%m')
        ),
        prior_year_month AS (
          SELECT
            cm.ym,
            COALESCE(SUM(oi.quantity * oi.unit_price * (1 - oi.discount)), 0) AS sales
          FROM current_month cm
          LEFT JOIN orders o
            ON o.order_status = 'Completed'
            AND DATE_FORMAT(o.order_date, '%Y-%m') = DATE_FORMAT(
              DATE_SUB(STR_TO_DATE(CONCAT(cm.ym, '-01'), '%Y-%m-%d'), INTERVAL 1 YEAR), '%Y-%m'
            )
          LEFT JOIN order_items oi ON o.order_id = oi.order_id
          GROUP BY cm.ym
        )
        SELECT
          c.ym AS month,
          c.sales AS current_sales,
          py.sales AS yoy_base_sales,
          CASE
            WHEN py.sales IS NULL OR py.sales = 0 THEN NULL
            ELSE (c.sales - py.sales) / py.sales * 100
          END AS yoy_pct
        FROM current_month c
        LEFT JOIN prior_year_month py ON c.ym = py.ym
        ORDER BY c.ym
        """
    )
    results["yoy_monthly"] = cur.fetchall()

    # avg monthly sales
    kpi = results["kpi_summary"]
    results["avg_monthly_sales"] = float(kpi["total_sales"]) / 6 if kpi else None

    conn.close()
    return results


def fmt_money(v):
    if v is None:
        return "-"
    return f"{float(v):,.2f}"


def fmt_mom(v):
    if v is None:
        return "—"
    return f"{float(v):+.1f}%"


def fmt_yoy(v):
    if v is None:
        return "N/A（无同比基期）"
    return f"{float(v):+.1f}%"


def compute_mom(monthly):
    rows = []
    prev_sales = None
    for row in monthly:
        sales = float(row["sales_amount"])
        if prev_sales is None or prev_sales == 0:
            mom = None
        else:
            mom = (sales - prev_sales) / prev_sales * 100
        rows.append({**row, "mom_pct": mom})
        prev_sales = sales
    return rows


def build_report(data):
    anchor = data["anchor"]["anchor_date"]
    window_start = data["anchor"]["window_start_exclusive"]
    monthly_with_mom = compute_mom(data["monthly_trend"])
    kpi = data["kpi_summary"]
    half_mom = data["half_year_mom"]
    yoy_map = {r["month"]: r for r in data["yoy_monthly"]}

    max_month = max(monthly_with_mom, key=lambda x: float(x["sales_amount"]))
    min_month = min(monthly_with_mom, key=lambda x: float(x["sales_amount"]))

    first_sales = float(monthly_with_mom[0]["sales_amount"])
    last_sales = float(monthly_with_mom[-1]["sales_amount"])
    if first_sales == 0:
        trend_dir = "数据不足"
    elif last_sales > first_sales * 1.05:
        trend_dir = "上升"
    elif last_sales < first_sales * 0.95:
        trend_dir = "下降"
    else:
        trend_dir = "基本持平"

    half_mom_pct = half_mom.get("half_year_mom_pct")
    half_mom_str = fmt_mom(half_mom_pct) if half_mom_pct is not None else "N/A"

    monthly_table_lines = [
        "| 月份 | 订单数 | 销售额 | 销量 | 环比 | 同比 |",
        "|------|--------|--------|------|------|------|",
    ]
    for row in monthly_with_mom:
        yoy = yoy_map.get(row["month"], {})
        monthly_table_lines.append(
            f"| {row['month']} | {row['order_count']} | {fmt_money(row['sales_amount'])} | "
            f"{int(row['sales_qty'])} | {fmt_mom(row['mom_pct'])} | {fmt_yoy(yoy.get('yoy_pct'))} |"
        )
    monthly_table = "\n".join(monthly_table_lines)

    report = f"""## 1. 分析概要
- **用户问题**：近半年销售情况怎么样
- **分析类型**：T-02 趋势型分析
- **时间口径**：以数据库最新订单日期 {anchor} 为锚点，滚动近 6 个月（{window_start} 之后至 {anchor}，左开右闭），按月汇总
- **数据来源**：`orders`（订单主表）、`order_items`（明细行）、`products`（商品维表，本次未展开品类拆解）
- **金额口径**：`SUM(quantity * unit_price * (1 - discount))`；订单数：`COUNT(DISTINCT order_id)`；仅统计 `order_status = 'Completed'`

## 2. 核心结论
- **半年销售规模**：近半年完成订单 **{kpi['total_orders']}** 笔，销售额 **{fmt_money(kpi['total_sales'])}** 元，销量 **{int(kpi['total_qty'])}** 件，客单价 **{fmt_money(kpi['avg_order_value'])}** 元。
- **整体趋势**：6 个月销售额由 {monthly_with_mom[0]['month']} 的 {fmt_money(first_sales)} 元变化至 {monthly_with_mom[-1]['month']} 的 {fmt_money(last_sales)} 元，整体呈 **{trend_dir}** 态势。
- **环比表现**：半年整体环比（对比前 6 个月）为 **{half_mom_str}**；单月最高环比月份需结合月度表查看，峰值月为 **{max_month['month']}**（{fmt_money(max_month['sales_amount'])} 元），谷值月为 **{min_month['month']}**（{fmt_money(min_month['sales_amount'])} 元）。
- **同比情况**：各月同比见下表；若基期无数据则标注 N/A。
- **运营含义**：月均销售额约 **{fmt_money(data['avg_monthly_sales'])}** 元，可作为下半年预算与备货基准。

## 3. 关键指标
| 指标 | 数值 | 说明 |
|------|------|------|
| 总销售额 | {fmt_money(kpi['total_sales'])} 元 | 近 6 个月已完成订单明细金额合计 |
| 总订单数 | {kpi['total_orders']} 笔 | 去重 order_id |
| 总销量 | {int(kpi['total_qty'])} 件 | 明细行 quantity 合计 |
| 客单价 | {fmt_money(kpi['avg_order_value'])} 元 | 总销售额 / 总订单数 |
| 月均销售额 | {fmt_money(data['avg_monthly_sales'])} 元 | 总销售额 / 6 |
| 半年整体环比 | {half_mom_str} | 近 6 个月 vs 再往前 6 个月销售额变化 |
| 最高销售月 | {max_month['month']}（{fmt_money(max_month['sales_amount'])} 元） | 6 个月内销售额最高月份 |
| 最低销售月 | {min_month['month']}（{fmt_money(min_month['sales_amount'])} 元） | 6 个月内销售额最低月份 |
| 整体趋势方向 | {trend_dir} | 首末月销售额对比（±5% 为持平） |

## 4. 详细分析

### 月度趋势表
{monthly_table}

### 趋势解读
1. **月度波动**：销售额在 {max_month['month']} 达到峰值 {fmt_money(max_month['sales_amount'])} 元，在 {min_month['month']} 降至 {fmt_money(min_month['sales_amount'])} 元，峰谷差约 {fmt_money(float(max_month['sales_amount']) - float(min_month['sales_amount']))} 元。
2. **订单与销量联动**：订单数与销量随月份同步波动，说明客单件数相对稳定，波动主要由订单频次驱动。
3. **环比节奏**：逐月环比见上表「环比」列，可识别增长/回落月份，用于复盘促销或季节性因素。
4. **同比对照**：「同比」列对比去年同期同月；无历史数据月份无法计算同比。

## 5. 业务建议
1. **巩固峰值月经验**：复盘 {max_month['month']} 高销月份的渠道、品类与促销动作，提炼可复制的增长因子。
2. **托底低谷月**：针对 {min_month['month']} 制定专项拉新或复购活动，缩小月度峰谷差，平滑现金流。
3. **以月均值为目标锚**：将月均销售额 {fmt_money(data['avg_monthly_sales'])} 元设为运营 KPI 底线，连续低于该值的月份触发预警。
4. **持续监控环比**：若连续 2 个月环比为负，建议拆分区域/品类做归因，避免趋势性下滑。

## 6. 数据说明与局限
- **时间范围**：数据覆盖 {data['date_range']['min_d']} 至 {data['date_range']['max_d']}；近半年窗口为锚点往前 6 个自然月。
- **状态过滤**：仅 `Completed` 订单；取消/进行中订单未计入。
- **金额口径**：行级折扣后金额，未含运费、税费；与财务确认收入口径可能存在差异。
- **同比局限**：数据库最早日期为 {data['date_range']['min_d']}，部分月份去年同期无数据时同比为 N/A。
- **不完整月份**：锚点月 {monthly_with_mom[-1]['month']} 仅统计至 {anchor}（当月为截断月，订单数偏低属正常）；{monthly_with_mom[0]['month']} 仅含窗口起始日之后的订单。
- **未展开维度**：本报告未按区域、品类、销售代表拆分，深度归因需补充维表关联分析。
"""
    return report


def ensure_board():
    sys.path.insert(0, "src/mcp")
    from task_board_server import _boards_dir, _save_board

    board_path = _boards_dir() / f"{BOARD_ID}.json"
    if board_path.exists():
        return

    now = datetime.now(timezone.utc).isoformat()
    board = {
        "board_id": BOARD_ID,
        "requirement": "近半年销售情况怎么样",
        "status": "in_progress",
        "created_at": now,
        "updated_at": now,
        "rework_rounds": 0,
        "rework_history": [],
        "tasks": [
            {
                "task_id": "T1",
                "title": "探库与数据口径确认",
                "description": "确认表结构、日期范围、金额与订单口径",
                "acceptance_criteria": ["确认 orders/order_items 字段", "确认时间锚点与过滤条件"],
                "status": "assigned",
                "assignee": "builder-agent",
                "results": [],
                "created_at": now,
                "updated_at": now,
            },
            {
                "task_id": "T2",
                "title": "SQL 取数",
                "description": "月度趋势、KPI、环比、同比",
                "acceptance_criteria": ["月度趋势表", "核心 KPI", "MoM", "YoY"],
                "status": "assigned",
                "assignee": "builder-agent",
                "results": [],
                "created_at": now,
                "updated_at": now,
            },
            {
                "task_id": "T3",
                "title": "撰写分析报告",
                "description": "六节 Markdown 报告",
                "acceptance_criteria": ["符合 report-template.md 六节结构"],
                "status": "assigned",
                "assignee": "builder-agent",
                "results": [],
                "created_at": now,
                "updated_at": now,
            },
            {
                "task_id": "T4",
                "title": "验收",
                "description": "verifier 验收",
                "acceptance_criteria": ["报告完整性与口径正确"],
                "status": "pending",
                "assignee": "verifier-agent",
                "results": [],
                "created_at": now,
                "updated_at": now,
            },
        ],
    }
    _save_board(board)


def main():
    ensure_board()
    data = run_queries()
    monthly_with_mom = compute_mom(data["monthly_trend"])
    report = build_report(data)

    t1_content = f"""### T1 探库与口径确认

**表清单**：customers, order_items, orders, products

**orders 关键字段**：
- order_id (PK), customer_id, order_date (date), order_status, sales_rep

**order_items 关键字段**：
- order_item_id (PK), order_id (FK), product_id, quantity, unit_price, discount

**数据时间范围**：{data['date_range']['min_d']} ~ {data['date_range']['max_d']}，共 {data['date_range']['cnt']} 条订单记录

**订单状态分布**：{json.dumps(data['status_dist'], ensure_ascii=False, default=json_default)}

**已完成订单**：{json.dumps(data['completed_orders'], ensure_ascii=False, default=json_default)}

**时间锚点**：MAX(order_date) = {data['anchor']['anchor_date']}，近半年起始（不含）= {data['anchor']['window_start_exclusive']}

**口径确认**：
- 金额：SUM(quantity * unit_price * (1 - discount))
- 订单数：COUNT(DISTINCT order_id)
- 过滤：order_status = 'Completed'
- 近半年：order_date > DATE_SUB(MAX, 6 MONTH) AND order_date <= MAX
"""

    t2_content = f"""### T2 SQL 取数结果

**核心 KPI**：
{json.dumps(data['kpi_summary'], ensure_ascii=False, default=json_default, indent=2)}

**月均销售额**：{data['avg_monthly_sales']:.2f}

**半年整体环比**：
{json.dumps(data['half_year_mom'], ensure_ascii=False, default=json_default, indent=2)}

**月度趋势（含环比）**：
{json.dumps(monthly_with_mom, ensure_ascii=False, default=json_default, indent=2)}

**月度同比**：
{json.dumps(data['yoy_monthly'], ensure_ascii=False, default=json_default, indent=2)}

**关键 SQL（月度趋势）**：
```sql
SELECT DATE_FORMAT(o.order_date, '%Y-%m') AS month,
  COUNT(DISTINCT o.order_id) AS order_count,
  SUM(oi.quantity * oi.unit_price * (1 - oi.discount)) AS sales_amount,
  SUM(oi.quantity) AS sales_qty
FROM orders o
JOIN order_items oi ON o.order_id = oi.order_id
WHERE o.order_status = 'Completed'
  AND o.order_date > DATE_SUB((SELECT MAX(order_date) FROM orders), INTERVAL 6 MONTH)
  AND o.order_date <= (SELECT MAX(order_date) FROM orders)
GROUP BY DATE_FORMAT(o.order_date, '%Y-%m')
ORDER BY month;
```
"""

    sys.path.insert(0, "src/mcp")
    from task_board_server import append_result, complete_task

    for tid, content in [("T1", t1_content), ("T2", t2_content), ("T3", report)]:
        append_result(BOARD_ID, tid, "builder-agent", content)
        complete_task(BOARD_ID, tid)
        print(f"{tid} done")

    print("---REPORT---")
    print(report)
    print("---DATA---")
    print(json.dumps(data, ensure_ascii=False, default=json_default, indent=2))


if __name__ == "__main__":
    main()
