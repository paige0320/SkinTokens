@echo off
REM Double-click this to start the SkinTokens Blender add-on backend.
REM Keep the window open while you use the add-on in Blender.
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo Could not find .venv\Scripts\python.exe
    echo Run setup_windows.ps1 first to create the environment.
    pause
    exit /b 1
)

echo Starting SkinTokens add-on backend (loopback only, token-protected)...
echo Loading the model can take a minute. Leave this window open.
echo.
".venv\Scripts\python.exe" addon_server.py

echo.
echo Backend stopped.
pause
