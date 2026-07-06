"""Hook 启动器：自举 .venv 后用项目虚拟环境执行指定 Hook 脚本。

Hook 必须继承 stdin（Cursor 传入 JSON），因此使用 os.execv 替换进程。
若本机无 Python，写入 hook-debug.log 并以 0 退出，避免阻塞 Cursor。
"""

from __future__ import annotations

import os
import sys
import traceback
from pathlib import Path

_HOOK_DIR = Path(__file__).resolve().parent
_ROOT = _HOOK_DIR.parents[1]
_SRC = _ROOT / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from bootstrap.venv import ensure_venv, print_python_install_guide, venv_python_path  # noqa: E402


def _append_bootstrap_log(message: str) -> None:
    log_dir = _HOOK_DIR / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "hook-debug.log"
    try:
        from datetime import datetime
        from zoneinfo import ZoneInfo

        timestamp = datetime.now(ZoneInfo("Asia/Shanghai")).strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        timestamp = "unknown"
    line = f"{timestamp}\trun_hook\t{message}\n"
    with log_file.open("a", encoding="utf-8") as handle:
        handle.write(line)


def main() -> int:
    if len(sys.argv) < 2:
        print("用法: run_hook.py <hook_script.py>", file=sys.stderr)
        return 2

    hook_name = sys.argv[1]
    hook_script = _HOOK_DIR / hook_name
    if not hook_script.is_file():
        _append_bootstrap_log(f"Hook 脚本不存在: {hook_name}")
        return 0

    venv_python = venv_python_path(_ROOT)
    try:
        if not (venv_python.exists() and _venv_ready(venv_python)):
            ensure_venv(_ROOT, verbose=False)
            venv_python = venv_python_path(_ROOT)
    except RuntimeError:
        _append_bootstrap_log("bootstrap 失败: 未找到 Python，Hook 已跳过")
        print_python_install_guide()
        return 0
    except Exception:
        _append_bootstrap_log(f"bootstrap 异常:\n{traceback.format_exc()}")
        return 0

    if not venv_python.exists():
        _append_bootstrap_log("bootstrap 后仍无 .venv，Hook 已跳过")
        return 0

    os.chdir(_ROOT)
    os.environ.setdefault("PYTHONUTF8", "1")
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    os.execv(
        str(venv_python),
        [str(venv_python), "-u", str(hook_script)],
    )


def _venv_ready(venv_python: Path) -> bool:
    try:
        import subprocess

        result = subprocess.run(
            [str(venv_python), "-c", "import tzdata"],
            capture_output=True,
            timeout=15,
            check=False,
        )
        return result.returncode == 0
    except Exception:
        return False


if __name__ == "__main__":
    raise SystemExit(main())
