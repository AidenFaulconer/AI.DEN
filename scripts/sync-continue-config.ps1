# Sync AI.DEN .env → ~/.continue/config.yaml for VS Code Continue
$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
$envFile = Join-Path $repoRoot ".env"
$template = Join-Path $repoRoot "continue\config.yaml"
$continueDir = Join-Path $env:USERPROFILE ".continue"
$dest = Join-Path $continueDir "config.yaml"

if (-not (Test-Path $template)) {
    Write-Error "Missing template: $template"
}

function Get-EnvValue([string]$key, [string]$default = "") {
    if (-not (Test-Path $envFile)) { return $default }
    foreach ($line in Get-Content $envFile) {
        if ($line -match "^\s*$key\s*=\s*(.+)\s*$") {
            return $Matches[1].Trim().Trim('"')
        }
    }
    return $default
}

$coderModel = Get-EnvValue "CODER_MODEL" "Qwen3.6-27B-MTP-UD-Q4_K_XL.gguf"
$llamaModel = Get-EnvValue "LLAMA_MODEL" $coderModel
$coderPort = Get-EnvValue "CODER_PORT" "8765"
$llamaPort = Get-EnvValue "LLAMA_PORT" "8766"
$mcpPort = Get-EnvValue "MCP_PORT" "5000"
$rulesPath = (Join-Path $repoRoot "continue\rules.md") -replace '\\', '/'

$yaml = Get-Content $template -Raw
$yaml = $yaml -replace 'Qwen3\.6-27B-MTP-UD-Q4_K_XL\.gguf', [regex]::Escape($coderModel)
$yaml = $yaml -replace 'http://localhost:8765/v1', "http://localhost:${coderPort}/v1"
$yaml = $yaml -replace 'http://localhost:8766/v1', "http://localhost:${llamaPort}/v1"
$yaml = $yaml -replace 'http://localhost:5000/mcp', "http://localhost:${mcpPort}/mcp"
$yaml = $yaml -replace 'file:///C:/Users/aidenleefaulconer/Downloads/vibe-coding/AI.DEN/continue/rules.md', "file:///$($rulesPath -replace ' ', '%20')"

if (-not (Test-Path $continueDir)) {
    New-Item -ItemType Directory -Path $continueDir | Out-Null
}
Copy-Item -Path $template -Destination $dest -Force
# Apply substitutions on dest (template copy then patch)
$content = Get-Content $dest -Raw
$content = $content -replace 'model: Qwen3\.6-27B-MTP-UD-Q4_K_XL\.gguf', "model: $coderModel"
$content = $content -replace '(apiBase: http://localhost:)8765(/v1)', "`${1}${coderPort}`${2}"
$content = $content -replace '(name: AI\.DEN General.*\r?\n(?:.*\r?\n)*?    model: )Qwen3\.6-27B-MTP-UD-Q4_K_XL\.gguf', "`${1}$llamaModel"
$content = $content -replace '(apiBase: http://localhost:)8766(/v1)', "`${1}${llamaPort}`${2}"
$content = $content -replace 'http://localhost:5000/mcp', "http://localhost:${mcpPort}/mcp"
$content = $content -replace 'file:///C:/Users/aidenleefaulconer/Downloads/vibe-coding/AI.DEN/continue/rules.md', "file:///$($rulesPath -replace ' ', '%20')"
Set-Content -Path $dest -Value $content -Encoding UTF8

Write-Host "Wrote Continue config: $dest"
Write-Host "  Coder: http://localhost:${coderPort}/v1  model=$coderModel"
Write-Host "  MCP:   http://localhost:${mcpPort}/mcp"
Write-Host "Reload Continue in VS Code (or restart window) after stack is up."
