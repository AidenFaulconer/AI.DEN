# Upstream sources (vendored forks)

AI.DEN is a **single Git repository** (monorepo). These directories were originally separate clones; nested `.git` folders were removed so one history tracks the integrated solution.

| Path | Upstream | Pinned commit (at integration) | AI.DEN role |
|------|----------|-------------------------------|-------------|
| `caveman/` | https://github.com/JuliusBrussee/caveman | `ef6050c` | Caveman prompt / skill reference |
| `claw-code-local/` | https://github.com/codetwentyfive/claw-code-local | `f4cc5d7` | Claw CLI (Docker + native) |
| `ollama-mcp/` | https://github.com/jayluxferro/ollama-mcp | `cde4aa1` | MCP server (heavily patched) |
| `pymadcad/` | https://github.com/jimy-byerley/pymadcad | `f6c4bc3` | Optional CAD lib |
| `unsloth/` | https://github.com/unslothai/unsloth | `1c2a86f` | Optional training studio (`COMPOSE_PROFILES=unsloth`) |

**First-party (no upstream):** `proxy/`, `scripts/`, `docker-compose*.yml`, `start-aiden.bat`, `continue/`, `hermes-data/config.yaml`, `docs/`.

## Pulling upstream changes

There is no submodule wiring. To sync a component:

```powershell
cd claw-code-local
git init
git remote add upstream https://github.com/codetwentyfive/claw-code-local.git
git fetch upstream
git merge upstream/main
# resolve conflicts, test, then commit at AI.DEN root
cd ..
git add claw-code-local
git commit -m "chore: merge claw-code-local from upstream"
```

Repeat per directory. Prefer small, tested merges.

## Re-recording pins

After a merge, update the commit column in this file and run:

```powershell
.\scripts\record-upstream.ps1
```
