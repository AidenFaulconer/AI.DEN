# Download a small Qwen3 draft GGUF for speculative decoding (draft mode)
$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
$modelsDir = Join-Path $repoRoot "models"
$draftName = if ($env:LLAMACPP_DRAFT_GGUF) { $env:LLAMACPP_DRAFT_GGUF } else { "Qwen3-4B-Instruct-2507-Q4_K_M.gguf" }
$dest = Join-Path $modelsDir $draftName

if (-not (Test-Path $modelsDir)) { New-Item -ItemType Directory -Path $modelsDir | Out-Null }

if (Test-Path $dest) {
    Write-Host "Already exists: $dest"
    exit 0
}

# bartowski quant — adjust repo/file if you prefer another mirror
$hfRepo = "bartowski/Qwen3-4B-Instruct-2507-GGUF"
Write-Host "Downloading $draftName from $hfRepo ..."
Write-Host "Destination: $dest"

$hfCli = Get-Command huggingface-cli -ErrorAction SilentlyContinue
if ($hfCli) {
    Push-Location $modelsDir
    huggingface-cli download $hfRepo $draftName --local-dir .
    Pop-Location
    if (Test-Path $dest) { Write-Host "Done."; exit 0 }
}

# curl fallback (Windows SSL)
$url = "https://huggingface.co/$hfRepo/resolve/main/$draftName"
Write-Host "Trying curl: $url"
curl.exe -L --ssl-no-revoke -o $dest $url
if (Test-Path $dest) { Write-Host "Done: $dest" } else { Write-Error "Download failed" }
