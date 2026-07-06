"""Hook 公共模块：危险意图检测与 mcp-guard 日志。"""

from __future__ import annotations

import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

CHINA_TZ = ZoneInfo("Asia/Shanghai")

USER_QUERY_PATTERN = re.compile(r"<user_query>\s*(.*?)\s*</user_query>", re.DOTALL)

WRITE_SQL_PATTERN = re.compile(
    r"\b(INSERT|UPDATE|DELETE|DROP|ALTER|CREATE|TRUNCATE|REPLACE|GRANT|REVOKE)\b",
    re.IGNORECASE,
)

DENY_SQL_PATTERN = re.compile(
    r"\b(DROP|TRUNCATE)\b",
    re.IGNORECASE,
)

ASK_SQL_PATTERN = re.compile(
    r"\b(INSERT|UPDATE|DELETE|ALTER|CREATE|REPLACE|GRANT|REVOKE)\b",
    re.IGNORECASE,
)

READONLY_SQL_PREFIX = re.compile(
    r"^\s*(SELECT|SHOW|DESCRIBE|EXPLAIN|WITH)\b",
    re.IGNORECASE,
)

NL_DANGER_PATTERNS: list[tuple[re.Pattern[str], str, str]] = [
    (re.compile(r"drop\s+table", re.I), "deny", "自然语言/SQL：删表（DROP TABLE）"),
    (re.compile(r"truncate\s+table", re.I), "deny", "自然语言/SQL：清空表（TRUNCATE）"),
    (re.compile(r"删除.{0,80}表", re.I), "deny", "自然语言：删除数据表"),
    (re.compile(r"删掉.{0,80}表", re.I), "deny", "自然语言：删除数据表"),
    (re.compile(r"drop\s+\S+", re.I), "deny", "自然语言/SQL：DROP 操作"),
    (
        re.compile(r"\b(delete|update|insert|alter|create)\b", re.I),
        "ask",
        "自然语言/SQL：数据库写操作",
    ),
    (re.compile(r"rm\s+-rf", re.I), "deny", "自然语言/SQL：强制递归删除"),
]


def project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def log_dir() -> Path:
    path = project_root() / ".cursor" / "hooks" / "logs"
    path.mkdir(parents=True, exist_ok=True)
    return path


def read_hook_payload() -> dict:
    """从 stdin 读取 hook JSON；兼容 Windows BOM / 编码损坏 / 空输入。"""
    try:
        data = sys.stdin.buffer.read()
    except Exception:
        data = b""

    read_hook_payload.last_len = len(data)  # type: ignore[attr-defined]
    read_hook_payload.last_preview = data[:120]  # type: ignore[attr-defined]

    if not data:
        return {}

    text = data.decode("utf-8-sig", errors="replace").strip()
    if not text:
        return {}

    try:
        parsed = json.loads(text)
        return parsed if isinstance(parsed, dict) else {}
    except json.JSONDecodeError:
        return {}


def _prompt_from_payload(payload: dict) -> str:
    for key in ("prompt", "message", "text", "content", "user_message", "input"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    for value in payload.values():
        if isinstance(value, dict):
            nested = _prompt_from_payload(value)
            if nested:
                return nested
    return ""


def _prompt_looks_valid(prompt: str) -> bool:
    if not prompt.strip():
        return False
    if prompt.count("\ufffd") > max(1, len(prompt) // 4):
        return False
    if len(prompt) > 4 and prompt.count("?") > len(prompt) // 2:
        return False
    return True


def parse_last_user_prompt(transcript_path: str | Path) -> str:
    """从 Cursor JSONL transcript 读取最后一条 user 消息。"""
    path = Path(transcript_path)
    if not path.is_file():
        return ""

    last_prompt = ""
    try:
        with path.open(encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if record.get("role") != "user":
                    continue
                content = record.get("message", {}).get("content", [])
                if not isinstance(content, list):
                    continue
                for block in content:
                    if not isinstance(block, dict) or block.get("type") != "text":
                        continue
                    text = str(block.get("text") or "")
                    match = USER_QUERY_PATTERN.search(text)
                    if match:
                        last_prompt = match.group(1).strip()
                    elif text.strip():
                        last_prompt = text.strip()
    except OSError:
        return ""
    return last_prompt


def resolve_user_prompt(payload: dict) -> tuple[str, str]:
    """解析用户 prompt，stdin 失败或损坏时回退 transcript。"""
    stdin_prompt = _prompt_from_payload(payload)
    if _prompt_looks_valid(stdin_prompt):
        return stdin_prompt, "stdin"

    transcript = (
        payload.get("transcript_path")
        or os.environ.get("CURSOR_TRANSCRIPT_PATH")
        or ""
    )
    if transcript:
        transcript_prompt = parse_last_user_prompt(transcript)
        if _prompt_looks_valid(transcript_prompt):
            return transcript_prompt, "transcript"

    if stdin_prompt:
        return stdin_prompt, "stdin-corrupt"
    return "", "empty"


def _safe_text(text: str) -> str:
    return text.encode("utf-8", errors="replace").decode("utf-8")


def append_mcp_guard_log(
    decision: str,
    reason: str,
    server: str,
    tool_name: str,
    detail: str,
) -> None:
    log_file = log_dir() / "mcp-guard.log"
    timestamp = datetime.now(CHINA_TZ).strftime("%Y-%m-%d %H:%M:%S")
    safe_detail = _safe_text(detail).replace("\n", " ").replace("\t", " ")[:500]
    safe_reason = _safe_text(reason)
    line = f"{timestamp}\t{decision}\t{safe_reason}\t{server}\t{tool_name}\t{safe_detail}\n"
    with log_file.open("a", encoding="utf-8") as handle:
        handle.write(line)


def append_hook_debug(message: str) -> None:
    log_file = log_dir() / "hook-debug.log"
    timestamp = datetime.now(CHINA_TZ).strftime("%Y-%m-%d %H:%M:%S")
    safe_message = _safe_text(message).replace("\n", " | ").replace("\t", " ")[:1000]
    line = f"{timestamp}\t{safe_message}\n"
    with log_file.open("a", encoding="utf-8") as handle:
        handle.write(line)


def check_sql_text(text: str) -> tuple[str, str] | None:
    query = text.strip()
    if not query:
        return None
    if DENY_SQL_PATTERN.search(query):
        return "deny", "数据库破坏性写操作（DROP/TRUNCATE）"
    if ASK_SQL_PATTERN.search(query) and not READONLY_SQL_PREFIX.search(query):
        return "ask", "数据库写操作"
    if WRITE_SQL_PATTERN.search(query) and not READONLY_SQL_PREFIX.search(query):
        return "ask", "数据库写操作"
    return None


def check_user_text(text: str) -> tuple[str, str] | None:
    content = text.strip()
    if not content:
        return None

    sql_verdict = check_sql_text(content)
    if sql_verdict:
        decision, reason = sql_verdict
        return decision, f"用户输入含 SQL：{reason}"

    for pattern, decision, reason in NL_DANGER_PATTERNS:
        if pattern.search(content):
            return decision, reason
    return None
