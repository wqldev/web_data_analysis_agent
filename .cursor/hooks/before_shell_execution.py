#!/usr/bin/env python3
"""beforeShellExecution：危险 Shell 命令拦截或提醒。"""

from __future__ import annotations

import json
import re
import sys

from guard_common import append_mcp_guard_log, read_hook_payload

SHELL_DENY_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"rm\s+-rf", re.I), "强制递归删除（rm -rf）"),
    (re.compile(r"del\s+/[fqsb].*\/s", re.I), "Windows 强制递归删除"),
    (re.compile(r"format\s+[a-z]:", re.I), "磁盘格式化"),
    (re.compile(r"mkfs\.", re.I), "磁盘格式化（mkfs）"),
    (re.compile(r"dd\s+if=", re.I), "磁盘裸写（dd）"),
    (re.compile(r":\(\)\s*\{\s*:\|:&\s*\};:", re.I), "Fork 炸弹"),
]

SHELL_ASK_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"mysql\b.*\b(drop|truncate|delete|update|insert)\b", re.I), "MySQL 写/删操作"),
    (re.compile(r"\b(drop|truncate)\s+table\b", re.I), "删表 SQL"),
    (re.compile(r"git\s+push\s+.*--force", re.I), "Git 强制推送"),
    (re.compile(r"git\s+reset\s+--hard", re.I), "Git 硬重置"),
]


def _extract_command(payload: dict) -> str:
    for key in ("command", "cmd", "shell_command", "script"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _check_command(command: str) -> tuple[str, str] | None:
    if not command:
        return None
    for pattern, reason in SHELL_DENY_PATTERNS:
        if pattern.search(command):
            return "deny", reason
    for pattern, reason in SHELL_ASK_PATTERNS:
        if pattern.search(command):
            return "ask", reason
    return None


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
    payload = read_hook_payload()
    command = _extract_command(payload)

    verdict = _check_command(command)
    if verdict:
        decision, reason = verdict
        append_mcp_guard_log(
            decision=decision,
            reason=reason,
            server="shell",
            tool_name="shell_command",
            detail=command,
        )
        if decision == "deny":
            _respond(
                "deny",
                f"已拦截危险 Shell 命令：{reason}。",
                f"Hook 拦截 Shell：{reason}。命令：{command}",
            )
            return 0
        _respond(
            "ask",
            f"检测到潜在风险 Shell 命令：{reason}。请确认是否继续。",
            f"Hook 提醒 Shell：{reason}。命令：{command}",
        )
        return 0

    append_mcp_guard_log(
        decision="allow",
        reason="passed",
        server="shell",
        tool_name="shell_command",
        detail=command[:500],
    )
    _respond("allow", "", "")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
