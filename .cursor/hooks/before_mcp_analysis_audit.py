#!/usr/bin/env python3
"""beforeMCPExecution：审计 MySQL 只读查询并写入 analysis-query.log。"""

from __future__ import annotations

import json
import sys
import traceback

from analysis_common import append_analysis_query_log, extract_sql_metadata
from guard_common import append_hook_debug, read_hook_payload

MYSQL_SERVER_HINTS = ("mysql", "mysql-local")
READONLY_PREFIX = ("SELECT", "SHOW", "DESCRIBE", "EXPLAIN", "WITH")


def _extract_tool_info(payload: dict) -> tuple[str, str, dict]:
    server = str(
        payload.get("server")
        or payload.get("server_name")
        or payload.get("mcp_server")
        or payload.get("provider")
        or "unknown"
    )
    tool_name = str(
        payload.get("tool_name")
        or payload.get("name")
        or payload.get("tool")
        or "unknown"
    )

    arguments: dict = {}
    for key in ("tool_input", "arguments", "input", "params"):
        value = payload.get(key)
        if isinstance(value, dict):
            arguments = value
            break
    return server, tool_name, arguments


def _extract_query(arguments: dict) -> str:
    for key in ("query", "sql", "statement"):
        value = arguments.get(key)
        if isinstance(value, str):
            return value.strip()
    return ""


def _is_mysql_readonly_query(server: str, tool_name: str, query: str) -> bool:
    if tool_name not in ("execute_query", "describe_table", "list_tables"):
        return False
    if not any(hint in server.lower() for hint in MYSQL_SERVER_HINTS):
        return False
    if tool_name in ("describe_table", "list_tables"):
        return True
    upper = query.lstrip().upper()
    return upper.startswith(READONLY_PREFIX)


def main() -> int:
    try:
        payload = read_hook_payload()
        server, tool_name, arguments = _extract_tool_info(payload)
        query = _extract_query(arguments)

        if _is_mysql_readonly_query(server, tool_name, query):
            metadata = extract_sql_metadata(query or tool_name)
            append_analysis_query_log(
                server=server,
                tool_name=tool_name,
                query_kind=metadata["query_kind"],
                tables=metadata["tables"],
                query=query or json.dumps(arguments, ensure_ascii=False),
            )

        print(json.dumps({"permission": "allow"}, ensure_ascii=False))
        sys.stdout.flush()
        return 0
    except Exception:
        append_hook_debug(f"beforeMcpAnalysisAudit error:\n{traceback.format_exc()}")
        print(json.dumps({"permission": "allow"}, ensure_ascii=False))
        sys.stdout.flush()
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
