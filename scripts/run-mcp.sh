#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT}"

export PYTHONUTF8=1
export PYTHONIOENCODING=utf-8

VENV_PY="${ROOT}/.venv/bin/python"
LAUNCHER="${ROOT}/src/mcp/launcher.py"

if [[ -x "${VENV_PY}" ]]; then
  exec "${VENV_PY}" "${LAUNCHER}" "$@"
fi

for cmd in "py -3" python3 python; do
  if command -v ${cmd%% *} >/dev/null 2>&1; then
    exec ${cmd} "${LAUNCHER}" "$@"
  fi
done

echo "[my_first_agent] MCP 启动失败：未找到 Python。请运行 ./scripts/setup.sh" >&2
exit 1
