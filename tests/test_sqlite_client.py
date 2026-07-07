from pathlib import Path

from src.core.sqlite_client import describe_table, execute_query, list_tables, test_connection


def test_sqlite_client_reads_sample_tables(tmp_path: Path) -> None:
    db_path = tmp_path / "sample.db"
    import sqlite3

    conn = sqlite3.connect(db_path)
    try:
        conn.execute("CREATE TABLE orders (order_id INTEGER PRIMARY KEY, order_date TEXT, order_status TEXT)")
        conn.execute("CREATE TABLE order_items (order_item_id INTEGER PRIMARY KEY, order_id INTEGER, quantity INTEGER)")
        conn.commit()
    finally:
        conn.close()

    import os
    os.environ["DATA_DB_PATH"] = str(db_path)

    assert list_tables() == ["orders", "order_items"]
    assert describe_table("orders")[0]["name"] == "order_id"
    rows = execute_query("SELECT COUNT(*) AS cnt FROM orders")
    assert rows[0]["cnt"] == 0
    result = test_connection()
    assert result["status"] == "ok"
