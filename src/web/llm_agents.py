"""Web 端三 Agent 的 LLM 实现（使用 model_config 中的自定义模型）。"""

from __future__ import annotations

import json
import re
from typing import Any

from core import sqlite_client
from core.intent import AnalysisType
from core.llm_client import chat_completion
from core.model_config import get_model

_READONLY_SQL = re.compile(r"^\s*(SELECT|WITH|SHOW|DESCRIBE|PRAGMA)\b", re.I)
_JSON_BLOCK = re.compile(r"```(?:json)?\s*([\s\S]*?)```", re.I)


def _extract_json(text: str) -> dict[str, Any]:
    text = text.strip()
    for candidate in (text,):
        try:
            parsed = json.loads(candidate)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            pass
    match = _JSON_BLOCK.search(text)
    if match:
        parsed = json.loads(match.group(1).strip())
        if isinstance(parsed, dict):
            return parsed
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        parsed = json.loads(text[start : end + 1])
        if isinstance(parsed, dict):
            return parsed
    raise ValueError("LLM 未返回有效 JSON")


def _validate_readonly_sql(sql: str) -> str:
    cleaned = sql.strip().rstrip(";")
    if not cleaned:
        raise ValueError("SQL 为空")
    if not _READONLY_SQL.match(cleaned):
        raise ValueError(f"仅允许只读 SQL，拒绝: {cleaned[:80]}")
    return cleaned


def gather_schema_context(max_tables: int = 8, sample_rows: int = 2) -> str:
    tables = sqlite_client.list_tables()
    if not tables:
        return "数据库当前无可用表。"

    lines = [f"共 {len(tables)} 张表: {', '.join(tables)}"]
    for table in tables[:max_tables]:
        cols = sqlite_client.describe_table(table)
        col_desc = ", ".join(f"{c['Field']}({c['Type']})" for c in cols[:12])
        lines.append(f"\n### 表 `{table}`\n字段: {col_desc}")
        try:
            rows = sqlite_client.execute_query(f'SELECT * FROM "{table}" LIMIT {sample_rows}')
            if rows:
                lines.append("样例: " + json.dumps(rows, ensure_ascii=False, default=str))
        except Exception as exc:
            lines.append(f"样例读取失败: {exc}")
    return "\n".join(lines)


def default_tasks_spec(type_label: str) -> list[dict[str, Any]]:
    return [
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
            "description": "严格按六节模板撰写中文报告",
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
                "对照六节报告完整性",
            ],
            "assignee": "verifier-agent",
        },
    ]


def planner_plan(
    requirement: str,
    analysis_type: AnalysisType,
    type_label: str,
    schema_context: str,
) -> dict[str, Any]:
    """planner-agent：拆解任务与验收标准。"""
    prompt = f"""你是 planner-agent，负责将数据分析需求拆解为 T1~T4 任务。

用户需求：{requirement}
分析类型：{type_label}（{analysis_type}）

数据库结构：
{schema_context}

请输出 JSON（不要其他文字）：
{{
  "project": "分析项目名称",
  "analysis_type": "{type_label}",
  "analysis_notes": "规划说明（中文，2-4句）",
  "tasks": [
    {{
      "task_id": "T1",
      "title": "...",
      "description": "...",
      "acceptance_criteria": ["..."],
      "assignee": "builder-agent"
    }},
    ... T2, T3 给 builder-agent, T4 给 verifier-agent
  ]
}}

约束：
- T1 探库确认字段；T2 只读 SQL 汇总；T3 六节报告；T4 独立验收
- acceptance_criteria 必须具体可检查
- 全部中文"""
    raw = chat_completion(
        [
            {"role": "system", "content": "你是数据分析规划专家，只输出合法 JSON。"},
            {"role": "user", "content": prompt},
        ],
        temperature=0.3,
    )
    data = _extract_json(raw)
    tasks = data.get("tasks") or default_tasks_spec(type_label)
    for spec in tasks:
        spec.setdefault("assignee", "builder-agent")
        if spec.get("task_id") == "T4":
            spec["assignee"] = "verifier-agent"
    return {
        "project": data.get("project") or requirement,
        "analysis_type": data.get("analysis_type") or type_label,
        "analysis_category": analysis_type,
        "analysis_notes": data.get("analysis_notes", ""),
        "tasks": tasks,
    }


def builder_explore(
    requirement: str,
    type_label: str,
    schema_context: str,
    plan_notes: str,
) -> str:
    """builder-agent T1：数据源与字段确认。"""
    prompt = f"""你是 builder-agent，执行 T1 数据探查。

用户问题：{requirement}
分析类型：{type_label}
规划说明：{plan_notes}

数据库结构：
{schema_context}

请用中文 Markdown 输出【T1 数据源与字段确认】，包含：
- 探库结果（表清单摘要）
- 目标表及 JOIN 关系
- 时间范围口径
- 日期/金额/去重字段
- 分析类型与关键假设
不要编造不存在的表或字段。"""
    return chat_completion(
        [
            {"role": "system", "content": "你是数据分析师，基于给定 schema 做探库结论，禁止编造表结构。"},
            {"role": "user", "content": prompt},
        ],
        temperature=0.2,
    )


