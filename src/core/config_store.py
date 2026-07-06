"""MySQL 连接配置持久化与运行时注入。"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = ROOT / "data" / "mysql_config.json"
DEFAULT_CONFIG: dict[str, Any] = {
    "host": "localhost",
    "port": 3306,
    "user": "root",
    "password": "",
    "database": "mysql_dataset_test",
    "allow_writes": False,
}


def _ensure_data_dir() -> None:
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)


def load_config() -> dict[str, Any]:
    if CONFIG_PATH.exists():
        data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        return {**DEFAULT_CONFIG, **data}
    return dict(DEFAULT_CONFIG)


def save_config(config: dict[str, Any]) -> dict[str, Any]:
    _ensure_data_dir()
    existing = load_config() if CONFIG_PATH.exists() else DEFAULT_CONFIG
    merged = {**existing, **config}
    if not str(config.get("password", "")).strip() and existing.get("password"):
        merged["password"] = existing["password"]
    payload = {
        "host": str(merged["host"]).strip(),
        "port": int(merged["port"]),
        "user": str(merged["user"]).strip(),
        "password": str(merged.get("password", "")),
        "database": str(merged["database"]).strip(),
        "allow_writes": bool(merged.get("allow_writes", False)),
    }
    CONFIG_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    apply_config(payload)
    return payload


def apply_config(config: dict[str, Any] | None = None) -> None:
    cfg = config or load_config()
    os.environ["MYSQL_HOST"] = str(cfg["host"])
    os.environ["MYSQL_PORT"] = str(cfg["port"])
    os.environ["MYSQL_USER"] = str(cfg["user"])
    os.environ["MYSQL_PASSWORD"] = str(cfg.get("password", ""))
    os.environ["MYSQL_DATABASE"] = str(cfg["database"])
    os.environ["MYSQL_ALLOW_WRITES"] = "true" if cfg.get("allow_writes") else "false"


def public_config(config: dict[str, Any] | None = None) -> dict[str, Any]:
    cfg = config or load_config()
    return {
        "host": cfg["host"],
        "port": cfg["port"],
        "user": cfg["user"],
        "database": cfg["database"],
        "allow_writes": cfg.get("allow_writes", False),
        "password_set": bool(cfg.get("password")),
    }
