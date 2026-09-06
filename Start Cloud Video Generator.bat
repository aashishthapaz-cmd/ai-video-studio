@echo off
setlocal
cd /d "%~dp0"
title Zero-Cost Cloud Video Generator Studio
echo =======================================================
echo   Starting Zero-Cost Cloud Video Generator Studio
echo   (0 MB Local GPU VRAM · Fast Cloud Multi-Engine)
echo =======================================================
if not exist "%~dp0logs" mkdir "%~dp0logs"
start "Cloud Video Generator" /min "C:\Users\Kunyo.co\AppData\Local\Programs\Python\Python310\python.exe" "%~dp0cloud_generator\server.py"
timeout /t 2 /nobreak >nul
start "" http://127.0.0.1:8190/
echo Studio running at http://127.0.0.1:8190/
endlocal
