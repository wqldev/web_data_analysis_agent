#!/usr/bin/env python3
"""beforeSubmitPrompt：用户自然语言提交时审计危险意图并写入 mcp-guard.log。"""

from __future__ import annotations

import json
import sys
import traceback

from guard_common import (
    append_hook_debug,
    append_mcp_guard_log,
    check_user_text,
    read_hook_payload,
    resolve_user_prompt,
)


def _log_prompt_audit(prompt: str) -> None:
    verdict = check_user_text(prompt)
    if verdict:
        decision, reason = verdict
        append_mcp_guard_log(
            decision=decision,
            reason=reason,
            server="dialog",
            tool_name="user_prompt",
            detail=prompt,
        )
        return
    append_mcp_guard_log(
        decision="allow",
        reason="用户输入无危险意图",
        server="dialog",
        tool_name="user_prompt",
        detail=prompt,
    )


def main() -> int:
    try:
        payload = read_hook_payload()
        prompt, source = resolve_user_prompt(payload)
        stdin_len = getattr(read_hook_payload, "last_len", 0)
        stdin_preview = getattr(read_hook_payload, "last_preview", b"")

        append_hook_debug(
            f"beforeSubmitPrompt source={source} prompt_len={len(prompt)} "
            f"stdin_bytes={stdin_len} keys={list(payload.keys())[:10]} "
            f"stdin_preview={stdin_preview!r}"
        )

        if prompt:
            _log_prompt_audit(prompt)
        else:
            append_hook_debug(
                "beforeSubmitPrompt empty prompt after stdin+transcript fallback"
            )

        print(json.dumps({"continue": True}, ensure_ascii=False))
        sys.stdout.flush()
        return 0
    except Exception:
        append_hook_debug(f"beforeSubmitPrompt error:\n{traceback.format_exc()}")
        print(json.dumps({"continue": True}, ensure_ascii=False))
        sys.stdout.flush()
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
