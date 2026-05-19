# Git layout for AI.DEN

## One repo, many origins

This project is intentionally a **monorepo**:

- **One** `.git` at the repository root
- **No** nested `.git` inside `caveman/`, `claw-code-local/`, `ollama-mcp/`, `pymadcad/`, or `unsloth/`
- Upstream URLs and integration commits are recorded in **`UPSTREAM.md`**

That avoids submodule pain in Docker/Windows workflows while keeping a clear audit trail of forks.

## What is tracked vs ignored

| Tracked | Ignored (see `.gitignore`) |
|---------|----------------------------|
| Compose, proxy, scripts, docs | `.env` (secrets) — use `.env.example` |
| Patched `ollama-mcp/server.py` | `models/*.gguf` (multi-GB) |
| Vendored source trees | `**/target/`, `node_modules/` |
| `proxy/*.txt` pipeline prompts | `.claw/` sessions, Docker volumes |

## First-time setup

```powershell
cd AI.DEN
copy .env.example .env
# edit .env — never commit it

git status
```

## Initial remote (GitHub / GitLab)

```powershell
git remote add origin https://github.com/YOUR_USER/AI.DEN.git
git branch -M main
git push -u origin main
```

## If nested `.git` reappears

Cloning a subproject inside the tree recreates nested repos. Remove them:

```powershell
.\scripts\remove-nested-git.ps1
git add -A
git commit -m "chore: remove accidental nested git repos"
```

## Line endings

Shell entrypoints use **LF** (`scripts/*.sh` in `.gitattributes`). Use Git defaults on Windows:

```powershell
git config core.autocrlf true
```
