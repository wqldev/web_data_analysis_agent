@echo off
setlocal EnableDelayedExpansion

set "ROOT=%~dp0.."
cd /d "%ROOT%"

set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8

if exist "%ROOT%\.venv\Scripts\python.exe" (
  "%ROOT%\.venv\Scripts\python.exe" "%ROOT%\src\mcp\launcher.py" %*
  exit /b !errorlevel!
)

where py >nul 2>&1
if !errorlevel! equ 0 (
  py -3 "%ROOT%\src\mcp\launcher.py" %*
  exit /b !errorlevel!
)

where python >nul 2>&1
if !errorlevel! equ 0 (
  python "%ROOT%\src\mcp\launcher.py" %*
  exit /b !errorlevel!
)

echo [web_data_analysis_agent] MCP 启动失败：未找到 Python。请运行 scripts\setup.ps1 1>&2
exit /b 1
