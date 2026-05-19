@echo off
setlocal enabledelayedexpansion
chcp 65001 >nul 2>&1

:: ── Navigate to script directory ────────────────────────────────
cd /d "%~dp0"

:: ── ANSI color codes ────────────────────────────────────────────
for /f %%a in ('echo prompt $E ^| cmd') do set "ESC=%%a"
set "C=%ESC%[36m"
set "G=%ESC%[32m"
set "Y=%ESC%[33m"
set "R=%ESC%[31m"
set "D=%ESC%[2m"
set "B=%ESC%[1m"
set "N=%ESC%[0m"

:: ── Read models + host ports from .env (fallbacks match docker-compose defaults) ─
set "CODER=qwen2.5-coder:7b"
set "LLAMA=llama3.1:8b"
set "VISION=gemma4"
set "CODER_PORT=8765"
set "LLAMA_PORT=8766"
set "VISION_PORT=8767"
set "OLLAMA_PORT=11434"
set "WEBUI_PORT=8080"
set "AUTO_LAUNCH_CLAW=true"
set "COMPOSE_PROFILES="
set "HERMES_GATEWAY_PORT=8642"
set "LLAMACPP_PORT=8081"
set "LLAMA_BACKEND=llamacpp"
set "INFERENCE_BACKEND=llamacpp"
set "COMPOSE_EXTRA="
set "AIDEN_USE_RESOURCE_LIMITS=1"
if exist ".env" (
    for /f "usebackq tokens=1,* delims==" %%a in (".env") do (
        if "%%a"=="CODER_MODEL" set "CODER=%%b"
        if "%%a"=="LLAMA_MODEL" set "LLAMA=%%b"
        if "%%a"=="VISION_MODEL" set "VISION=%%b"
        if "%%a"=="CODER_PORT" set "CODER_PORT=%%b"
        if "%%a"=="LLAMA_PORT" set "LLAMA_PORT=%%b"
        if "%%a"=="VISION_PORT" set "VISION_PORT=%%b"
        if "%%a"=="OLLAMA_PORT" set "OLLAMA_PORT=%%b"
        if "%%a"=="WEBUI_PORT" set "WEBUI_PORT=%%b"
        if "%%a"=="AUTO_LAUNCH_CLAW" set "AUTO_LAUNCH_CLAW=%%b"
        if "%%a"=="COMPOSE_PROFILES" set "COMPOSE_PROFILES=%%b"
        if "%%a"=="HERMES_GATEWAY_PORT" set "HERMES_GATEWAY_PORT=%%b"
        if "%%a"=="LLAMACPP_PORT" set "LLAMACPP_PORT=%%b"
        if "%%a"=="LLAMA_BACKEND" set "LLAMA_BACKEND=%%b"
        if "%%a"=="AIDEN_USE_RESOURCE_LIMITS" set "AIDEN_USE_RESOURCE_LIMITS=%%b"
        if "%%a"=="LLAMACPP_GGUF" set "LLAMACPP_GGUF=%%b"
    )
)
if not defined LLAMACPP_GGUF set "LLAMACPP_GGUF=Qwen3.6-27B-MTP-UD-Q4_K_XL.gguf"
if /i "!AIDEN_USE_RESOURCE_LIMITS!"=="1" set "COMPOSE_EXTRA=-f docker-compose.resources.yml"
if /i "!AIDEN_USE_RESOURCE_LIMITS!"=="true" set "COMPOSE_EXTRA=-f docker-compose.resources.yml"
if /i "%~1"=="mtp" (
    set "COMPOSE_PROFILES=hermes"
    set "LLAMA_BACKEND=llamacpp"
    if /i "!AIDEN_USE_RESOURCE_LIMITS!"=="1" (
        set "COMPOSE_EXTRA=-f docker-compose.resources.yml"
    ) else (
        set "COMPOSE_EXTRA="
    )
    shift
)

:: ── Banner ──────────────────────────────────────────────────────
echo.
echo %C%======================================================%N%
echo %C%=%N%%B%     AI.DEN  --  Local AI Cluster                   %N%%C%=%N%
echo %C%=%N%%D%     Ollama + Open WebUI + Model Router Pipeline (open-claw -> caveman)            %N%%C%=%N%
echo %C%======================================================%N%
echo.

:: ── Route commands ──────────────────────────────────────────────
if /i "%~1"=="--stop"       goto :cmd_stop
if /i "%~1"=="-stop"        goto :cmd_stop
if /i "%~1"=="stop"         goto :cmd_stop

