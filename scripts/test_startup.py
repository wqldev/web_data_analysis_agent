"""Quick test to verify imports and SQLite client work."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

print("=== Testing imports ===")
from core import sqlite_client
from core.model_config import public_config, get_api_key
from core.llm_client import chat_completion
from core.intent import classify_intent, classify_info_query, is_ddl_request
print("All imports OK")

print("\n=== Testing SQLite ===")
result = sqlite_client.test_connection()
print(f"Connection: {result}")

tables = sqlite_client.list_tables()
print(f"Tables: {tables}")

if "orders" in tables:
    desc = sqlite_client.describe_table("orders")
    print(f"Orders columns: {[d['Field'] for d in desc]}")

    rows = sqlite_client.execute_query("SELECT COUNT(*) AS cnt FROM orders")
    print(f"Orders count: {rows[0]['cnt']}")

    # Test MySQL SQL conversion
    rows = sqlite_client.execute_query(
        "SELECT strftime('%Y-%m', order_date) AS month, COUNT(*) AS cnt "
        "FROM orders GROUP BY month ORDER BY month"
    )
    print(f"Months: {len(rows)} rows")
    for r in rows[:3]:
        print(f"  {r}")

print("\n=== Testing model config ===")
config = public_config()
print(f"Config: {config}")

print("\n=== Testing app import ===")
from web.app import app
print("FastAPI app imported OK")

print("\n=== All tests passed! ===")
