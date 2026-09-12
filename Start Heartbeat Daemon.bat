@echo off
title Autonomous Studio - Queue Heartbeat Watchdog
cd /d "%~dp0"
echo ======================================================================
echo    Autonomous AI Video Studio - Precision Heartbeat Daemon
echo    Monitors queue and guarantees on-time GitHub Actions triggering
echo ======================================================================
echo.
python tools\queue_heartbeat.py
pause
