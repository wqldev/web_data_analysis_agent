"""MCP 服务启动器：自举 .venv 后启动指定 server 脚本。"""

from __future__ import annotations

import os
import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parents[1]
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from bootstrap.venv import ensure_venv, print_python_install_guide, project_root  # noqa: E402


def main() -> int:
    if len(sys.argv) < 2:
        print("用法: launcher.py <server_script.py>", file=sys.stderr)
        return 2

    script_name = sys.argv[1]
    root = project_root()
    server = Path(__file__).resolve().parent / script_name

    if not server.is_file():
        print(f"MCP 脚本不存在: {server}", file=sys.stderr)
        return 2

    try:
        venv_python = ensure_venv(root)
    except RuntimeError:
        return 1
    except Exception as exc:
        print(f"环境初始化失败: {exc}", file=sys.stderr)
        print_python_install_guide()
        return 1

    os.chdir(root)
    os.execv(str(venv_python), [str(venv_python), str(server)])


if __name__ == "__main__":
    raise SystemExit(main())
