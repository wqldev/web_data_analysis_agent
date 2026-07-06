"""本地 MySQL MCP 服务，通过 stdio 与 Cursor 通信。"""

from __future__ import annotations

import json
import os
import re
from contextlib import contextmanager
from typing import Any

import pymysql
from mcp.server.fastmcp import FastMCP
from pymysql.cursors import DictCursor

mcp = FastMCP("mysql-local")

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


@mcp.tool()
def test_connection() -> str:
    """测试 MySQL 数据库连接是否正常。"""
    config = _get_db_config()
    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute("SELECT VERSION() AS version, DATABASE() AS current_database")
            row = cursor.fetchone()
    return json.dumps(
        {
            "status": "ok",
            "message": "MySQL 连接成功",
            "host": config["host"],
            "port": config["port"],
            "user": config["user"],
            "database": config["database"],
            "version": row["version"],
            "current_database": row["current_database"],
        },
        ensure_ascii=False,
        indent=2,
    )


@mcp.tool()
def list_tables() -> str:
    """列出当前数据库中的所有表。"""
    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute("SHOW TABLES")
            rows = cursor.fetchall()
    table_key = f"Tables_in_{_get_db_config()['database']}"
    tables = [row[table_key] for row in rows]
    return json.dumps({"tables": tables, "count": len(tables)}, ensure_ascii=False, indent=2)


@mcp.tool()
def describe_table(table_name: str) -> str:
    """查看指定表的结构（字段、类型、键等）。"""
    if not re.match(r"^[A-Za-z0-9_]+$", table_name):
        raise ValueError("表名只能包含字母、数字和下划线")

    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(f"DESCRIBE `{table_name}`")
            rows = cursor.fetchall()
    return _format_result(rows)


@mcp.tool()
def execute_query(query: str) -> str:
    """执行 SQL 查询。默认仅允许 SELECT/SHOW/DESCRIBE/EXPLAIN 等只读语句。"""
    query = query.strip()
    if not query:
        raise ValueError("SQL 不能为空")

    if not _allow_writes() and _WRITE_PATTERN.match(query):
        raise ValueError(
            "当前为只读模式（MYSQL_ALLOW_WRITES=false），不允许执行写操作。"
            "如需写入，请在 mcp.json 中将 MYSQL_ALLOW_WRITES 设为 true。"
        )

    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(query)
            if cursor.description:
                rows = cursor.fetchall()
                return _format_result(rows)
            conn.commit()
            return json.dumps(
                {"affected_rows": cursor.rowcount, "message": "执行成功"},
                ensure_ascii=False,
                indent=2,
            )


if __name__ == "__main__":
    mcp.run(transport="stdio")
