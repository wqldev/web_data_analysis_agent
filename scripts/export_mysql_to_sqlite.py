"""将 MySQL 数据导出到 SQLite .db 文件。"""
import sqlite3
import re
from decimal import Decimal

import pymysql
from pymysql.cursors import DictCursor

MYSQL_CONFIG = {
    "host": "localhost",
    "port": 3306,
    "user": "root",
    "password": "123456",
    "database": "mysql_dataset_test",
}

DB_PATH = r"C:\Users\10512\Desktop\web_agent\data\data.db"


def mysql_type_to_sqlite(col_type: str) -> str:
    t = col_type.lower().strip()
    if "int" in t:
        return "INTEGER"
    if "decimal" in t or "float" in t or "double" in t or "numeric" in t or "real" in t:
        return "REAL"
    return "TEXT"


def split_column_definitions(cols_section: str) -> list[str]:
    """Split column definitions respecting nested parentheses."""
    parts = []
    current = ""
    depth = 0
    for ch in cols_section:
        if ch == "(":
            depth += 1
            current += ch
        elif ch == ")":
            depth -= 1
            current += ch
        elif ch == "," and depth == 0:
            parts.append(current.strip())
            current = ""
        else:
            current += ch
    if current.strip():
        parts.append(current.strip())
    return parts


def clean_line(line: str) -> str:
    """Clean a MySQL column definition line for SQLite."""
    line = line.replace("`", '"')

    # Remove MySQL-specific keywords
    line = re.sub(r"\s+AUTO_INCREMENT", "", line, flags=re.I)
    line = re.sub(r"\s+unsigned\b", "", line, flags=re.I)
    line = re.sub(r"\s+CHARACTER\s+SET\s+\w+", "", line, flags=re.I)
    line = re.sub(r"\s+COLLATE\s+\w+", "", line, flags=re.I)
    line = re.sub(r"\s+ON\s+UPDATE\s+CURRENT_TIMESTAMP", "", line, flags=re.I)

    # Remove COMMENT '...' (handle nested parentheses inside comment)
    while True:
        m = re.search(r"\s+COMMENT\s+'[^']*'", line, flags=re.I)
        if not m:
            break
        line = line[: m.start()] + line[m.end() :]

    # Normalize DEFAULT clause for SQLite
    line = re.sub(r"\s+DEFAULT\s+'([^']*)'", r" DEFAULT '\1'", line, flags=re.I)

    return line.strip()


def convert_create_sql(mysql_sql: str) -> str:
    """Convert MySQL CREATE TABLE to SQLite-compatible syntax."""
    table_match = re.search(r"CREATE\s+TABLE\s+`?(\w+)`?\s*\(", mysql_sql, re.I)
    if not table_match:
        raise ValueError(f"Cannot parse CREATE TABLE: {mysql_sql[:100]}")
    table_name = table_match.group(1)

    # Extract content between outer parentheses
    paren_depth = 0
    start_idx = mysql_sql.index("(")
    cols_section = ""
    for i, ch in enumerate(mysql_sql[start_idx:], start_idx):
        if ch == "(":
            paren_depth += 1
        elif ch == ")":
            paren_depth -= 1
        if paren_depth == 0 and i > start_idx:
            cols_section = mysql_sql[start_idx + 1 : i]
            break

    col_lines = split_column_definitions(cols_section)
    output_lines = []
    pk_col = None

    for line in col_lines:
        line_stripped = line.strip()
        if not line_stripped:
            continue

        # Skip table-level constraints
        if re.match(r'^\s*(KEY|INDEX|CONSTRAINT|UNIQUE\s+(KEY|INDEX))', line_stripped, re.I):
            continue
        if re.match(r'^\s*FOREIGN\s+KEY', line_stripped, re.I):
            continue

        # Extract PRIMARY KEY
        pk_match = re.search(
            r'PRIMARY\s+KEY\s*\(\s*`?(\w+)`?\s*\)', line_stripped, re.I
        )
        if pk_match:
            pk_col = pk_match.group(1)
            continue

        # Clean the line
        cleaned = clean_line(line_stripped)

        # Match column definition: "name" type(optional_params) rest...
        col_match = re.match(
            r'^"(\w+)"\s+(\w+(?:\s*\([^)]*\))?)\s*(.*)', cleaned, re.I
        )
        if col_match:
            col_name = col_match.group(1)
            col_type = col_match.group(2)
            sqlite_type = mysql_type_to_sqlite(col_type)
            rest = col_match.group(3).strip()

            not_null = ""
            if re.search(r"\bNOT\s+NULL\b", rest, re.I):
                not_null = " NOT NULL"

            default = ""
            default_match = re.search(r"\bDEFAULT\s+(.+?)(?:\s|$)", rest, re.I)
            if default_match:
                dv = default_match.group(1).strip()
                if dv.upper() != "NULL":
                    default = f" DEFAULT {dv}"

            output_lines.append(f'"{col_name}" {sqlite_type}{not_null}{default}')
        else:
            output_lines.append(cleaned)

    # Add primary key
    if pk_col:
        output_lines.append(f'PRIMARY KEY ("{pk_col}")')

    return (
        f'CREATE TABLE "{table_name}" (\n  '
        + ",\n  ".join(output_lines)
        + "\n)"
    )


