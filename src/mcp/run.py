"""跨平台 MCP 启动器：自动创建 .venv、安装依赖，并启动 server.py。"""

from __future__ import annotations

import runpy
import sys
from pathlib import Path


def main() -> None:
    launcher = Path(__file__).resolve().with_name("launcher.py")
    sys.argv = [str(launcher), "server.py"]
    runpy.run_path(str(launcher), run_name="__main__")


if __name__ == "__main__":
    main()
