# Continue in VS Code + AI.DEN

## Can Continue auto-detect errors?

**Partially — you enable it, it is not magic background polling.**

| Feature | How it works |
|---------|----------------|
| **Problems / diagnostics** | `@problems` context provider reads the VS Code **Problems** panel (TS, ESLint, Python, etc.) for the **current file**. Add `@problems` to the prompt or use the **/Fix errors** prompt. |
| **Terminal output** | `@terminal` attaches the **last command** from the integrated terminal + output. Run a test, then ask the agent with `@terminal`. |
| **Auto on every message** | No — unless you @-mention or use **Agent** mode with a prompt that tells the model to use them. |

Configured in `continue/config.yaml` under `context:` (`problems`, `terminal`, …).

## Can Continue run terminals / tests?

| Mechanism | Runs where | Best for |
|-----------|------------|----------|
| **Continue Agent + MCP `run_command`** | Linux `mcp-server` container | `docker compose`, `python`, `pytest` in repo |
| **MCP `run_tests`** | Same | Default verify (`docker compose config`, py_compile, …) |
| **MCP `project_tasks`** | Same | Lists stack/test/lint commands |
| **VS Code integrated terminal** | Windows host | `start-aiden.bat`, `npm run dev`, local Node apps |
| **@terminal** | N/A (context only) | Feed last terminal output to the model |

**Use Agent mode** (not Chat-only) so MCP tools execute. Model must have `tool_use` (configured).

## MCP workspace must match your VS Code project

By default Docker mounts the **AI.DEN** repo at `/workspace`. If you open **another project** in VS Code, `read_file` for `frontend/src/...` fails — that path is not in AI.DEN.

**Fix** (run once per project, from your app repo root):

```powershell
C:\path\to\AI.DEN\scripts\use-mcp-workspace.ps1
```

Or set in AI.DEN `.env`:

```env
AIDEN_MCP_WORKSPACE_HOST=C:/path/to/your-frontend-app
```

Then:

```powershell
cd C:\path\to\AI.DEN
docker compose up -d --force-recreate mcp-server ctags-indexer
```

Verify: `http://localhost:5000/health` → `workspace_root` and `sample_entries` should match your app (e.g. `frontend/`, `package.json`).

MCP tools: `workspace_info`, `glob_files` with `**/contact.jsx`.

## Setup checklist

1. Stack up: `start-aiden.bat`
2. Point MCP at your project: `use-mcp-workspace.ps1` (if not editing AI.DEN itself)
3. Sync config: `.\scripts\sync-continue-config.ps1` (writes `~/.continue/config.yaml` with **absolute paths**, not `file:///` — Continue on Windows doubles `C:\` with `file:///C:/...`)
4. VS Code: **Reload Window** (or reload Continue), select **AI.DEN Coder**, open **Agent** panel
5. Enable MCP server **AI.DEN Ollama MCP** in Continue settings (verify `http://localhost:5000/health` returns 200 first)
6. Rebuild MCP after updates: `docker compose up -d --build mcp-server`

## Slash prompts

- `/Fix errors` — @problems workflow + run_tests
- `/Run tests` — project_tasks + run_tests
- `/Start AI.DEN stack` — host vs docker guidance

## Repo map and ignores

See **[continue-repo-context.md](continue-repo-context.md)** — `@tree` + `@repo-map`, `.continueignore`, hardware-aware signatures.

## Claw Code alongside Continue

See **[claw-with-continue.md](claw-with-continue.md)** — terminal agent on the same `:8765` router; not inside Continue.

## Limits (local 27B)

- Agent may fail to call tools reliably — use low temperature (0.15 in config).
- `run_command` cannot run Windows `.bat` files inside Linux MCP — use host terminal.
- Problems provider is **per current file**, not whole workspace — use grep or @repo-map for other files.
