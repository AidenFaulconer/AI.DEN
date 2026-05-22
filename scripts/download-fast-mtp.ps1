# Download Qwen3.5-9B MTP GGUF for llamacpp-fast (dual-model routing)
$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
$modelsDir = Join-Path $repoRoot "models"
$fastName = if ($env:LLAMACPP_FAST_GGUF) { $env:LLAMACPP_FAST_GGUF } else { "Qwen3.5-9B-UD-Q4_K_XL.gguf" }
$dest = Join-Path $modelsDir $fastName

if (-not (Test-Path $modelsDir)) { New-Item -ItemType Directory -Path $modelsDir | Out-Null }

if (Test-Path $dest) {
    Write-Host "Already exists: $dest"
    exit 0
}

$hfRepo = "unsloth/Qwen3.5-9B-MTP-GGUF"
Write-Host "Downloading $fastName from $hfRepo ..."
Write-Host "Destination: $dest"

$hfCli = Get-Command huggingface-cli -ErrorAction SilentlyContinue
if ($hfCli) {
    Push-Location $modelsDir
    huggingface-cli download $hfRepo $fastName --local-dir .
    Pop-Location
    if (Test-Path $dest) { Write-Host "Done."; exit 0 }
}

$url = "https://huggingface.co/$hfRepo/resolve/main/$fastName"
Write-Host "Trying curl: $url"
curl.exe -L --ssl-no-revoke -o $dest $url
if (Test-Path $dest) { Write-Host "Done: $dest" } else { Write-Error "Download failed" }
