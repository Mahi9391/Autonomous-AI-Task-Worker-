# PowerShell helper to start all services using virtualenv
$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Split-Path -Parent $ScriptDir

Write-Host "Starting all CentrAlign services..." -ForegroundColor Cyan
& "$ProjectRoot\.venv\Scripts\python.exe" "$ScriptDir\start_all.py"
