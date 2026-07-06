#!/usr/bin/env bash
set -euo pipefail

HOOK_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "${HOOK_DIR}/../.." && pwd)"
cd "${ROOT}"

export PYTHONUTF8=1
export PYTHONIOENCODING=utf-8

VENV_PY="${ROOT}/.venv/bin/python"
RUN_HOOK="${HOOK_DIR}/run_hook.py"

if [[ -x "${VENV_PY}" ]]; then
  exec "${VENV_PY}" -u "${RUN_HOOK}" "$@"
fi

for cmd in py -3 python3 python; do
  if command -v ${cmd%% *} >/dev/null 2>&1; then
    exec ${cmd} -u "${RUN_HOOK}" "$@"
  fi
done

echo "[my_first_agent] Hook 跳过：未找到 Python。请运行 ./scripts/setup.sh 安装环境。" >&2
exit 0
