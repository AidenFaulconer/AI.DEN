@echo off
setlocal EnableDelayedExpansion
chcp 65001 >nul 2>&1
cd /d "%~dp0"

:: Claw Code (Rust CLI) wired to AI.DEN OpenAI-compatible proxy.
:: Upstream: https://github.com/ultraworkers/claw-code  — USAGE.md (Ollama / OpenAI-compat).

set "CODER=qwen2.5-coder:7b"
set "LLAMA=llama3.1:8b"
set "VISION=gemma4"
set "CODER_PORT=8765"
set "LLAMA_PORT=8766"
set "VISION_PORT=8767"
set "GATEWAY_PORT=11434"

if exist ".env" (
    for /f "usebackq tokens=1,* delims==" %%a in (".env") do (
        if "%%a"=="CODER_MODEL" set "CODER=%%b"
        if "%%a"=="LLAMA_MODEL" set "LLAMA=%%b"
        if "%%a"=="VISION_MODEL" set "VISION=%%b"
        if "%%a"=="CODER_PORT" set "CODER_PORT=%%b"
        if "%%a"=="LLAMA_PORT" set "LLAMA_PORT=%%b"
        if "%%a"=="VISION_PORT" set "VISION_PORT=%%b"
        if "%%a"=="OLLAMA_PORT" set "GATEWAY_PORT=%%b"
    )
)

if /i "%~1"=="help" goto :help
if /i "%~1"=="/?" goto :help

set "PROFILE=coder"
set "AIDEN_MODEL=!CODER!"
set "AIDEN_PORT=!CODER_PORT!"
set "SKIP=0"

if /i "%~1"=="general" (
    set "PROFILE=general"
    set "AIDEN_MODEL=!LLAMA!"
    set "AIDEN_PORT=!LLAMA_PORT!"
    set "SKIP=1"
)
if /i "%~1"=="llama" (
    set "PROFILE=general"
    set "AIDEN_MODEL=!LLAMA!"
    set "AIDEN_PORT=!LLAMA_PORT!"
    set "SKIP=1"
)
if /i "%~1"=="vision" (
    set "PROFILE=vision"
    set "AIDEN_MODEL=!VISION!"
    set "AIDEN_PORT=!VISION_PORT!"
    set "SKIP=1"
)
if /i "%~1"=="gateway" (
    set "PROFILE=gateway"
    set "AIDEN_MODEL=!CODER!"
    set "AIDEN_PORT=!GATEWAY_PORT!"
    set "SKIP=1"
)

:: Non-empty placeholder for OpenAI-compat (Ollama / AI.DEN); value is not sent to local stack.
set "OPENAI_API_KEY=ollama"
:: Avoid accidental Anthropic routing when using local models
set "ANTHROPIC_API_KEY="
set "ANTHROPIC_AUTH_TOKEN="

set "CLAW_USE_DOCKER=0"
set "CLAW_EXE="
if defined CLAW_BIN set "CLAW_EXE=!CLAW_BIN!"
if not defined CLAW_EXE if exist "%~dp0claw-code\rust\target\release\claw.exe" set "CLAW_EXE=%~dp0claw-code\rust\target\release\claw.exe"
if not defined CLAW_EXE if exist "%~dp0claw-code\rust\target\debug\claw.exe" set "CLAW_EXE=%~dp0claw-code\rust\target\debug\claw.exe"
if not defined CLAW_EXE (
    for /f "delims=" %%p in ('where claw.exe 2^>nul') do (
        set "CLAW_EXE=%%p"
        goto :have_claw
    )
)
:have_claw

if not defined CLAW_EXE (
    set "CLAW_USE_DOCKER=1"
    echo [!] claw.exe not found on PATH — using Docker image aiden-clawcode:local
    echo     Rebuild image: docker compose --profile claw build clawcode
    echo     Or build natively: cd claw-code\rust ^&^& cargo build --workspace --release
    docker info >nul 2>&1
    if errorlevel 1 (
        echo [!] Docker is not running. Start Docker Desktop or set CLAW_BIN to claw.exe
        goto :help_fail
    )
    docker image inspect aiden-clawcode:local >nul 2>&1
    if errorlevel 1 (
        echo [i] First-time Docker build for Claw ^(often 10–20 min^)...
        docker compose --profile claw build clawcode
        if errorlevel 1 (
            echo [!] docker compose build clawcode failed.
            goto :help_fail
        )
    )
)

:: Host: proxies listen on localhost. Container: reach host stack via host.docker.internal.
if "!CLAW_USE_DOCKER!"=="1" (
    set "OPENAI_BASE_URL=http://host.docker.internal:!AIDEN_PORT!/v1"
) else (
    set "OPENAI_BASE_URL=http://127.0.0.1:!AIDEN_PORT!/v1"
)

