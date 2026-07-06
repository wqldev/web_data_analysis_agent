"""MySQL 只读查询客户端（Web 与 MCP 共用逻辑）。"""

from __future__ import annotations

import json
import os
import re
from contextlib import contextmanager
from typing import Any

import pymysql
from pymysql.cursors import DictCursor

_WRITE_PATTERN = re.compile(
    r"^\s*(INSERT|UPDATE|DELETE|DROP|ALTER|CREATE|TRUNCATE|REPLACE|GRANT|REVOKE)\b",
    re.IGNORECASE,
)


def _get_db_config() -> dict[str, Any]:
    return {
        "host": os.getenv("MYSQL_HOST", "localhost"),
        "port": int(os.getenv("MYSQL_PORT", "3306")),
        "user": os.getenv("MYSQL_USER", "root"),
        "password": os.getenv("MYSQL_PASSWORD", ""),
        "database": os.getenv("MYSQL_DATABASE", ""),
        "charset": "utf8mb4",
        "cursorclass": DictCursor,
    }


def _allow_writes() -> bool:
    return os.getenv("MYSQL_ALLOW_WRITES", "false").lower() in ("1", "true", "yes")


@contextmanager
def get_connection():
    conn = pymysql.connect(**_get_db_config())
    try:
        yield conn
    finally:
        conn.close()


def _format_result(rows: list[dict[str, Any]]) -> str:
    return json.dumps(rows, ensure_ascii=False, indent=2, default=str)


def test_connection() -> dict[str, Any]:
    config = _get_db_config()
    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute("SELECT VERSION() AS version, DATABASE() AS current_database")
            row = cursor.fetchone()
    return {
        "status": "ok",
        "message": "MySQL 连接成功",
        "host": config["host"],
        "port": config["port"],
        "user": config["user"],
        "database": config["database"],
        "version": row["version"],
        "current_database": row["current_database"],
    }


def list_tables() -> list[str]:
    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute("SHOW TABLES")
            rows = cursor.fetchall()
    table_key = f"Tables_in_{_get_db_config()['database']}"
    return [row[table_key] for row in rows]


def describe_table(table_name: str) -> list[dict[str, Any]]:
    if not re.match(r"^[A-Za-z0-9_]+$", table_name):
        raise ValueError("表名只能包含字母、数字和下划线")
    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(f"DESCRIBE `{table_name}`")
            return cursor.fetchall()


def execute_query(query: str) -> list[dict[str, Any]]:
    query = query.strip()
    if not query:
        raise ValueError("SQL 不能为空")
    if not _allow_writes() and _WRITE_PATTERN.match(query):
        raise ValueError("当前为只读模式，不允许执行写操作。")
    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(query)
            if cursor.description:
                return cursor.fetchall()
            conn.commit()
            return [{"affected_rows": cursor.rowcount, "message": "执行成功"}]
