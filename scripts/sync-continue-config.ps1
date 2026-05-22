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

# Continue on Windows breaks file:///C:/... (ENOENT C:\C:\...). Use forward-slash absolute paths.
function To-ContinuePath([string]$path) {
    return (Resolve-Path -LiteralPath $path).Path -replace '\\', '/'
}

$coderModel = Get-EnvValue "CODER_MODEL" "Qwen3.6-27B-MTP-UD-Q4_K_XL.gguf"
$fastModel = Get-EnvValue "CODER_FAST_MODEL" "Qwen3.5-9B-UD-Q4_K_XL.gguf"
$llamaModel = Get-EnvValue "LLAMA_MODEL" $coderModel
$coderPort = Get-EnvValue "CODER_PORT" "8765"
$llamaPort = Get-EnvValue "LLAMA_PORT" "8766"
$mcpPort = Get-EnvValue "MCP_PORT" "5000"
$llamaCtx = Get-EnvValue "LLAMACPP_CTX_SIZE" "12288"
# Continue contextLength gates read_file max size; router still trims prompts (AIDEN_MAX_PROMPT_TOKENS).
$ctxSize = Get-EnvValue "AIDEN_CONTINUE_CONTEXT_LENGTH" $llamaCtx
$maxTokens = Get-EnvValue "OLLAMA_MCP_MAX_TOKENS" "1536"
$fitTarget = [int](Get-EnvValue "LLAMACPP_FIT_TARGET" "512")
$repoSigs = Get-EnvValue "AIDEN_REPO_MAP_SIGNATURES" ""
if ($repoSigs -eq "") {
    $repoSigs = if ($fitTarget -gt 768) { "true" } else { "false" }
}

$rulesPath = To-ContinuePath (Join-Path $repoRoot "continue\rules.md")
$agentPath = To-ContinuePath (Join-Path $repoRoot "continue\agent-workflow.md")
$promptFix = To-ContinuePath (Join-Path $repoRoot "continue\prompts\fix-errors.md")
$promptTest = To-ContinuePath (Join-Path $repoRoot "continue\prompts\run-tests.md")
$promptStack = To-ContinuePath (Join-Path $repoRoot "continue\prompts\start-stack.md")
$promptClaw = To-ContinuePath (Join-Path $repoRoot "continue\prompts\claw-terminal.md")

if (-not (Test-Path $continueDir)) {
    New-Item -ItemType Directory -Path $continueDir | Out-Null
}

$content = Get-Content $template -Raw
$content = $content -replace 'model: Qwen3\.5-9B-UD-Q4_K_XL\.gguf', "model: $fastModel"
$content = $content -replace '(name: AI\.DEN Coder \(Qwen3\.6 quality[^\r\n]*\r?\n(?:[^\r\n]*\r?\n)*?    model: )Qwen3\.6-27B-MTP-UD-Q4_K_XL\.gguf', "`${1}$coderModel"
$content = $content -replace 'model: Qwen3\.6-27B-MTP-UD-Q4_K_XL\.gguf', "model: $coderModel"
$content = $content -replace '(apiBase: http://localhost:)8765(/v1)', "`${1}${coderPort}`${2}"
$content = $content -replace '(name: AI\.DEN General[^\r\n]*\r?\n(?:[^\r\n]*\r?\n)*?    model: )Qwen3\.6-27B-MTP-UD-Q4_K_XL\.gguf', "`${1}$llamaModel"
$content = $content -replace '(apiBase: http://localhost:)8766(/v1)', "`${1}${llamaPort}`${2}"
$content = $content -replace 'http://localhost:5000/mcp', "http://localhost:${mcpPort}/mcp"
$content = $content -replace 'contextLength: \d+', "contextLength: $ctxSize"
$content = $content -replace 'maxTokens: \d+', "maxTokens: $maxTokens"
$content = $content -replace 'includeSignatures: (true|false)', "includeSignatures: $repoSigs"

