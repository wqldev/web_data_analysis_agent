#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
if [[ ! -x .venv/bin/python ]]; then
  echo "[web] 未找到 .venv，请先运行 scripts/setup.sh"
  exit 1
fi
echo "[web] 启动 Agent-Loop Web 服务 http://127.0.0.1:8000"
exec .venv/bin/python -m uvicorn web.app:app --app-dir src --host 127.0.0.1 --port 8000 --reload
