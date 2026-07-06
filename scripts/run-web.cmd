@echo off
setlocal
cd /d "%~dp0.."
if not exist ".venv\Scripts\python.exe" (
  echo [web] 未找到 .venv，请先运行 scripts\setup.ps1
  exit /b 1
)
echo [web] 启动 Agent-Loop Web 服务 http://127.0.0.1:8000
".venv\Scripts\python.exe" -m uvicorn web.app:app --app-dir src --host 127.0.0.1 --port 8000
