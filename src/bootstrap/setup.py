"""项目环境初始化 CLI。

用法（在项目根目录）：
  python src/bootstrap/setup.py
  py -3 src/bootstrap/setup.py
  .\\scripts\\setup.ps1
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parents[1]
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from bootstrap.venv import ensure_venv, print_python_install_guide, project_root  # noqa: E402


def main() -> int:
    root = project_root()
    print(f"项目根目录: {root}", file=sys.stderr)

    try:
        venv_python = ensure_venv(root, verbose=True)
    except RuntimeError:
        return 1
    except subprocess.CalledProcessError as exc:
        print(f"初始化失败: {exc}", file=sys.stderr)
        print_python_install_guide()
        return 1

    print("\n初始化完成。", file=sys.stderr)
    print(f"  虚拟环境 Python: {venv_python}", file=sys.stderr)
    print("  MCP 配置: .cursor/mcp.json", file=sys.stderr)
    print("  下一步: 在 Cursor 中打开本项目，检查 Settings → MCP 连接状态。", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
