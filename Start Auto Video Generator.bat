@echo off
setlocal
cd /d "%~dp0"
title Auto Video Generator Manager
echo Starting Auto Video Generator on port 18765...
if not exist "%~dp0logs" mkdir "%~dp0logs"
start "Auto Video Generator" /min "C:\Users\Kunyo.co\AppData\Local\Programs\Python\Python310\python.exe" "%~dp0app.py"
timeout /t 3 /nobreak >nul
start "" http://127.0.0.1:18765/
echo Manager started. Keep this window open only if you want the startup message visible.
endlocal
