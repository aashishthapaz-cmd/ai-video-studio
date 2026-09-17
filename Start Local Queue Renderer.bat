@echo off
setlocal
cd /d "%~dp0"
title Local ComfyUI Queue Renderer
echo Starting the local queue renderer with ComfyUI and Facebook publishing...
if not exist "%~dp0logs" mkdir "%~dp0logs"
start "Local Queue Renderer" /min "C:\Users\Kunyo.co\AppData\Local\Programs\Python\Python310\python.exe" "%~dp0cloud_generator\server.py"
timeout /t 2 /nobreak >nul
start "" http://127.0.0.1:8190/
echo Local queue renderer started. Keep this PC powered on for scheduled posts.
endlocal