if /i "%~1"=="--status"     goto :cmd_status
if /i "%~1"=="-status"      goto :cmd_status
if /i "%~1"=="status"       goto :cmd_status

if /i "%~1"=="--logs"       goto :cmd_logs
if /i "%~1"=="-logs"        goto :cmd_logs
if /i "%~1"=="logs"         goto :cmd_logs

if /i "%~1"=="--pull"       goto :cmd_pull
if /i "%~1"=="-pull"        goto :cmd_pull
if /i "%~1"=="pull"         goto :cmd_pull

if /i "%~1"=="--cpu"        goto :cmd_start_cpu_only
if /i "%~1"=="-cpu"         goto :cmd_start_cpu_only
if /i "%~1"=="cpu"          goto :cmd_start_cpu_only

if /i "%~1"=="--help"       goto :cmd_help
if /i "%~1"=="-help"        goto :cmd_help
if /i "%~1"=="help"         goto :cmd_help
if /i "%~1"=="/?"           goto :cmd_help

goto :cmd_start_default

:: ════════════════════════════════════════════════════════════════
:: require_docker — call before any Docker Compose / docker exec work
:: ════════════════════════════════════════════════════════════════
:require_docker
docker info >nul 2>&1
if errorlevel 1 (
    echo %R%[ERROR]%N% Docker is not running. Start Docker Desktop first.
    pause
    exit /b 1
)
exit /b 0

:: ════════════════════════════════════════════════════════════════
:: STOP
:: ════════════════════════════════════════════════════════════════
:cmd_stop
call :require_docker
if errorlevel 1 goto :eof
echo %Y%[STOP]%N% Shutting down AI.DEN...
docker compose down
echo %G%[DONE]%N% AI.DEN stopped.
goto :eof

:: ════════════════════════════════════════════════════════════════
:: STATUS
:: ════════════════════════════════════════════════════════════════
:cmd_status
call :require_docker
if errorlevel 1 goto :eof
echo %C%[STATUS]%N% Container health:
echo.
docker compose ps 2>nul
echo.
echo %C%[MODELS]%N% Inference backend: !LLAMA_BACKEND!
docker exec ollama ollama list 2>nul
if errorlevel 1 (
    curl -sf -m 3 "http://localhost:!LLAMACPP_PORT!/v1/models" 2>nul
    if errorlevel 1 echo   %D%^(check llamacpp on port !LLAMACPP_PORT!^)%N%
)
goto :eof

:: ════════════════════════════════════════════════════════════════
:: LOGS
:: ════════════════════════════════════════════════════════════════
:cmd_logs
call :require_docker
if errorlevel 1 goto :eof
docker compose logs -f
goto :eof

:: ════════════════════════════════════════════════════════════════
:: PULL MODELS
:: ════════════════════════════════════════════════════════════════
:cmd_pull
call :require_docker
if errorlevel 1 goto :eof
docker exec ollama ollama list >nul 2>&1
if errorlevel 1 (
    echo %R%[ERROR]%N% Ollama container not running. Start AI.DEN first.
    goto :eof
)

echo %Y%[PULL]%N% Checking %B%!CODER!%N% ...
docker exec ollama ollama list 2>nul | findstr /c:"!CODER!" >nul 2>&1
if errorlevel 1 (
    echo %Y%[PULL]%N% Downloading %B%!CODER!%N% ^(~9 GB^)...
    docker exec ollama ollama pull !CODER!
) else (
    echo %G%[OK]%N% !CODER! already downloaded
)

echo %Y%[PULL]%N% Checking %B%!LLAMA!%N% ...
docker exec ollama ollama list 2>nul | findstr /c:"!LLAMA!" >nul 2>&1
if errorlevel 1 (
    echo %Y%[PULL]%N% Downloading %B%!LLAMA!%N% ^(~5 GB^)...
    docker exec ollama ollama pull !LLAMA!
) else (
    echo %G%[OK]%N% !LLAMA! already downloaded
)

echo %Y%[PULL]%N% Checking %B%!VISION!%N% ...
docker exec ollama ollama list 2>nul | findstr /c:"!VISION!" >nul 2>&1
if errorlevel 1 (
    echo %Y%[PULL]%N% Downloading %B%!VISION!%N% ^(~10 GB^)...
    docker exec ollama ollama pull !VISION!
) else (
    echo %G%[OK]%N% !VISION! already downloaded
)
goto :eof

