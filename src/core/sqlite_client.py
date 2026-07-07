"""SQLite 数据库客户端（替换 mysql_client）。"""

from __future__ import annotations

import json
import os
import re
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any

_WRITE_PATTERN = re.compile(
    r"^\s*(INSERT|UPDATE|DELETE|DROP|ALTER|CREATE|TRUNCATE|REPLACE|GRANT|REVOKE)\b",
    re.IGNORECASE,
)

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DB_PATH = ROOT / "data" / "data.db"


def _get_db_path() -> str:
    return os.getenv("DATA_DB_PATH", str(DEFAULT_DB_PATH))


def _allow_writes() -> bool:
    return os.getenv("DATA_ALLOW_WRITES", "false").lower() in ("1", "true", "yes")


@contextmanager
def get_connection():
    db_path = _get_db_path()
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


def _format_result(rows: list[sqlite3.Row]) -> str:
    return json.dumps([dict(r) for r in rows], ensure_ascii=False, indent=2, default=str)


def test_connection() -> dict[str, Any]:
    db_path = _get_db_path()
    with get_connection() as conn:
        cursor = conn.execute("SELECT sqlite_version() AS version")
        row = cursor.fetchone()
    return {
        "status": "ok",
        "message": "SQLite 连接成功",
        "database": str(Path(db_path).name),
        "db_path": db_path,
        "version": row["version"],
    }


def list_tables() -> list[str]:
    with get_connection() as conn:
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        )
        rows = cursor.fetchall()
    return [r["name"] for r in rows]


def describe_table(table_name: str) -> list[dict[str, Any]]:
    if not re.match(r"^[A-Za-z0-9_]+$", table_name):
        raise ValueError("表名只能包含字母、数字和下划线")
    with get_connection() as conn:
        cursor = conn.execute(f'PRAGMA table_info("{table_name}")')
        rows = cursor.fetchall()
    return [
        {
            "Field": r["name"],
            "Type": r["type"],
            "Null": "YES" if r["notnull"] == 0 else "NO",
            "Key": "PRI" if r["pk"] else "",
            "Default": r["dflt_value"],
        }
        for r in rows
    ]


def _convert_mysql_sql(query: str) -> str:
    """将 MySQL 特有 SQL 语法转换为 SQLite 兼容语法。"""
    # DATE_FORMAT(date, '%Y-%m') -> strftime('%Y-%m', date)
    query = re.sub(
        r"DATE_FORMAT\s*\(\s*([^,]+)\s*,\s*'([^']*)'\s*\)",
        r"strftime('\2', \1)",
        query,
        flags=re.I,
    )
    # DATE_SUB(date, INTERVAL N MONTH) -> date(date, '-N months')
    query = re.sub(
        r"DATE_SUB\s*\(\s*([^,]+)\s*,\s*INTERVAL\s+(\d+)\s+(MONTH|DAY|YEAR)\s*\)",
        lambda m: f"date({m.group(1)}, '-{m.group(2)} {m.group(3).lower()}s')"
        if m.group(3).upper() in ("MONTH", "DAY", "YEAR")
        else f"date({m.group(1)}, '-{m.group(2)} {m.group(3).lower()}')",
        query,
        flags=re.I,
    )
    # DATEDIFF(d1, d2) -> CAST(julianday(d1) - julianday(d2) AS INTEGER)
    query = re.sub(
        r"DATEDIFF\s*\(\s*([^,]+)\s*,\s*([^)]+)\s*\)",
        r"CAST(julianday(\1) - julianday(\2) AS INTEGER)",
        query,
        flags=re.I,
    )
    # COALESCE -> IFNULL for older SQLite (but COALESCE works in 3.8.3+, keeping it)
    # Remove MySQL specific backtick quoting but keep for safety
    # Convert CONCAT
    query = re.sub(
        r"CONCAT\s*\(([^)]+)\)",
        lambda m: m.group(0),  # SQLite doesn't have CONCAT, use ||
        query,
        flags=re.I,
    )
    return query


def execute_query(query: str) -> list[dict[str, Any]]:
    query = query.strip()
    if not query:
        raise ValueError("SQL 不能为空")
    if not _allow_writes() and _WRITE_PATTERN.match(query):
        raise ValueError("当前为只读模式，不允许执行写操作。")
    query = _convert_mysql_sql(query)
    with get_connection() as conn:
        cursor = conn.execute(query)
        if cursor.description:
            rows = cursor.fetchall()
            return [dict(r) for r in rows]
        conn.commit()
        return [{"affected_rows": cursor.rowcount, "message": "执行成功"}]
