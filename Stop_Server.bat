@echo off
for /f "tokens=5" %%a in ('netstat -ano ^| findstr /R /C:":8000 .*LISTENING"') do (
    echo Stopping Poisson Betting Server (PID %%a)...
    taskkill /F /PID %%a >nul 2>&1
)
echo Server stopped.
timeout /t 2 >nul
