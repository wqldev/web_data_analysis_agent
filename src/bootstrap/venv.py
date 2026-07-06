"""跨平台虚拟环境自举：检测 Python、创建 .venv、安装依赖。"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

MIN_PYTHON = (3, 10)


def project_root() -> Path:
    """从 src/bootstrap/venv.py 向上两级即为项目根目录。"""
    return Path(__file__).resolve().parents[2]


def venv_python_path(root: Path | None = None) -> Path:
    root = root or project_root()
    if sys.platform == "win32":
        return root / ".venv" / "Scripts" / "python.exe"
    return root / ".venv" / "bin" / "python"


def requirements_path(root: Path | None = None) -> Path:
    root = root or project_root()
    return root / "src" / "mcp" / "requirements.txt"


def _log(message: str, verbose: bool) -> None:
    if verbose:
        print(message, file=sys.stderr)


def _python_version_ok(executable: str | Path) -> bool:
    try:
        result = subprocess.run(
            [str(executable), "-c", "import sys; print(sys.version_info[:2])"],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        if result.returncode != 0:
            return False
        major, minor = eval(result.stdout.strip())  # noqa: S307
        return (major, minor) >= MIN_PYTHON
    except (OSError, subprocess.SubprocessError, SyntaxError, ValueError):
        return False


def _resolve_executable(command: str) -> Path | None:
    """将 'py -3' 或 'python' 解析为可执行文件路径。"""
    parts = command.split()
    if not parts:
        return None

    if parts[0] == "py" and len(parts) > 1:
        try:
            result = subprocess.run(
                parts + ["-c", "import sys; print(sys.executable)"],
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )
            if result.returncode == 0:
                path = Path(result.stdout.strip())
                return path if path.exists() else None
        except (OSError, subprocess.SubprocessError):
            return None
        return None

    resolved = shutil.which(parts[0])
    if not resolved:
        return None
    path = Path(resolved)
    return path if path.exists() else None


def find_system_python() -> Path | None:
    """按优先级查找本机 Python 3.10+。"""
    if sys.platform == "win32":
        candidates = ["py -3.12", "py -3.11", "py -3.10", "py -3", "python3", "python"]
    else:
        candidates = ["python3.12", "python3.11", "python3.10", "python3", "python"]

    for command in candidates:
        executable = _resolve_executable(command)
        if executable and _python_version_ok(executable):
            return executable
    return None


def print_python_install_guide() -> None:
    """输出中文安装指引到 stderr。"""
    lines = [
        "",
        "========================================",
        "  未检测到 Python 3.10 或更高版本",
        "========================================",
        "",
        "Windows（任选其一）：",
        "  1. 官网安装：https://www.python.org/downloads/",
        "     安装时勾选「Add python.exe to PATH」",
        "  2. 包管理器：winget install Python.Python.3.12",
        "  3. 安装完成后，在项目根目录执行：",
        "     .\\scripts\\setup.ps1",
        "",
        "macOS：",
        "  brew install python@3.12",
        "  ./scripts/setup.sh",
        "",
        "Linux（Debian/Ubuntu）：",
        "  sudo apt update",
        "  sudo apt install python3.12 python3.12-venv python3-pip",
        "  ./scripts/setup.sh",
        "",
        "初始化成功后，项目会使用根目录下的 .venv 运行 MCP 与 Hook。",
        "========================================",
        "",
    ]
    print("\n".join(lines), file=sys.stderr)


def _deps_installed(venv_python: Path) -> bool:
    try:
        result = subprocess.run(
            [str(venv_python), "-c", "import mcp, pymysql, tzdata"],
            capture_output=True,
            timeout=30,
            check=False,
        )
        return result.returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def ensure_venv(root: Path | None = None, *, verbose: bool = False) -> Path:
    """
    确保 .venv 存在且依赖已安装，返回 venv 内 python 路径。

    若本机无 Python，抛出 RuntimeError（调用方应捕获并输出安装指引）。
    """
    root = root or project_root()
    venv_python = venv_python_path(root)
    req_file = requirements_path(root)

    if venv_python.exists() and _deps_installed(venv_python):
        _log(f"使用已有虚拟环境: {venv_python}", verbose)
        return venv_python

    system_python = find_system_python()
    if system_python is None:
        print_python_install_guide()
        raise RuntimeError("未找到 Python 3.10+，无法创建虚拟环境")

    venv_dir = root / ".venv"
    if not venv_python.exists():
        _log(f"正在创建虚拟环境: {venv_dir}", verbose)
        subprocess.run(
            [str(system_python), "-m", "venv", str(venv_dir)],
            check=True,
            cwd=root,
        )

    if not _deps_installed(venv_python):
        _log(f"正在安装依赖: {req_file}", verbose)
        subprocess.run(
            [str(venv_python), "-m", "pip", "install", "-r", str(req_file)],
            check=True,
            cwd=root,
        )

    if not _deps_installed(venv_python):
        raise RuntimeError("依赖安装后校验失败，请检查网络与 pip 配置")

    _log(f"环境就绪: {venv_python}", verbose)
    return venv_python