def builder_queries(
    requirement: str,
    analysis_type: AnalysisType,
    type_label: str,
    t1_content: str,
    schema_context: str,
) -> list[dict[str, str]]:
    """builder-agent T2：生成只读 SQL 列表。"""
    prompt = f"""你是 builder-agent，为 SQLite 数据库编写只读分析 SQL。

用户问题：{requirement}
分析类型：{type_label}（{analysis_type}）

T1 探库结论：
{t1_content}

数据库结构：
{schema_context}

输出 JSON（不要其他文字）：
{{
  "queries": [
    {{"name": "kpi_summary", "purpose": "关键指标汇总", "sql": "SELECT ..."}},
    {{"name": "detail_breakdown", "purpose": "维度/趋势明细", "sql": "SELECT ..."}}
  ]
}}

约束：
- 仅 SELECT 或 WITH...SELECT，禁止写操作
- 使用 SQLite 语法（strftime 代替 DATE_FORMAT）
- 至少 2 条查询：1 条 KPI 汇总 + 1 条明细
- SQL 必须可执行，表名/字段名必须来自 schema"""
    raw = chat_completion(
        [
            {"role": "system", "content": "你是 SQL 专家，只输出合法 JSON，SQL 必须兼容 SQLite。"},
            {"role": "user", "content": prompt},
        ],
        temperature=0.2,
        max_tokens=3000,
    )
    data = _extract_json(raw)
    queries = data.get("queries") or []
    if not queries:
        raise ValueError("LLM 未生成任何 SQL 查询")
    validated: list[dict[str, str]] = []
    for item in queries[:5]:
        sql = _validate_readonly_sql(str(item.get("sql", "")))
        validated.append(
            {
                "name": str(item.get("name") or f"query_{len(validated) + 1}"),
                "purpose": str(item.get("purpose") or ""),
                "sql": sql,
            }
        )
    return validated


def execute_queries(queries: list[dict[str, str]]) -> tuple[dict[str, Any], str]:
    """执行 LLM 生成的 SQL，返回结构化结果与 T2 文本。"""
    results: dict[str, Any] = {"queries": []}
    lines = ["【T2 LLM 汇总 SQL 结果】", ""]
    for item in queries:
        name = item["name"]
        sql = item["sql"]
        purpose = item.get("purpose", "")
        try:
            rows = sqlite_client.execute_query(sql)
            entry = {"name": name, "purpose": purpose, "sql": sql, "rows": rows, "error": None}
            preview = json.dumps(rows[:20], ensure_ascii=False, indent=2, default=str)
            lines.append(f"### {name} — {purpose}")
            lines.append(f"```sql\n{sql}\n```")
            lines.append(f"结果（前 20 行）:\n```json\n{preview}\n```\n")
        except Exception as exc:
            entry = {"name": name, "purpose": purpose, "sql": sql, "rows": [], "error": str(exc)}
            lines.append(f"### {name} — 执行失败")
            lines.append(f"错误: {exc}\n")
        results["queries"].append(entry)
    return results, "\n".join(lines)


def builder_report(
    requirement: str,
    type_label: str,
    analysis_type: AnalysisType,
    t1_content: str,
    t2_content: str,
    t2_data: dict[str, Any],
    plan_notes: str = "",
) -> str:
    """builder-agent T3：撰写六节 Markdown 报告。"""
    data_json = json.dumps(t2_data, ensure_ascii=False, indent=2, default=str)[:12000]
    prompt = f"""你是 builder-agent，基于真实查询结果撰写数据分析报告。

用户问题：{requirement}
分析类型：{type_label}（{analysis_type}）
规划说明：{plan_notes}

T1 探库：
{t1_content}

T2 查询与结果：
{t2_content}

结构化数据（JSON 摘要）：
{data_json}

严格按以下六节输出完整 Markdown 报告（标题用 ## 1. 分析概要 格式）：
## 1. 分析概要
## 2. 核心结论（3~5 条 bullet）
## 3. 关键指标（至少 3 行 KPI 表格：| 指标 | 数值 | 说明 |）
## 4. 详细分析（至少 1 张表 + 解读）
## 5. 业务建议（2~4 条）
## 6. 数据说明与局限

约束：
- 数字必须来自 T2 查询结果，不得编造
- 若某查询失败，在第 6 节说明局限
- 全部中文"""
    return chat_completion(
        [
            {"role": "system", "content": "你是资深数据分析师，报告结构固定六节，数据必须可追溯。"},
            {"role": "user", "content": prompt},
        ],
        temperature=0.5,
        max_tokens=6000,
    )


def verifier_check(
    requirement: str,
    report: str,
    plan: dict[str, Any],
) -> dict[str, Any]:
    """verifier-agent：验收报告。"""
    tasks_json = json.dumps(plan.get("tasks", []), ensure_ascii=False, indent=2)[:8000]
    prompt = f"""你是 verifier-agent，独立验收 builder 的分析报告。

用户需求：{requirement}

任务与验收标准：
{tasks_json}

报告正文：
{report[:12000]}

输出 JSON（不要其他文字）：
{{
  "passed": true,
  "summary": "验收摘要（中文）",
  "structure_checks": [
    {{"section": "1 分析概要", "passed": true, "evidence": "..."}}
  ],
  "fix_items": [],
  "report_task_id": "T3"
}}

验收规则：
- 六节齐全（1~6）
- 第 2 节至少 3 条结论
- 第 3 节 KPI 表至少 3 行
- 数字与口径合理、无明显编造
- 任一不满足则 passed=false 且 fix_items 具体列出问题"""
    raw = chat_completion(
        [
            {"role": "system", "content": "你是严格的数据分析验收员，只输出合法 JSON。"},
            {"role": "user", "content": prompt},
        ],
        temperature=0.2,
    )
    data = _extract_json(raw)
    data.setdefault("passed", False)
    data.setdefault("summary", "验收完成")
    data.setdefault("structure_checks", [])
    data.setdefault("fix_items", [])
    data.setdefault("rework_rounds_used", 0)
    data.setdefault("report_task_id", "T3")
    return data


def llm_status_line() -> str:
    return f"使用模型: {get_model()}"
