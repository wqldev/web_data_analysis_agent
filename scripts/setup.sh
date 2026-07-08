#!/usr/bin/env bash
# 项目环境一键初始化（macOS / Linux）
# 用法：./scripts/setup.sh

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT}"

echo "== web_data_analysis_agent 环境初始化 =="
echo "项目根目录: ${ROOT}"

find_python() {
  for cmd in python3.12 python3.11 python3.10 python3 python "py -3"; do
    if command -v "${cmd%% *}" >/dev/null 2>&1; then
      ver=$(${cmd} -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>/dev/null || true)
      if [[ "${ver}" =~ ^3\.(1[0-9]|[0-9]{2})$ ]]; then
        echo "${cmd}"
        return 0
      fi
    fi
  done
  return 1
}

PY_CMD="$(find_python)" || {
  echo ""
  echo "未找到 Python 3.10+。请先安装："
  echo "  macOS:  brew install python@3.12"
  echo "  Ubuntu: sudo apt install python3.12 python3.12-venv python3-pip"
  echo ""
  exit 1
}

echo "使用 Python: ${PY_CMD}"
${PY_CMD} "${ROOT}/src/bootstrap/setup.py"

echo ""
echo "完成。请在 Cursor 中打开本项目并检查 MCP 连接。"
