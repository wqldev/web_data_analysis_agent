"""通用 LLM API 客户端（替换 cursor-sdk）。支持 OpenAI 兼容接口。"""

from __future__ import annotations

import json
from typing import Any

import httpx

from core.model_config import get_api_base, get_api_key, get_max_tokens, get_model, get_temperature


def chat_completion(
    messages: list[dict[str, str]],
    model: str | None = None,
    temperature: float | None = None,
    max_tokens: int | None = None,
) -> str:
    """调用 OpenAI 兼容的聊天补全 API，返回回复文本。"""
    api_key = get_api_key()
    if not api_key:
        raise RuntimeError("未配置 API Key。请在管理员配置中填写。")

    api_base = get_api_base().rstrip("/")
    model = model or get_model()
    temperature = temperature if temperature is not None else get_temperature()
    max_tokens = max_tokens or get_max_tokens()

    url = f"{api_base}/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }

    try:
        with httpx.Client(timeout=120) as client:
            resp = client.post(url, headers=headers, json=payload)
            resp.raise_for_status()
            data = resp.json()
    except httpx.HTTPStatusError as e:
        detail = ""
        try:
            detail = e.response.text
        except Exception:
            pass
        raise RuntimeError(f"API 请求失败 ({e.response.status_code}): {detail}") from e
    except httpx.RequestError as e:
        raise RuntimeError(f"无法连接到 API 服务: {e}") from e

    choices = data.get("choices", [])
    if not choices:
        return ""

    content = choices[0].get("message", {}).get("content", "")
    return content.strip()


def test_api_connection() -> dict[str, Any]:
    """测试 API 连接是否有效。"""
    api_key = get_api_key()
    if not api_key:
        raise RuntimeError("未配置 API Key")

    api_base = get_api_base().rstrip("/")
    model = get_model()

    url = f"{api_base}/models"
    headers = {"Authorization": f"Bearer {api_key}"}

    try:
        with httpx.Client(timeout=30) as client:
            resp = client.get(url, headers=headers)
            resp.raise_for_status()
            data = resp.json()
        models = data.get("data", [])
        model_names = [m.get("id") for m in models if isinstance(m, dict)]
        return {
            "status": "ok",
            "message": f"API 连接成功，{len(model_names)} 个模型可用",
            "model_count": len(model_names),
            "models": model_names[:10],
        }
    except httpx.HTTPStatusError as e:
        detail = ""
        try:
            detail = e.response.text
        except Exception:
            pass
        raise RuntimeError(f"API 连接失败 ({e.response.status_code}): {detail}") from e
    except httpx.RequestError as e:
        raise RuntimeError(f"无法连接到 API 服务: {e}") from e
