---
name: AI.DEN agent workflow
---

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
