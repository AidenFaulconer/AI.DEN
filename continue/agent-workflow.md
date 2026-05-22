---
name: AI.DEN agent workflow
---

## Finding files (MCP)

1. `glob_files` or `grep_search` — never `read_file` a path you have not verified.
2. `workspace_info` — if paths fail or workspace root is unclear.
3. `get_session_summary` — new thread or after switching from Claw when context was compacted.
3. **Monorepo:** VS Code on `AI.DEN` → use `House-App/...` prefixes; or open `House-App` as the workspace folder.

## Errors (VS Code)

- User should attach **@problems** (Problems panel: TypeScript, ESLint, Python, etc.).
- Attach **@terminal** after a failed command in the integrated terminal.
- You do not auto-see diagnostics unless @-mentioned or user is in **Agent** mode with context attached.

## Running tests / apps

| Where | Use for |
|-------|---------|
| MCP `project_tasks` | Discover test/stack/lint commands for this repo |
| MCP `run_tests` | Quick verify (`docker compose config`, py_compile, npm test) |
| MCP `run_command` | Shell inside MCP container (docker compose, python) |
| VS Code terminal + **@terminal** | `start-aiden.bat`, `npm run dev` on Windows host |
| MCP `agent_chat` | Multi-step fix + test loop |

## AI.DEN stack

- Start on host: `start-aiden.bat` (not inside MCP container).
- From MCP: `docker compose ps`, `docker compose logs mcp-server`.

After code changes: `run_tests` then ask user to confirm in browser/UI if needed.
