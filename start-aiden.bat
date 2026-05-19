@echo off
cd /d "%~dp0"

:: Load .env before delayed expansion (values may contain !)
call :load_env

setlocal EnableDelayedExpansion
chcp 65001 >nul 2>&1

for /f %%a in ('echo prompt $E ^| cmd') do set "ESC=%%a"
set "C=!ESC![36m"
set "G=!ESC![32m"
set "Y=!ESC![33m"
set "R=!ESC![31m"
set "D=!ESC![2m"
set "B=!ESC![1m"
set "N=!ESC![0m"

echo.
echo !C!======================================================!N!
echo !C!=!N!!B!     AI.DEN  --  Local AI Cluster                   !N!!C!=!N!
echo !C!=!N!!D!     llama.cpp + model-router + MCP + Open WebUI    !N!!C!=!N!
echo !C!======================================================!N!
echo.

:: Route commands
if /i "%~1"=="--stop" goto :cmd_stop
if /i "%~1"=="-stop" goto :cmd_stop
if /i "%~1"=="stop" goto :cmd_stop
if /i "%~1"=="--status" goto :cmd_status
if /i "%~1"=="-status" goto :cmd_status
if /i "%~1"=="status" goto :cmd_status
if /i "%~1"=="--logs" goto :cmd_logs
if /i "%~1"=="-logs" goto :cmd_logs
if /i "%~1"=="logs" goto :cmd_logs
if /i "%~1"=="--pull" goto :cmd_pull
if /i "%~1"=="-pull" goto :cmd_pull
if /i "%~1"=="pull" goto :cmd_pull
if /i "%~1"=="--cpu" goto :cmd_start_cpu
if /i "%~1"=="-cpu" goto :cmd_start_cpu
if /i "%~1"=="cpu" goto :cmd_start_cpu
if /i "%~1"=="--help" goto :cmd_help
if /i "%~1"=="-help" goto :cmd_help
if /i "%~1"=="help" goto :cmd_help
if /i "%~1"=="/?" goto :cmd_help
if /i "%~1"=="mtp" (
    set "COMPOSE_PROFILES=hermes"
    set "COMPOSE_EXTRA=!COMPOSE_EXTRA! -f docker-compose.hermes-mtp.yml"
    shift
)
goto :cmd_start_default

:: ---------------------------------------------------------------------------
:load_env
setlocal DisableDelayedExpansion
set "CODER=qwen2.5-coder:7b"
set "LLAMA=llama3.1:8b"
set "VISION=gemma4"
set "CODER_PORT=8765"
set "LLAMA_PORT=8766"
set "VISION_PORT=8767"
set "OLLAMA_PORT=11434"
set "WEBUI_PORT=8080"
set "MCP_PORT=5000"
set "AUTO_LAUNCH_CLAW=true"
set "COMPOSE_PROFILES="
set "HERMES_GATEWAY_PORT=8642"
set "LLAMACPP_PORT=8081"
set "LLAMA_BACKEND=llamacpp"
set "COMPOSE_EXTRA="
set "AIDEN_USE_RESOURCE_LIMITS=1"
set "LLAMACPP_GGUF=Qwen3.6-27B-MTP-UD-Q4_K_XL.gguf"
if exist ".env" (
    for /f "usebackq eol=# tokens=1,* delims==" %%a in (".env") do (
        if "%%a"=="CODER_MODEL" set "CODER=%%b"
        if "%%a"=="LLAMA_MODEL" set "LLAMA=%%b"
        if "%%a"=="VISION_MODEL" set "VISION=%%b"
        if "%%a"=="CODER_PORT" set "CODER_PORT=%%b"
        if "%%a"=="LLAMA_PORT" set "LLAMA_PORT=%%b"
        if "%%a"=="VISION_PORT" set "VISION_PORT=%%b"
        if "%%a"=="OLLAMA_PORT" set "OLLAMA_PORT=%%b"
        if "%%a"=="WEBUI_PORT" set "WEBUI_PORT=%%b"
        if "%%a"=="MCP_PORT" set "MCP_PORT=%%b"
        if "%%a"=="AUTO_LAUNCH_CLAW" set "AUTO_LAUNCH_CLAW=%%b"
        if "%%a"=="COMPOSE_PROFILES" set "COMPOSE_PROFILES=%%b"
        if "%%a"=="HERMES_GATEWAY_PORT" set "HERMES_GATEWAY_PORT=%%b"
        if "%%a"=="LLAMACPP_PORT" set "LLAMACPP_PORT=%%b"
        if "%%a"=="LLAMA_BACKEND" set "LLAMA_BACKEND=%%b"
        if "%%a"=="AIDEN_USE_RESOURCE_LIMITS" set "AIDEN_USE_RESOURCE_LIMITS=%%b"
        if "%%a"=="LLAMACPP_GGUF" set "LLAMACPP_GGUF=%%b"
    )
)
if /i "%AIDEN_USE_RESOURCE_LIMITS%"=="1" set "COMPOSE_EXTRA=-f docker-compose.yml -f docker-compose.resources.yml"
if /i "%AIDEN_USE_RESOURCE_LIMITS%"=="true" set "COMPOSE_EXTRA=-f docker-compose.yml -f docker-compose.resources.yml"
if not defined COMPOSE_EXTRA set "COMPOSE_EXTRA=-f docker-compose.yml"
endlocal ^
  & set "CODER=%CODER%" ^
  & set "LLAMA=%LLAMA%" ^
  & set "VISION=%VISION%" ^
  & set "CODER_PORT=%CODER_PORT%" ^
  & set "LLAMA_PORT=%LLAMA_PORT%" ^
  & set "VISION_PORT=%VISION_PORT%" ^
  & set "OLLAMA_PORT=%OLLAMA_PORT%" ^
  & set "WEBUI_PORT=%WEBUI_PORT%" ^
  & set "MCP_PORT=%MCP_PORT%" ^
  & set "AUTO_LAUNCH_CLAW=%AUTO_LAUNCH_CLAW%" ^
  & set "COMPOSE_PROFILES=%COMPOSE_PROFILES%" ^
  & set "HERMES_GATEWAY_PORT=%HERMES_GATEWAY_PORT%" ^
  & set "LLAMACPP_PORT=%LLAMACPP_PORT%" ^
  & set "LLAMA_BACKEND=%LLAMA_BACKEND%" ^
  & set "COMPOSE_EXTRA=%COMPOSE_EXTRA%" ^
  & set "AIDEN_USE_RESOURCE_LIMITS=%AIDEN_USE_RESOURCE_LIMITS%" ^
  & set "LLAMACPP_GGUF=%LLAMACPP_GGUF%"
