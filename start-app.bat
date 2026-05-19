@echo off
:: Alias launcher — keeps window open on errors
cd /d "%~dp0"
call "%~dp0start-aiden.bat" %*
set "EC=%ERRORLEVEL%"
if not "%EC%"=="0" (
    echo.
    echo [start-app] Exited with code %EC%.
    pause
)
exit /b %EC%
