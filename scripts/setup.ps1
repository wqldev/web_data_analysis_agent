# 项目环境一键初始化（Windows）
# 用法：在项目根目录执行  .\scripts\setup.ps1

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

Write-Host "== web_data_analysis_agent 环境初始化 ==" -ForegroundColor Cyan
Write-Host "项目根目录: $Root"

function Test-Python310 {
    param([string[]]$Commands)
    foreach ($cmd in $Commands) {
        try {
            $parts = $cmd -split '\s+', 2
            $exe = $parts[0]
            $args = if ($parts.Length -gt 1) { $parts[1] } else { "" }
            if (-not (Get-Command $exe -ErrorAction SilentlyContinue)) { continue }
            $version = & $exe $args.Split() -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>$null
            if ($version -match '^3\.(1[0-9]|[0-9]{2})$') {
                return $cmd
            }
        } catch {
            continue
        }
    }
    return $null
}

$pyCmd = Test-Python310 @("py -3.12", "py -3.11", "py -3.10", "py -3", "python3", "python")

if (-not $pyCmd) {
    Write-Host ""
    Write-Host "未找到 Python 3.10+。请先安装：" -ForegroundColor Yellow
    Write-Host "  1. https://www.python.org/downloads/  （勾选 Add to PATH）"
    Write-Host "  2. winget install Python.Python.3.12"
    Write-Host ""
    Write-Host "安装完成后重新运行: .\scripts\setup.ps1"
    exit 1
}

Write-Host "使用 Python: $pyCmd" -ForegroundColor Green

if ($pyCmd -match "^py ") {
    & py -3 "$Root\src\bootstrap\setup.py"
} else {
    & python "$Root\src\bootstrap\setup.py"
}

if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host ""
Write-Host "完成。请在 Cursor 中打开本项目并检查 MCP 连接。" -ForegroundColor Green