# Absolute paths (no file://) — avoids Windows C:\C:\ bug in Continue
$content = $content -replace 'uses: continue/rules\.md', "uses: $rulesPath"
$content = $content -replace 'uses: continue/agent-workflow\.md', "uses: $agentPath"
$content = $content -replace 'uses: continue/prompts/fix-errors\.md', "uses: $promptFix"
$content = $content -replace 'uses: continue/prompts/run-tests\.md', "uses: $promptTest"
$content = $content -replace 'uses: continue/prompts/start-stack\.md', "uses: $promptStack"
$content = $content -replace 'uses: continue/prompts/claw-terminal\.md', "uses: $promptClaw"
# Legacy file:// entries from older templates
$content = $content -replace 'uses: file:///[^`\r\n]+/continue/rules\.md', "uses: $rulesPath"
$content = $content -replace 'uses: file:///[^`\r\n]+/continue/agent-workflow\.md', "uses: $agentPath"
$content = $content -replace 'uses: file:///[^`\r\n]+/continue/prompts/fix-errors\.md', "uses: $promptFix"
$content = $content -replace 'uses: file:///[^`\r\n]+/continue/prompts/run-tests\.md', "uses: $promptTest"
$content = $content -replace 'uses: file:///[^`\r\n]+/continue/prompts/start-stack\.md', "uses: $promptStack"
$content = $content -replace 'uses: file:///[^`\r\n]+/continue/prompts/claw-terminal\.md', "uses: $promptClaw"

Set-Content -Path $dest -Value $content -Encoding UTF8

# Workspace ignore file (node_modules, dist, …) — Continue + repo-map indexing
$ignoreTemplate = Join-Path $repoRoot "continue\.continueignore"
$ignoreDest = Join-Path $repoRoot ".continueignore"
if ((Test-Path $ignoreTemplate) -and -not (Test-Path $ignoreDest)) {
    Copy-Item $ignoreTemplate $ignoreDest
    Write-Host "Created .continueignore at repo root (from continue/.continueignore)"
}

Write-Host "Wrote Continue config: $dest"
Write-Host "  Coder: http://localhost:${coderPort}/v1  quality=$coderModel  fast=$fastModel  ctx=$ctxSize"
Write-Host "  Routing: $(Get-EnvValue 'AIDEN_MODEL_ROUTING' 'auto')  (see docs/dual-model-routing.md)"
Write-Host "  MCP:   http://localhost:${mcpPort}/mcp"
Write-Host "  @repo-map includeSignatures=$repoSigs  (FIT_TARGET=$fitTarget)"
Write-Host '  Agent mode: glob_files before read_file; @tree or @repo-map subfolder only - docs/continue-repo-context.md'
Write-Host '  Claw terminal: launch-claw.bat  |  docs/claw-with-continue.md'

$clawTemplate = Join-Path $repoRoot "continue\claw.settings.example.json"
$clawDest = Join-Path $env:USERPROFILE ".claw\settings.json"
if (Test-Path $clawTemplate) {
    $clawDir = Split-Path $clawDest -Parent
    if (-not (Test-Path $clawDir)) { New-Item -ItemType Directory -Path $clawDir | Out-Null }
    $clawJson = Get-Content $clawTemplate -Raw
    $clawJson = $clawJson -replace 'http://127.0.0.1:8765', "http://127.0.0.1:${coderPort}"
    $clawJson = $clawJson -replace 'http://127.0.0.1:5000', "http://127.0.0.1:${mcpPort}"
    $clawJson = $clawJson -replace 'openai/Qwen3\.6-27B-MTP-UD-Q4_K_XL\.gguf', "openai/$coderModel"
    Set-Content -Path $clawDest -Value $clawJson -Encoding UTF8
    Write-Host "  Claw MCP settings: $clawDest (duplicate builtins denied - docs/tool-policy.md)"
}

& (Join-Path $PSScriptRoot "sync-claude-md.ps1")

Write-Host "Reload Continue in VS Code after stack is up."
