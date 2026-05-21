---
name: Fix errors
description: Fix VS Code Problems and verify with tests
invokable: true
---

Fix all issues using this workflow:

1. Include context: @problems @currentFile @terminal (if user ran a command).
2. MCP read_file / grep_search / symbol_search to locate causes.
3. MCP edit_file with minimal diffs.
4. MCP run_tests (or project_tasks then run_command).
5. If host-only (start-aiden.bat, npm run dev), tell user the exact terminal command.

Do not guess API names — use library_docs for library questions.
