@echo off
setlocal
cd /d "%~dp0.."
if not exist ".venv\Scripts\python.exe" (
  echo [web] 未找到 .venv，请先运行 scripts\setup.ps1
  exit /b 1
)
echo [web] 启动 AI Agent 数据分析服务 http://0.0.0.0:8000
echo [web] 公网访问请将 0.0.0.0 替换为服务器 IP
".venv\Scripts\python.exe" -m uvicorn web.app:app --app-dir src --host 0.0.0.0 --port 8000
