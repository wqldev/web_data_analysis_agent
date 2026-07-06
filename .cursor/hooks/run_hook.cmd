@echo off
setlocal EnableDelayedExpansion

rem Hook 启动包装：优先 .venv，否则用系统 Python 自举后执行
set "HOOK_DIR=%~dp0"
set "ROOT=%HOOK_DIR%..\.."
cd /d "%ROOT%"

set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8

if exist "%ROOT%\.venv\Scripts\python.exe" (
  "%ROOT%\.venv\Scripts\python.exe" -u "%HOOK_DIR%run_hook.py" %*
  exit /b !errorlevel!
)

where py >nul 2>&1
if !errorlevel! equ 0 (
  py -3 -u "%HOOK_DIR%run_hook.py" %*
  exit /b !errorlevel!
)

where python >nul 2>&1
if !errorlevel! equ 0 (
  python -u "%HOOK_DIR%run_hook.py" %*
  exit /b !errorlevel!
)

echo [my_first_agent] Hook 跳过：未找到 Python。请运行 scripts\setup.ps1 安装环境。 1>&2
exit /b 0
