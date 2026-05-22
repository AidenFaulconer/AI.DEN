# Tool policy — one surface per capability

AI.DEN uses **MCP** (`:5000`) for Continue/Agent and optional **Claw** terminal tools. Duplicates are disabled so the model does not pick a weaker twin.

## Continue / MCP (primary)

| Capability | Tool | Disabled alternative |
|------------|------|-------------------|
| Read files | `read_file` | Claw `read_file` (deny in Claw settings) |
| Write / patch | `write_file`, `edit_file` | Claw builtins |
| Find paths | `glob_files` | Claw `glob_search`, aliases `glob_search` → `glob_files` |
| Search text | `grep_search` | — |
| Shell in workspace | `run_command` | Claw `bash` when MCP mounted (Linux container) |
| Symbols | `symbol_search` (ctags) | Claw `LSP` (heavy on 4GB) |
| Web | `web_search`, `fetch_url` | Claw `WebSearch`, `WebFetch` |
| Library docs | `library_docs` | `context7_docs` (alias only, not in tool list) |
| Stack / tests | `project_tasks`, `run_tests` | — |
| Resume after compaction | `get_session_summary` | manual `read_file` of `.aiden/last-session-summary.md` |

**Env:** `AIDEN_MCP_DISABLED_TOOLS=context7_docs,embed` (default). Set to `none` to expose all schemas.

## Claw terminal (when MCP attached)

Copy settings:

```powershell
copy continue\claw.settings.example.json %USERPROFILE%\.claw\settings.json
```

`permissions.deny` blocks Claw builtins that duplicate MCP. **Keep `bash`** for native Windows host commands (`.bat`, local `npm`). In Docker `clawcode`, prefer MCP `run_command` and add `bash` to deny if you only use the container workspace.

## Apply changes

```powershell
docker compose up -d --build mcp-server
docker compose up -d --force-recreate model-router
.\scripts\sync-continue-config.ps1
```

Reload Continue; restart Claw after updating `~/.claw/settings.json`.
