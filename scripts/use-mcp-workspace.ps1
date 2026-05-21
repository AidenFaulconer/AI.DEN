# Point AI.DEN MCP + ctags at the VS Code / Continue project folder (not the AI.DEN repo).
# Run from YOUR app repo root, or pass -ProjectPath.
param(
    [string]$ProjectPath = (Get-Location).Path
)

$ErrorActionPreference = "Stop"
$ProjectPath = (Resolve-Path $ProjectPath).Path
$aidenRoot = Split-Path -Parent $PSScriptRoot
$envFile = Join-Path $aidenRoot ".env"

if (-not (Test-Path $envFile)) {
    Write-Error "Missing $envFile — run from AI.DEN checkout."
}

# Docker Desktop on Windows accepts C:/ style paths
$dockerPath = $ProjectPath -replace '\\', '/'

function Set-EnvLine([string]$key, [string]$value) {
    $lines = Get-Content $envFile
    $found = $false
    $out = foreach ($line in $lines) {
        if ($line -match "^\s*$key\s*=") {
            $found = $true
            "$key=$value"
        } else {
            $line
        }
    }
    if (-not $found) {
        $out += "$key=$value"
    }
    Set-Content -Path $envFile -Value $out -Encoding UTF8
}

Set-EnvLine "AIDEN_MCP_WORKSPACE_HOST" $dockerPath
Write-Host "Set AIDEN_MCP_WORKSPACE_HOST=$dockerPath"
Write-Host "Recreating mcp-server + ctags-indexer..."
Push-Location $aidenRoot
try {
    docker compose up -d --force-recreate mcp-server ctags-indexer
    Start-Sleep -Seconds 2
    $health = Invoke-RestMethod -Uri "http://localhost:5000/health" -TimeoutSec 10
    Write-Host "MCP workspace_root: $($health.workspace_root)"
    Write-Host "Sample entries: $($health.sample_entries -join ', ')"
} finally {
    Pop-Location
}
Write-Host "Done. Continue read_file paths are relative to this folder."