exit /b 0

:: ---------------------------------------------------------------------------
:require_docker
docker info >nul 2>&1
if errorlevel 1 (
    echo !R![ERROR]!N! Docker is not running. Start Docker Desktop, then run this again.
    call :pause_exit 1
)
exit /b 0

:: ---------------------------------------------------------------------------
:compose_up
set "GPU_MODE=%~1"
if "!GPU_MODE!"=="0" (
    docker compose !COMPOSE_EXTRA! -f docker-compose.cpu.yml up -d --build
) else (
    docker compose !COMPOSE_EXTRA! up -d --build
)
exit /b %ERRORLEVEL%

:: ---------------------------------------------------------------------------
:pause_exit
echo.
if "%~1"=="" (
    pause
    exit /b 0
)
echo [exit code %~1]
pause
exit /b %~1

:: ---------------------------------------------------------------------------
:cmd_stop
call :require_docker
if errorlevel 1 exit /b 1
echo !Y![STOP]!N! Shutting down AI.DEN...
docker compose !COMPOSE_EXTRA! down
echo !G![DONE]!N! AI.DEN stopped.
call :pause_exit
exit /b 0

:: ---------------------------------------------------------------------------
:cmd_status
call :require_docker
if errorlevel 1 exit /b 1
echo !C![STATUS]!N! Container health:
echo.
docker compose !COMPOSE_EXTRA! ps
echo.
echo !C![MODELS]!N! Backend: !LLAMA_BACKEND!
curl -sf -m 5 "http://localhost:!LLAMACPP_PORT!/v1/models" 2>nul
if errorlevel 1 echo   !D!(llamacpp not ready on port !LLAMACPP_PORT!)!N!
echo.
curl -sf -m 3 "http://localhost:!MCP_PORT!/health" 2>nul
if errorlevel 1 (echo   !D!(MCP not ready on port !MCP_PORT!)!N!) else (echo   !G!MCP OK!N! http://localhost:!MCP_PORT!/mcp)
call :pause_exit
exit /b 0

:: ---------------------------------------------------------------------------
:cmd_logs
call :require_docker
if errorlevel 1 exit /b 1
echo !D!Streaming logs (Ctrl+C to stop tailing; containers keep running)!N!
docker compose !COMPOSE_EXTRA! logs -f --tail=80
call :pause_exit
exit /b 0

:: ---------------------------------------------------------------------------
:cmd_pull
call :require_docker
if errorlevel 1 exit /b 1
echo !Y![PULL]!N! Ollama is optional in this stack; models live in .\models\ as GGUF.
echo   Expected: models\!LLAMACPP_GGUF!
if not exist "models\!LLAMACPP_GGUF!" (
    echo !R![WARN]!N! File not found. See models\README.md
) else (
    echo !G![OK]!N! Found models\!LLAMACPP_GGUF!
)
call :pause_exit
exit /b 0

:: ---------------------------------------------------------------------------
:cmd_help
echo   !B!Usage:!N!  start-aiden.bat [command]
echo   Same as:      start-app.bat
echo.
echo   !B!Commands:!N!
echo     (no arg)   Start all services (GPU if available)
echo     cpu        Force CPU-only compose overlay
echo     mtp        Enable Hermes profile + MTP overlay
echo     stop       Shut down containers
echo     status     Health + model list
echo     logs       Tail container logs
echo     pull       Check GGUF in models\
echo     help       This help
echo.
echo   Window stays open while services run. Close or Ctrl+C to stop the stack.
call :pause_exit
exit /b 0

:: ---------------------------------------------------------------------------
:cmd_start_cpu
call :require_docker
if errorlevel 1 exit /b 1
set "GPU_MODE=0"
echo !C![START]!N! Launching AI.DEN (CPU-only)...
call :compose_up 0
if errorlevel 1 (
    echo !R![ERROR]!N! docker compose failed.
    call :pause_exit 1
)
goto :after_start

:: ---------------------------------------------------------------------------
:cmd_start_default
call :require_docker
if errorlevel 1 exit /b 1
set "GPU_MODE=1"
echo !C![START]!N! Launching AI.DEN (GPU compose)...
call :compose_up 1
if errorlevel 1 (
    echo !Y![WARN]!N! GPU start failed — retrying CPU-only...
    set "GPU_MODE=0"
    call :compose_up 0
    if errorlevel 1 (
        echo !R![ERROR]!N! Failed to start. Run: start-aiden.bat cpu
        call :pause_exit 1
    )
)

:: ---------------------------------------------------------------------------
:after_start
echo.
docker compose !COMPOSE_EXTRA! ps
echo.
echo !C![HEALTH]!N! Waiting for services (first boot can take several minutes)...

call :wait_for "llama.cpp"     "http://localhost:!LLAMACPP_PORT!/v1/models" 600
call :wait_for "Model router"  "http://localhost:!CODER_PORT!/_aiden/pipeline" 120
call :wait_for "MCP server"    "http://localhost:!MCP_PORT!/health" 90
call :wait_for "Coder API"     "http://localhost:!CODER_PORT!/" 30
call :wait_for "Open WebUI"    "http://localhost:!WEBUI_PORT!/" 120

echo !COMPOSE_PROFILES! | findstr /i "hermes" >nul 2>&1
if not errorlevel 1 call :wait_for "Hermes Agent" "http://localhost:!HERMES_GATEWAY_PORT!/" 90

echo.
if not exist "models\*.gguf" (
    echo !Y![MODELS]!N! No GGUF in .\models\ — see models\README.md
    echo   Expected: models\!LLAMACPP_GGUF!
    echo.
)

echo !G![READY]!N! AI.DEN is online.
echo.
echo   !B!Cursor / Continue / Claw!N!
echo     API      http://127.0.0.1:!CODER_PORT!/v1
echo     MCP      http://127.0.0.1:!MCP_PORT!/mcp
echo     Pipeline http://127.0.0.1:!CODER_PORT!/_aiden/pipeline
echo.
echo   !B!Endpoints!N!
echo   Coder   http://localhost:!CODER_PORT!     !CODER!
echo   Llama   http://localhost:!LLAMA_PORT!     !LLAMA!
echo   Vision  http://localhost:!VISION_PORT!     !VISION!
echo   WebUI   http://localhost:!WEBUI_PORT!
echo   MCP     http://localhost:!MCP_PORT!/mcp
echo   llama   http://localhost:!LLAMACPP_PORT!/v1
echo.
echo   !D!Other terminal: start-aiden.bat status ^| logs ^| stop!N!
echo.

call :maybe_launch_claw

title AI.DEN - Local AI Cluster [RUNNING]
echo !C![LIVE]!N! Streaming logs. !B!Close this window!N! or !B!Ctrl+C!N! to shut down all services.
echo.

docker compose !COMPOSE_EXTRA! logs -f --tail=50
if "!GPU_MODE!"=="0" (
    docker compose !COMPOSE_EXTRA! -f docker-compose.cpu.yml down
) else (
    docker compose !COMPOSE_EXTRA! down
)

title AI.DEN - Shutting Down
echo.
echo !Y![STOP]!N! AI.DEN stopped.
echo.
pause
exit /b 0

:: ---------------------------------------------------------------------------
:maybe_launch_claw
if /i "!AUTO_LAUNCH_CLAW!"=="false" exit /b 0
if /i "!AUTO_LAUNCH_CLAW!"=="0" exit /b 0
if /i "!AUTO_LAUNCH_CLAW!"=="no" exit /b 0
if /i "!AUTO_LAUNCH_CLAW!"=="off" exit /b 0
start "AIDEN - Claw" /D "%~dp0" cmd /k call "%~dp0launch-claw.bat"
exit /b 0

:: ---------------------------------------------------------------------------
:wait_for
setlocal EnableDelayedExpansion
set "LABEL=%~1"
set "URL=%~2"
set /a "TIMEOUT=%~3"
set /a "ELAPSED=0"
<nul set /p "=  Waiting for !LABEL! "
:wait_loop
if !ELAPSED! geq !TIMEOUT! (
    echo  !R!timeout!N!
    endlocal
    exit /b 0
)
curl -sf -o nul -m 3 "!URL!" >nul 2>&1
if not errorlevel 1 (
    echo  !G!ready!N!
    endlocal
    exit /b 0
)
<nul set /p "=."
timeout /t 3 /nobreak >nul
set /a ELAPSED+=3
goto :wait_loop
