# One-click launcher for the SkinTokens Blender add-on backend.
#
#   Right-click  -> Run with PowerShell
#   or:          powershell -ExecutionPolicy Bypass -File .\run_addon_server.ps1
#
# Keep this window open while you use the add-on in Blender. It loads the model
# once and keeps it in VRAM. The add-on auto-detects the connection token, so
# you don't need to copy anything.

$ErrorActionPreference = "Stop"
Set-Location -Path $PSScriptRoot

$py = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $py)) {
    Write-Host "Could not find .venv\Scripts\python.exe." -ForegroundColor Red
    Write-Host "Run setup_windows.ps1 first to create the environment." -ForegroundColor Yellow
    Read-Host "Press Enter to close"
    exit 1
}

Write-Host "Starting SkinTokens add-on backend (loopback only, token-protected)..." -ForegroundColor Cyan
Write-Host "Loading the model can take a minute. Leave this window open." -ForegroundColor DarkGray

& $py addon_server.py
