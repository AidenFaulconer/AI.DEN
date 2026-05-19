# Remove nested .git directories so AI.DEN stays a single repository
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$removed = @()

Get-ChildItem -Path $root -Filter ".git" -Recurse -Force -Directory | ForEach-Object {
    if ($_.FullName -eq (Join-Path $root ".git")) { return }
    Write-Host "Removing $($_.FullName)"
    Remove-Item -LiteralPath $_.FullName -Recurse -Force
    $removed += $_.FullName
}

if ($removed.Count -eq 0) {
    Write-Host "No nested .git directories found."
} else {
    Write-Host "Removed $($removed.Count) nested repo(s). Root .git is unchanged."
}
