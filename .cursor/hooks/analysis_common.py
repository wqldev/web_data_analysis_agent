"""数据分析 Hook 公共模块：意图识别与 SQL 审计。"""

from __future__ import annotations

import re
from datetime import datetime
from zoneinfo import ZoneInfo

from guard_common import _safe_text, log_dir

CHINA_TZ = ZoneInfo("Asia/Shanghai")

ANALYSIS_INTENT_PATTERNS: list[tuple[str, re.Pattern[str], str]] = [
    ("compare", re.compile(r"同比|环比|对比|哪个.{0,20}(更好|更高|最高|更低)|排名|Top|TOP|前三|后三|差距", re.I), "对比分析"),
    ("trend", re.compile(r"趋势|涨|跌|走势|近.{0,6}(月|年|半年|季度)|波动|异常|预测|季节性|拐点|生命周期", re.I), "趋势分析"),
    ("attribution", re.compile(r"为什么|原因|因素|影响|导致|问题出|归因|下降|增长.{0,10}原因", re.I), "归因分析"),
    ("segment", re.compile(r"分群|分几类|画像|客户类型|VIP|年龄段|高价值|沉睡|复购|流失.{0,10}特征", re.I), "分群分析"),
    ("hypothesis", re.compile(r"如果|能不能|会不会|假设|要是|值不值得|提升多少|降低多少", re.I), "假设分析"),
    ("general", re.compile(r"分析|看看|情况|怎么样|如何|统计|汇总|洞察|报表|指标|销售|订单|转化", re.I), "通用分析"),
]

TABLE_FROM_PATTERN = re.compile(
    r"\b(?:FROM|JOIN)\s+[`'\"]?([a-zA-Z0-9_().]+)[`'\"]?",
    re.IGNORECASE,
)

QUERY_KIND_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("aggregate", re.compile(r"\b(COUNT|SUM|AVG|MAX|MIN|GROUP\s+BY)\b", re.I)),
    ("window", re.compile(r"\b(OVER\s*\(|ROW_NUMBER|RANK|DENSE_RANK|LAG|LEAD)\b", re.I)),
    ("join", re.compile(r"\b(JOIN|INNER\s+JOIN|LEFT\s+JOIN|RIGHT\s+JOIN)\b", re.I)),
    ("explore", re.compile(r"\b(SHOW|DESCRIBE|EXPLAIN|LIST)\b", re.I)),
    ("select", re.compile(r"^\s*SELECT\b", re.I)),
]


def classify_analysis_intent(text: str) -> tuple[str, str, str] | None:
    content = text.strip()
    if not content:
        return None
    for category, pattern, label in ANALYSIS_INTENT_PATTERNS:
        match = pattern.search(content)
        if match:
            return category, label, match.group(0)
    return None


def extract_sql_metadata(query: str) -> dict[str, str]:
    sql = query.strip()
    if not sql:
        return {"query_kind": "empty", "tables": ""}

    query_kind = "other"
    for kind, pattern in QUERY_KIND_PATTERNS:
        if pattern.search(sql):
            query_kind = kind
            break

    tables = sorted({m.group(1) for m in TABLE_FROM_PATTERN.finditer(sql)})
    return {
        "query_kind": query_kind,
        "tables": ",".join(tables),
    }


def append_analysis_intent_log(
    category: str,
    label: str,
    keyword: str,
    prompt: str,
    source: str,
) -> None:
    log_file = log_dir() / "analysis-intent.log"
    timestamp = datetime.now(CHINA_TZ).strftime("%Y-%m-%d %H:%M:%S")
    safe_prompt = _safe_text(prompt).replace("\n", " ").replace("\t", " ")[:300]
    line = (
        f"{timestamp}\t{category}\t{label}\t{keyword}\t{source}\t{safe_prompt}\n"
    )
    with log_file.open("a", encoding="utf-8") as handle:
        handle.write(line)


def append_analysis_query_log(
    server: str,
    tool_name: str,
    query_kind: str,
    tables: str,
    query: str,
) -> None:
    log_file = log_dir() / "analysis-query.log"
    timestamp = datetime.now(CHINA_TZ).strftime("%Y-%m-%d %H:%M:%S")
    safe_query = _safe_text(query).replace("\n", " ").replace("\t", " ")[:500]
    line = (
        f"{timestamp}\t{query_kind}\t{tables}\t{server}\t{tool_name}\t{safe_query}\n"
    )
    with log_file.open("a", encoding="utf-8") as handle:
        handle.write(line)
