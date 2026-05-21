---
name: AI.DEN workspace
---

You run against the local AI.DEN stack (model-router + llama.cpp), not cloud APIs.

- Coder (default): `http://localhost:8765/v1` — claw + caveman pipeline injected automatically.
- General: `http://localhost:8766/v1` — same pipeline, `LLAMA_MODEL` from `.env`.
- Model id must match `GET http://localhost:8765/v1/models` (GGUF filename when using llama.cpp).
- Do not point Continue at bare `:8081` if you want the prompt pipeline.

## Repo context (@tree / @repo-map)

- **`@tree`** — folder structure (low token cost).
- **`@repo-map`** — file list + signatures; on 4GB signatures are **off** after sync. In the `@` menu, pick a **subfolder**, not “Entire codebase”.
- **`node_modules`** — excluded via `.continueignore` + `.gitignore` (not fully mapped).
- Details: `docs/continue-repo-context.md`

## Claw Code (optional, terminal)

Continue does not embed Claw. Same AI stack: `launch-claw.bat` → `:8765`. Slash **`/Claw terminal`** or `docs/claw-with-continue.md`. Optional MCP: `continue/claw.settings.example.json` → `%USERPROFILE%\.claw\settings.json`.

## MCP workspace (important)

MCP follows the **VS Code / Continue workspace** via MCP `roots` (no script per project). Docker must mount a **parent folder** that contains your repo (default: `AIDEN_MCP_WORKSPACE_HOST=..` → all of `vibe-coding` at `/workspace`).

If paths fail: call MCP `workspace_info`, or widen the mount in AI.DEN `.env` and recreate `mcp-server` + `ctags-indexer`.

## MCP tools (AI.DEN Ollama MCP on :5000)

Use **only** these names via native tool_calls (never print XML in chat/thought text):

| Task | MCP tool | Example args |
|------|----------|----------------|
| Wrong project / paths fail | `workspace_info` | (no args) — shows mounted root |
| Find files | `glob_files` | `pattern: "**/config.yaml"` |
| List directory | `list_dir` | `path: "continue"` or `path: "."` |
| Read file | `read_file` | `path: "continue/config.yaml"` |
| Shell | `run_command` | `command: "dir continue"` |
| Compile/deprecation fix | `web_search` | `query: "Rust E0382 borrow moved"` |
| Library API docs (free) | `library_docs` | `library: "react"`, `query: "useEffect cleanup"`, `ecosystem: npm` |
| List project packages | `project_dependencies` | (no args) |
| Doc URL | `fetch_url` | `url: "https://..."` |
| Symbol in repo | `symbol_search` | `query: "AgentLoop"` — uses `.aiden/tags` from **ctags-indexer** when ready |

**Wrong names (do not use):** `file_glob_search`, `ls`, `file_read`, `<tool_call>`, `<function=...>`.

**Library docs:** use `library_docs` (free) — see `docs/free-library-docs.md`. Do not use paid Context7 unless you opt in separately.

For "where is config.yaml": call `glob_files` with `**/config.yaml` — answer is usually `continue/config.yaml`.

Prefer small, correct diffs.

## Continue + VS Code (errors & tests)

- **Errors:** user attaches `@problems` (Problems panel) and/or `@terminal` — you do not see them otherwise.
- **Agent mode** required for MCP tools to run (not Chat-only).
- **Tests:** `project_tasks` → `run_tests` or `run_command` (MCP container). Host scripts (`start-aiden.bat`, `npm run dev`) → user runs in VS Code terminal, then `@terminal`.
- Slash prompts: `/Fix errors`, `/Run tests`, `/Start AI.DEN stack`.

See `docs/continue-vscode.md` and `continue/agent-workflow.md`.
