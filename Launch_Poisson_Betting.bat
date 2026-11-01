@echo off
cd /d "%~dp0"

REM Check if port 8000 is already listening
netstat -ano | findstr /R /C:":8000 .*LISTENING" >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    REM Start the Python backend silently in the background using pythonw
    where pythonw >nul 2>&1
    if %ERRORLEVEL% EQU 0 (
        start "" pythonw "%~dp0app.py"
    ) else (
        start "Poisson Betting Server" /min python "%~dp0app.py"
    )
    timeout /t 1 /nobreak >nul
)

REM Launch in Standalone Desktop App mode (Edge or Chrome, fallback to default browser)
where msedge >nul 2>&1
if %ERRORLEVEL% EQU 0 (
    start "" msedge --app=http://127.0.0.1:8000
    exit /b 0
)

if exist "%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe" (
    start "" "%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe" --app=http://127.0.0.1:8000
    exit /b 0
)

if exist "%ProgramFiles%\Microsoft\Edge\Application\msedge.exe" (
    start "" "%ProgramFiles%\Microsoft\Edge\Application\msedge.exe" --app=http://127.0.0.1:8000
    exit /b 0
)

if exist "%ProgramFiles%\Google\Chrome\Application\chrome.exe" (
    start "" "%ProgramFiles%\Google\Chrome\Application\chrome.exe" --app=http://127.0.0.1:8000
    exit /b 0
)

start "" http://127.0.0.1:8000
