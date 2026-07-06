#!/usr/bin/env python3
"""beforeSubmitPrompt：识别数据分析类用户问题并写入 analysis-intent.log。"""

from __future__ import annotations

import json
import sys
import traceback

from analysis_common import append_analysis_intent_log, classify_analysis_intent
from guard_common import append_hook_debug, read_hook_payload, resolve_user_prompt


def main() -> int:
    try:
        payload = read_hook_payload()
        prompt, source = resolve_user_prompt(payload)

        if prompt:
            intent = classify_analysis_intent(prompt)
            if intent:
                category, label, keyword = intent
                append_analysis_intent_log(
                    category=category,
                    label=label,
                    keyword=keyword,
                    prompt=prompt,
                    source=source,
                )
                append_hook_debug(
                    f"beforeSubmitAnalysis matched category={category} "
                    f"keyword={keyword} source={source}"
                )

        print(json.dumps({"continue": True}, ensure_ascii=False))
        sys.stdout.flush()
        return 0
    except Exception:
        append_hook_debug(f"beforeSubmitAnalysis error:\n{traceback.format_exc()}")
        print(json.dumps({"continue": True}, ensure_ascii=False))
        sys.stdout.flush()
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
