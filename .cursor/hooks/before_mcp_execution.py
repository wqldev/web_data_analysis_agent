#!/usr/bin/env python3
"""beforeMCPExecution：MCP 工具调用前拦截或提醒危险操作。"""

from __future__ import annotations

import json
import sys

from guard_common import append_mcp_guard_log, check_sql_text, read_hook_payload


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


def _respond(permission: str, user_message: str, agent_message: str) -> None:
    print(
        json.dumps(
            {
                "permission": permission,
                "user_message": user_message,
                "agent_message": agent_message,
            },
            ensure_ascii=False,
        )
    )


def main() -> int:
    payload: dict = read_hook_payload()
    server, tool_name, arguments = _extract_tool_info(payload)
    detail = json.dumps(arguments, ensure_ascii=False)[:500]

    if tool_name == "execute_query":
        query = _extract_query(arguments)
        verdict = check_sql_text(query)
        if verdict:
            decision, reason = verdict
            append_mcp_guard_log(
                decision=decision,
                reason=reason,
                server=server,
                tool_name=tool_name,
                detail=query or detail,
            )
            if decision == "deny":
                _respond(
                    "deny",
                    f"已拦截 MCP 危险操作：{reason}。请在 MySQL 客户端自行执行。",
                    f"Hook 拦截 MCP {server}/{tool_name}：{reason}。SQL：{query}",
                )
                return 0
            _respond(
                "ask",
                f"检测到 MCP 潜在风险：{reason}。请确认是否继续。",
                f"Hook 提醒 MCP {server}/{tool_name}：{reason}。SQL：{query}",
            )
            return 0

    append_mcp_guard_log(
        decision="allow",
        reason="passed",
        server=server,
        tool_name=tool_name,
        detail=detail,
    )
    _respond("allow", "", "")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
