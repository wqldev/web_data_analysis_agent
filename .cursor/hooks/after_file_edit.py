#!/usr/bin/env python3
"""afterFileEdit：Agent 改文件后自动格式化并写入编辑日志。"""

from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

CHINA_TZ = ZoneInfo("Asia/Shanghai")


def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _log_dir() -> Path:
    log_dir = _project_root() / ".cursor" / "hooks" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    return log_dir


def _extract_file_path(payload: dict) -> Path | None:
    candidates = [
        payload.get("file_path"),
        payload.get("path"),
        payload.get("file"),
        payload.get("filePath"),
    ]
    for item in payload.values():
        if isinstance(item, dict):
            candidates.extend(
                [
                    item.get("file_path"),
                    item.get("path"),
                    item.get("file"),
                    item.get("filePath"),
                ]
            )
    for value in candidates:
        if not value or not isinstance(value, str):
            continue
        path = Path(value)
        if not path.is_absolute():
            path = _project_root() / path
        if path.exists():
            return path
    return None


def _format_sql(content: str) -> str:
    lines = [line.rstrip() for line in content.splitlines()]
    return "\n".join(lines).rstrip() + "\n"


def _format_python(content: str) -> str:
    try:
        import black  # type: ignore

        return black.format_str(content, mode=black.Mode())
    except Exception:
        lines = [line.rstrip() for line in content.splitlines()]
        return "\n".join(lines).rstrip() + "\n"


def _format_json(content: str) -> str:
    data = json.loads(content)
    return json.dumps(data, ensure_ascii=False, indent=2) + "\n"


def _format_text(content: str) -> str:
    lines = [line.rstrip() for line in content.splitlines()]
    return "\n".join(lines).rstrip() + "\n"


def _format_file(path: Path) -> bool:
    suffix = path.suffix.lower()
    original = path.read_text(encoding="utf-8")
    if suffix == ".py":
        formatted = _format_python(original)
    elif suffix == ".sql":
        formatted = _format_sql(original)
    elif suffix == ".json":
        try:
            formatted = _format_json(original)
        except json.JSONDecodeError:
            formatted = _format_text(original)
    elif suffix in {".md", ".mdc", ".txt", ".yml", ".yaml"}:
        formatted = _format_text(original)
    else:
        return False
    if formatted != original:
        path.write_text(formatted, encoding="utf-8")
        return True
    return False


def _append_log(path: Path, formatted: bool, payload: dict) -> None:
    log_file = _log_dir() / "file-edits.log"
    timestamp = datetime.now(CHINA_TZ).strftime("%Y-%m-%d %H:%M:%S")
    tool = payload.get("tool_name") or payload.get("tool") or "unknown"
    line = f"{timestamp}\t{tool}\tformatted={formatted}\t{path}\n"
    with log_file.open("a", encoding="utf-8") as handle:
        handle.write(line)


def main() -> int:
    raw = sys.stdin.read().strip()
    payload: dict = json.loads(raw) if raw else {}
    path = _extract_file_path(payload)
    if path is None:
        return 0
    formatted = _format_file(path)
    _append_log(path, formatted, payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
