"""通用模型配置持久化（替换 cursor_config）。"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = ROOT / "data" / "model_config.json"
DEFAULT_CONFIG: dict[str, Any] = {
    "api_key": "",
    "model": "gpt-4o",
    "api_base": "https://api.openai.com/v1",
    "temperature": 0.7,
    "max_tokens": 4096,
}


def _ensure_data_dir() -> None:
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)


def load_config() -> dict[str, Any]:
    env_key = os.getenv("MODEL_API_KEY", "").strip()
    env_model = os.getenv("MODEL_NAME", "").strip()
    env_base = os.getenv("MODEL_API_BASE", "").strip()
    if CONFIG_PATH.exists():
        data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        merged = {**DEFAULT_CONFIG, **data}
    else:
        merged = dict(DEFAULT_CONFIG)
    if env_key:
        merged["api_key"] = env_key
    if env_model:
        merged["model"] = env_model
    if env_base:
        merged["api_base"] = env_base
    return merged


def save_config(config: dict[str, Any]) -> dict[str, Any]:
    _ensure_data_dir()
    existing = load_config() if CONFIG_PATH.exists() else DEFAULT_CONFIG
    merged = {**existing, **config}
    if not str(config.get("api_key", "")).strip() and existing.get("api_key"):
        merged["api_key"] = existing["api_key"]
    payload = {
        "api_key": str(merged.get("api_key", "")).strip(),
        "model": str(merged.get("model") or "gpt-4o").strip(),
        "api_base": str(merged.get("api_base") or "https://api.openai.com/v1").strip(),
        "temperature": float(merged.get("temperature", 0.7)),
        "max_tokens": int(merged.get("max_tokens", 4096)),
    }
    CONFIG_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload


def public_config(config: dict[str, Any] | None = None) -> dict[str, Any]:
    cfg = config or load_config()
    return {
        "model": cfg.get("model", "gpt-4o"),
        "api_base": cfg.get("api_base", "https://api.openai.com/v1"),
        "api_key_set": bool(cfg.get("api_key")),
    }


def get_api_key() -> str:
    return str(load_config().get("api_key", "")).strip()


def get_model() -> str:
    return str(load_config().get("model") or "gpt-4o").strip()


def get_api_base() -> str:
    return str(load_config().get("api_base") or "https://api.openai.com/v1").strip()


def get_temperature() -> float:
    return float(load_config().get("temperature", 0.7))


def get_max_tokens() -> int:
    return int(load_config().get("max_tokens", 4096))
