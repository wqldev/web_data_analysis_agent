#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
if [[ ! -x .venv/bin/python ]]; then
  echo "[web] 未找到 .venv，请先运行 scripts/setup.sh"
  exit 1
fi
echo "[web] 启动 AI Agent 数据分析服务 http://0.0.0.0:8000"
echo "[web] 公网访问请将 0.0.0.0 替换为服务器 IP"
exec .venv/bin/python -m uvicorn web.app:app --app-dir src --host 0.0.0.0 --port 8000 --reload
