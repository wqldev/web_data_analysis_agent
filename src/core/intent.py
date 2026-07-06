"""分析意图识别（与 agent-loop 路由一致）。"""

from __future__ import annotations

import re
from typing import Literal

AnalysisType = Literal["trend", "compare", "attribution", "segment", "hypothesis", "general"]

_PATTERNS: list[tuple[AnalysisType, re.Pattern[str], str]] = [
    ("compare", re.compile(r"同比|环比|对比|哪个.{0,20}(更好|更高|最高|更低)|排名|Top|TOP|前三|后三|差距", re.I), "对比型"),
    ("trend", re.compile(r"趋势|涨|跌|走势|近.{0,6}(月|年|半年|季度)|波动|异常|预测|季节性|拐点|生命周期|销售情况", re.I), "趋势型"),
    ("attribution", re.compile(r"为什么|原因|因素|影响|导致|问题出|归因|下降|下滑", re.I), "归因型"),
    (
        "segment",
        re.compile(
            r"分群|分几类|画像|客户类型|VIP|年龄段|高价值|沉睡|复购|流失|"
            r"哪些.{0,10}(用户|客户)|用户.{0,10}(特征|流失)|客户.{0,10}(特征|流失)|"
            r"最容易.{0,6}流失|潜在.{0,6}客户",
            re.I,
        ),
        "分群型",
    ),
    ("hypothesis", re.compile(r"如果|能不能|会不会|假设|要是|值不值得|提升多少|降低多少", re.I), "假设型"),
    ("general", re.compile(r"分析|统计|汇总|洞察|报表|指标|销售|订单|转化|复购|留存|活跃|流失率", re.I), "通用分析"),
]


# ── 信息查询（不经过 agent-loop，直连 MySQL 返回） ──
_INFO_TABLE_PATTERNS = [
    re.compile(r"有哪.{0,6}表|哪些表|表列表|表名|有什么表|所有表|展示表|列出.*表", re.I),
    re.compile(r"show\s+tables|list\s+tables", re.I),
]

_INFO_DESC_PATTERNS = [
    (re.compile(r"(.{1,32})表.{0,6}(结构|字段|列|有哪些列|有哪些字段|描述|describe)", re.I), 1),
    (re.compile(r"(describe|desc|show\s+columns|show\s+create\s+table)\s+`?(\w+)`?", re.I), 2),
]

InfoQueryType = Literal["list_tables", "describe_table", ""]

# Web 端数据库写操作 / DDL 拦截（database-security.mdc）
DDL_BLOCKED_MESSAGE = (
    "这是禁止行为！！！修改数据库是不允许的，如有任何问题请联系数据库管理员"
)

_DDL_PATTERNS: list[re.Pattern[str]] = [
    re.compile(
        r"\b(drop|create|alter|truncate|insert|update|delete|grant|revoke|replace)\b",
        re.I,
    ),
    re.compile(r"删(除|掉|除掉).{0,24}表|删除.{0,20}表|删表|清空.{0,12}表", re.I),
    re.compile(r"创建.{0,12}表|建表|新建.{0,12}表|修改.{0,12}表|更新.{0,12}表|改表结构", re.I),
    re.compile(r"数据库.{0,12}(删|写|改|创建|清空)|写操作|DDL", re.I),
]


def is_ddl_request(text: str) -> bool:
    """Web 用户输入含 DDL/写操作意图时返回 True，须固定拒绝文案。"""
    content = text.strip()
    if not content:
        return False
    return any(p.search(content) for p in _DDL_PATTERNS)

def classify_info_query(text: str) -> tuple[InfoQueryType, str]:
    """判断是否为简单的数据库信息查询，返回 (类型, 表名)。表名为空表示只需要表列表。"""
    content = text.strip()
    for p in _INFO_TABLE_PATTERNS:
        if p.search(content):
            return "list_tables", ""
    for p, group_idx in _INFO_DESC_PATTERNS:
        m = p.search(content)
        if m:
            table = m.group(group_idx).strip().lower()
            if re.match(r"^[a-z0-9_]+$", table):
                return "describe_table", table
    return "", ""


def classify_intent(text: str) -> tuple[AnalysisType, str] | None:
    """识别分析意图。不匹配任何分析模式时返回 None，不走 agent-loop。"""
    content = text.strip()
    for category, pattern, label in _PATTERNS:
        if pattern.search(content):
            return category, label
    return None