def export():
    print(f"Connecting to MySQL at {MYSQL_CONFIG['host']}:{MYSQL_CONFIG['port']}...")
    conn = pymysql.connect(
        host=MYSQL_CONFIG["host"],
        port=MYSQL_CONFIG["port"],
        user=MYSQL_CONFIG["user"],
        password=MYSQL_CONFIG["password"],
        database=MYSQL_CONFIG["database"],
        charset="utf8mb4",
        cursorclass=DictCursor,
    )

    try:
        with conn.cursor() as cursor:
            cursor.execute("SHOW TABLES")
            table_key = f"Tables_in_{MYSQL_CONFIG['database']}"
            tables = [row[table_key] for row in cursor.fetchall()]
        print(f"Found tables: {tables}")

        sqlite_conn = sqlite3.connect(DB_PATH)
        sqlite_conn.execute("PRAGMA journal_mode=WAL")
        sqlite_conn.execute("PRAGMA foreign_keys=OFF")

        try:
            for table in tables:
                print(f"\nExporting {table}...")
                with conn.cursor() as cursor:
                    cursor.execute(f"SHOW CREATE TABLE `{table}`")
                    create_sql = cursor.fetchone()["Create Table"]

                    sqlite_create = convert_create_sql(create_sql)
                    print(f"  SQLite DDL: {sqlite_create[:80]}...")

                    sqlite_conn.execute(f'DROP TABLE IF EXISTS "{table}"')
                    sqlite_conn.execute(sqlite_create)

                    cursor.execute(f"SELECT * FROM `{table}`")
                    rows = cursor.fetchall()
                    if rows:
                        columns = list(rows[0].keys())
                        placeholders = ", ".join(["?" for _ in columns])
                        col_names = ", ".join(f'"{c}"' for c in columns)
                        insert_sql = (
                            f'INSERT INTO "{table}" ({col_names}) VALUES ({placeholders})'
                        )
                        for row in rows:
                            values = [
                                float(row[c]) if isinstance(row[c], Decimal) else row[c]
                                for c in columns
                            ]
                            sqlite_conn.execute(insert_sql, values)
                    print(f"  -> {len(rows)} rows")

            sqlite_conn.commit()
            print(f"\nExport complete! Database saved to: {DB_PATH}")

            # Verify
            cursor = sqlite_conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
            tables_in_sqlite = [r[0] for r in cursor.fetchall()]
            print(f"SQLite tables: {tables_in_sqlite}")
            for t in tables_in_sqlite:
                cur = sqlite_conn.execute(f'SELECT COUNT(*) FROM "{t}"')
                count = cur.fetchone()[0]
                print(f"  {t}: {count} rows")

        finally:
            sqlite_conn.close()
    finally:
        conn.close()


if __name__ == "__main__":
    export()