:: Claw rejects bare Ollama ids; use openai/name for OpenAI-compat routing (prefix stripped on the wire).
set "CLAW_MODEL=!AIDEN_MODEL!"
if /i "!CLAW_MODEL!"=="opus" goto :claw_model_ok
if /i "!CLAW_MODEL!"=="sonnet" goto :claw_model_ok
if /i "!CLAW_MODEL!"=="haiku" goto :claw_model_ok
echo !AIDEN_MODEL!| findstr /R /C:"/" >nul || set "CLAW_MODEL=openai/!AIDEN_MODEL!"
:claw_model_ok

echo.
echo  Claw Code + AI.DEN   https://github.com/ultraworkers/claw-code
if "!CLAW_USE_DOCKER!"=="1" (
    echo  runtime=Docker ^(aiden-clawcode:local^)   OPENAI_BASE_URL=!OPENAI_BASE_URL!
) else (
    echo  runtime=native "!CLAW_EXE!"   OPENAI_BASE_URL=!OPENAI_BASE_URL!
)
echo  profile=!PROFILE!    Ollama id=!AIDEN_MODEL!    --model=!CLAW_MODEL!
echo.

curl -sf -o nul -m 2 "http://127.0.0.1:!AIDEN_PORT!/" >nul 2>&1
if errorlevel 1 (
    echo [!] Nothing listening on port !AIDEN_PORT!. Start stack: start-aiden.bat
    echo.
)

:: Strip profile keyword from forwarded args
set "ARGS="
if "!SKIP!"=="1" (
    set "_skip=1"
    for %%A in (%*) do (
        if "!_skip!"=="1" ( set "_skip=0" ) else (
            if defined ARGS ( set "ARGS=!ARGS! %%~A" ) else ( set "ARGS=%%~A" )
        )
    )
) else (
    set "ARGS=%*"
)

if "!CLAW_USE_DOCKER!"=="1" (
    if "!ARGS!"=="" (
        echo Running: docker compose run clawcode --model "!CLAW_MODEL!"
        docker compose --profile claw run --rm -it -e "OPENAI_BASE_URL=!OPENAI_BASE_URL!" -e "OPENAI_API_KEY=!OPENAI_API_KEY!" -e ANTHROPIC_API_KEY= -e ANTHROPIC_AUTH_TOKEN= clawcode --model "!CLAW_MODEL!"
    ) else (
        echo Running: docker compose run clawcode --model "!CLAW_MODEL!" !ARGS!
        docker compose --profile claw run --rm -it -e "OPENAI_BASE_URL=!OPENAI_BASE_URL!" -e "OPENAI_API_KEY=!OPENAI_API_KEY!" -e ANTHROPIC_API_KEY= -e ANTHROPIC_AUTH_TOKEN= clawcode --model "!CLAW_MODEL!" !ARGS!
    )
) else (
    if "!ARGS!"=="" (
        "%CLAW_EXE%" --model "!CLAW_MODEL!"
    ) else (
        echo Running: "%CLAW_EXE%" --model "!CLAW_MODEL!" !ARGS!
        "%CLAW_EXE%" --model "!CLAW_MODEL!" !ARGS!
    )
)
endlocal & exit /b 0

:help_fail
endlocal & exit /b 1

:help
echo.
echo launch-claw.bat  [ coder ^| general ^| vision ^| gateway ]  [claw args...]
echo.
echo Sets OPENAI_BASE_URL to AI.DEN proxy and OPENAI_API_KEY=ollama ^(required for OpenAI-compat routing^).
echo Clears ANTHROPIC_* so local models do not drift to Claude API.
echo Bare Ollama names from `.env` run as `--model openai/^<id^>` ^(Claw syntax; proxy still sees the real id^).
echo.
echo   coder ^(default^)  port CODER_PORT  + model CODER_MODEL
echo   general / llama   port LLAMA_PORT  + model LLAMA_MODEL
echo   vision            port VISION_PORT + model VISION_MODEL
echo   gateway           port OLLAMA_PORT  + model CODER_MODEL ^(pick another via --model yourself^)
echo.
echo Without claw.exe, the script builds / runs Docker image aiden-clawcode:local ^(compose profile claw^).
echo Examples:
echo   launch-claw.bat prompt "say hello"
echo   launch-claw.bat general prompt "summarize README.md"
echo   launch-claw.bat --permission-mode read-only prompt "list src folder"
echo.
echo Source + docs:  .\claw-code\       USAGE.md, README.md
echo.
endlocal & exit /b 0
