---
name: Start AI.DEN stack
description: Start or check local AI.DEN Docker stack
invokable: true
---

AI.DEN stack runs on the **Windows host**, not inside the MCP container.

1. Tell user to run in VS Code terminal: `start-aiden.bat` or `start-aiden.bat status`.
2. MCP run_command may use: `docker compose ps`, `docker compose logs mcp-server --tail 30`.
3. Endpoints: coder API :8765, MCP :5000/mcp, llama :8081.

If containers are down, user must start Docker Desktop first.
