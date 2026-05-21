# Sync AI.DEN .env + repo paths -> ~/.continue/config.yaml for VS Code Continue
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

function To-FileUri([string]$path) {
    $p = ($path -replace '\\', '/') -replace ' ', '%20'
    return "file:///$p"
}

$coderModel = Get-EnvValue "CODER_MODEL" "Qwen3.6-27B-MTP-UD-Q4_K_XL.gguf"
$llamaModel = Get-EnvValue "LLAMA_MODEL" $coderModel
$coderPort = Get-EnvValue "CODER_PORT" "8765"
$llamaPort = Get-EnvValue "LLAMA_PORT" "8766"
$mcpPort = Get-EnvValue "MCP_PORT" "5000"
$ctxSize = Get-EnvValue "LLAMACPP_CTX_SIZE" "16384"
$maxTokens = Get-EnvValue "OLLAMA_MCP_MAX_TOKENS" "1536"
$fitTarget = [int](Get-EnvValue "LLAMACPP_FIT_TARGET" "512")
$repoSigs = Get-EnvValue "AIDEN_REPO_MAP_SIGNATURES" ""
if ($repoSigs -eq "") {
    $repoSigs = if ($fitTarget -gt 768) { "true" } else { "false" }
}
# 4GB profile: smaller Continue window unless .env overrides ctx
if ($fitTarget -le 768 -and $ctxSize -gt 8192) {
    $ctxSize = "8192"
}

$rulesUri = To-FileUri (Join-Path $repoRoot "continue\rules.md")
$agentUri = To-FileUri (Join-Path $repoRoot "continue\agent-workflow.md")
$promptFix = To-FileUri (Join-Path $repoRoot "continue\prompts\fix-errors.md")
$promptTest = To-FileUri (Join-Path $repoRoot "continue\prompts\run-tests.md")
$promptStack = To-FileUri (Join-Path $repoRoot "continue\prompts\start-stack.md")

if (-not (Test-Path $continueDir)) {
    New-Item -ItemType Directory -Path $continueDir | Out-Null
}

$content = Get-Content $template -Raw
$content = $content -replace 'model: Qwen3\.6-27B-MTP-UD-Q4_K_XL\.gguf', "model: $coderModel"
$content = $content -replace '(apiBase: http://localhost:)8765(/v1)', "`${1}${coderPort}`${2}"
$content = $content -replace '(name: AI\.DEN General[^\r\n]*\r?\n(?:[^\r\n]*\r?\n)*?    model: )Qwen3\.6-27B-MTP-UD-Q4_K_XL\.gguf', "`${1}$llamaModel"
$content = $content -replace '(apiBase: http://localhost:)8766(/v1)', "`${1}${llamaPort}`${2}"
$content = $content -replace 'http://localhost:5000/mcp', "http://localhost:${mcpPort}/mcp"
$content = $content -replace 'contextLength: \d+', "contextLength: $ctxSize"
$content = $content -replace 'maxTokens: \d+', "maxTokens: $maxTokens"
$content = $content -replace 'includeSignatures: (true|false)', "includeSignatures: $repoSigs"

# Rewrite all file:// rules/prompts to this machine's repo path
$content = $content -replace 'file:///[^`\r\n]+/continue/rules\.md', $rulesUri
$content = $content -replace 'file:///[^`\r\n]+/continue/agent-workflow\.md', $agentUri
$content = $content -replace 'file:///[^`\r\n]+/continue/prompts/fix-errors\.md', $promptFix
$content = $content -replace 'file:///[^`\r\n]+/continue/prompts/run-tests\.md', $promptTest
$content = $content -replace 'file:///[^`\r\n]+/continue/prompts/start-stack\.md', $promptStack
$promptClaw = To-FileUri (Join-Path $repoRoot "continue\prompts\claw-terminal.md")
$content = $content -replace 'file:///[^`\r\n]+/continue/prompts/claw-terminal\.md', $promptClaw

Set-Content -Path $dest -Value $content -Encoding UTF8

# Workspace ignore file (node_modules, dist, …) — Continue + repo-map indexing
$ignoreTemplate = Join-Path $repoRoot "continue\.continueignore"
$ignoreDest = Join-Path $repoRoot ".continueignore"
if ((Test-Path $ignoreTemplate) -and -not (Test-Path $ignoreDest)) {
    Copy-Item $ignoreTemplate $ignoreDest
    Write-Host "Created .continueignore at repo root (from continue/.continueignore)"
}

Write-Host "Wrote Continue config: $dest"
Write-Host "  Coder: http://localhost:${coderPort}/v1  model=$coderModel  ctx=$ctxSize"
Write-Host "  MCP:   http://localhost:${mcpPort}/mcp"
Write-Host "  @repo-map includeSignatures=$repoSigs  (FIT_TARGET=$fitTarget)"
Write-Host '  Use Agent mode + @problems @tree @repo-map (subfolder) - docs/continue-repo-context.md'
Write-Host '  Claw terminal: launch-claw.bat  |  docs/claw-with-continue.md'
Write-Host "Reload Continue in VS Code after stack is up."