:: ════════════════════════════════════════════════════════════════
:: HELP
:: ════════════════════════════════════════════════════════════════
:cmd_help
echo   %B%Usage:%N%  start-aiden.bat [command]
echo   Same as:      start-app.bat %D%^(alias for discoverability^)%N%
echo.
echo   %B%Commands:%N%
echo   -----------------------------------------------
echo     %D%^(no arg^)%N%       Start AI.DEN ^(GPU accelerated^)
echo     cpu            Start AI.DEN in CPU-only mode
echo     stop           Shut down all containers
echo     status         Show container health + models
echo     logs           Tail live logs
echo     pull           Download / update models
echo     mtp            Start with llama.cpp MTP + Hermes Agent profiles
echo     help           Show this help
echo.
echo   The terminal stays open while AI.DEN runs.
echo   Close the window or press Ctrl+C to shut everything down.
echo.
goto :eof

:: ════════════════════════════════════════════════════════════════
:: START (default — GPU accelerated)
:: ════════════════════════════════════════════════════════════════
:cmd_start_default
call :require_docker
if errorlevel 1 exit /b 1
set "GPU_MODE=1"
echo %C%[START]%N% Launching AI.DEN...
echo.
echo   Mode: %B%GPU accelerated ^(NVIDIA RTX^)%N%
docker compose %COMPOSE_EXTRA% up -d
if errorlevel 1 (
    echo %R%[ERROR]%N% Failed to start containers. Try: %B%start-aiden.bat cpu%N%
    pause
    exit /b 1
)
goto :after_start

:: ════════════════════════════════════════════════════════════════
:: START (CPU-only fallback)
:: ════════════════════════════════════════════════════════════════
:cmd_start_cpu_only
call :require_docker
if errorlevel 1 exit /b 1
set "GPU_MODE=0"
echo %C%[START]%N% Launching AI.DEN...
echo.
echo   Mode: %B%CPU only%N% ^(no GPU acceleration^)
docker compose -f docker-compose.yml -f docker-compose.cpu.yml %COMPOSE_EXTRA% up -d
if errorlevel 1 (
    echo %R%[ERROR]%N% Failed to start containers.
    pause
    exit /b 1
)
goto :after_start

:: ════════════════════════════════════════════════════════════════
:: POST-START: health checks + summary + keep-alive
:: ════════════════════════════════════════════════════════════════
:after_start
echo.
echo %C%[HEALTH]%N% Waiting for services...

call :wait_for "Model router"   "http://localhost:!CODER_PORT!/_aiden/pipeline" 60
call :wait_for "llama.cpp MTP" "http://localhost:!LLAMACPP_PORT!/v1/models" 180
call :wait_for "Coder Proxy"    "http://localhost:!CODER_PORT!/"  30
call :wait_for "Llama Proxy"    "http://localhost:!LLAMA_PORT!/"  30
call :wait_for "Vision Proxy"   "http://localhost:!VISION_PORT!/" 30
call :wait_for "Open WebUI"     "http://localhost:!WEBUI_PORT!/"  90

echo !COMPOSE_PROFILES! | findstr /i "hermes" >nul 2>&1
if not errorlevel 1 (
    call :wait_for "Hermes Agent"  "http://localhost:!HERMES_GATEWAY_PORT!/" 90
)

echo.

if not exist "models\*.gguf" (
    echo %Y%[MODELS]%N% No GGUF in .\models\ — see models\README.md
    echo   Expected: models\!LLAMACPP_GGUF! ^(from .env^)
    echo.
)

