# PowerShell helper to stop all running services
$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Split-Path -Parent $ScriptDir

Write-Host "Stopping all CentrAlign services..." -ForegroundColor Yellow
& "$ProjectRoot\.venv\Scripts\python.exe" "$ScriptDir\stop_all.py"
