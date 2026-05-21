---
name: Claw terminal
description: Run the Claw Code CLI against the same AI.DEN stack (parallel to Continue Agent).
---

Use **Continue** for IDE edits and MCP tools in this chat.

For a **terminal agent harness** (bash loops, `/commit`, long autonomous runs), open a VS Code terminal in the project root and run:

```powershell
cd C:\path\to\AI.DEN
.\launch-claw.bat prompt "YOUR TASK HERE"
```

Interactive REPL: `.\launch-claw.bat` (same model + caveman pipeline as port 8765).

Optional shared MCP (library_docs, symbol_search): copy `continue/claw.settings.example.json` to `%USERPROFILE%\.claw\settings.json`, then `/mcp` inside Claw.

See `docs/claw-with-continue.md`.
