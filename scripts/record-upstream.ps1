# Append current HEAD of former sub-repos to UPSTREAM.md (run before removing nested .git)
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$repos = @{
    "caveman" = "https://github.com/JuliusBrussee/caveman"
    "claw-code-local" = "https://github.com/codetwentyfive/claw-code-local"
    "ollama-mcp" = "https://github.com/jayluxferro/ollama-mcp"
    "pymadcad" = "https://github.com/jimy-byerley/pymadcad"
    "unsloth" = "https://github.com/unslothai/unsloth"
}

Write-Host "Upstream pins (if .git still present):"
foreach ($name in $repos.Keys) {
    $p = Join-Path $root $name
    if (Test-Path (Join-Path $p ".git")) {
        $sha = git -C $p rev-parse --short HEAD 2>$null
        $subj = git -C $p log -1 --format="%s" 2>$null
        Write-Host "  $name : $sha — $subj"
    } else {
        Write-Host "  $name : (no nested .git)"
    }
}