:: ── Summary ─────────────────────────────────────────────────────
echo %G%[READY]%N% AI.DEN is online.
echo.
echo   %B%Pipeline ^(coder port !CODER_PORT! — use this for Cursor, NOT :8081 direct^)%N%
echo     %G%http://127.0.0.1:!CODER_PORT!/_aiden/pipeline%N%        %D%GET stages%N%
echo     %G%http://127.0.0.1:!CODER_PORT!/_aiden/pipeline/preview%N% %D%preview claw+caveman%N%
echo     %G%http://127.0.0.1:!CODER_PORT!/_aiden/swagger%N%       %D%Swagger UI%N%
echo.
echo   %B%Endpoints%N%
echo   -----------------------------------------------
echo   Coder API   %C%http://localhost:!CODER_PORT!%N%   !CODER!
echo   Llama API   %C%http://localhost:!LLAMA_PORT!%N%   !LLAMA!
echo   Vision API  %C%http://localhost:!VISION_PORT!%N%   !VISION!
echo   Web UI      %C%http://localhost:!WEBUI_PORT!%N%
echo   Ollama      %C%http://localhost:!OLLAMA_PORT!%N%  ^(direct^)
if /i "!LLAMA_BACKEND!"=="llamacpp" (
    echo   llama.cpp   %C%http://localhost:!LLAMACPP_PORT!/v1%N%  ^(MTP direct^)
)
echo !COMPOSE_PROFILES! | findstr /i "hermes" >nul 2>&1
if not errorlevel 1 (
    echo   Hermes      %C%http://localhost:!HERMES_GATEWAY_PORT!%N%  ^(gateway API^)
)
echo.
echo   %B%Commands%N%  ^(open a second terminal^)
echo   -----------------------------------------------
echo   %D%start-aiden.bat status%N%      Show health
echo   %D%start-aiden.bat pull%N%        Download models
echo   %D%start-aiden.bat cpu%N%         Restart without GPU
echo   %D%start-aiden.bat help%N%        All commands
echo   %D%launch-claw.bat help%N%        Claw CLI ^(native claw.exe or Docker openclaw^)
echo.
echo   %D%prompt pipeline HTTP%N%
echo     GET  http://localhost:!CODER_PORT!/_aiden/pipeline
echo     Swagger  http://localhost:!CODER_PORT!/_aiden/swagger
echo     OpenAPI  http://localhost:!CODER_PORT!/_aiden/openapi.yaml
echo     POST JSON ^{"stages":["claw","caveman"]^} — drop claw or caveman to disable
echo     ^(set AIDEN_ADMIN_TOKEN in .env to require Bearer auth on POST^)
echo.

call :maybe_launch_claw

:: ── Keep-alive: attach foreground ───────────────────────────────
:: Stops the detached containers then re-launches in foreground.
:: Closing this window or pressing Ctrl+C will stop everything.
title AI.DEN - Local AI Cluster [RUNNING]
echo %C%[LIVE]%N% AI.DEN is running. %B%Close this window%N% or %B%Ctrl+C%N% to shut down.
echo.
echo %D%--- streaming container logs ---%N%
echo.

:: Bring down detached containers, then restart attached to this terminal.
:: When this window closes, Docker Compose stops all containers.
docker compose stop >nul 2>&1
if "!GPU_MODE!"=="0" (
    docker compose -f docker-compose.yml -f docker-compose.cpu.yml %COMPOSE_EXTRA% up
) else (
    docker compose %COMPOSE_EXTRA% up
)

:: ── Shutdown (reached after Ctrl+C) ─────────────────────────────
title AI.DEN - Shutting Down
echo.
echo %Y%[STOP]%N% Shutting down AI.DEN...
if "!GPU_MODE!"=="0" (
    docker compose -f docker-compose.yml -f docker-compose.cpu.yml %COMPOSE_EXTRA% down >nul 2>nul
) else (
    docker compose %COMPOSE_EXTRA% down >nul 2>nul
)
echo %G%[DONE]%N% AI.DEN stopped. All containers removed.
echo.
pause
goto :eof

REM Optional Claw CLI window — called from READY summary
:maybe_launch_claw
if /i "!AUTO_LAUNCH_CLAW!"=="false" exit /b 0
if /i "!AUTO_LAUNCH_CLAW!"=="0" exit /b 0
if /i "!AUTO_LAUNCH_CLAW!"=="no" exit /b 0
if /i "!AUTO_LAUNCH_CLAW!"=="off" exit /b 0
start "AIDEN — Claw" /D "%~dp0" cmd /k call launch-claw.bat
exit /b 0

:: ════════════════════════════════════════════════════════════════
:: wait_for  <label> <url> <timeout_seconds>
:: ════════════════════════════════════════════════════════════════
:wait_for
setlocal
set "LABEL=%~1"
set "URL=%~2"
set /a "TIMEOUT=%~3"
set /a "ELAPSED=0"

<nul set /p "=  Waiting for %B%%LABEL%%N% "

:wait_loop
if !ELAPSED! geq !TIMEOUT! (
    echo  %R%timeout%N%
    endlocal
    goto :eof
)
curl -sf -o nul -m 2 "%URL%" >nul 2>&1
if not errorlevel 1 (
    echo  %G%ready%N%
    endlocal
    goto :eof
)
<nul set /p "=."
timeout /t 2 /nobreak >nul
set /a "ELAPSED+=2"
goto :wait_loop
