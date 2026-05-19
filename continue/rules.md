---
name: AI.DEN workspace
---

You run against the local AI.DEN stack (model-router + llama.cpp), not cloud APIs.

- Coder (default): `http://localhost:8765/v1` — claw + caveman pipeline injected automatically.
- General: `http://localhost:8766/v1` — same pipeline, `LLAMA_MODEL` from `.env`.
- Model id must match `GET http://localhost:8765/v1/models` (GGUF filename when using llama.cpp).
- Do not point Continue at bare `:8081` if you want the prompt pipeline.

## MCP tools (AI.DEN Ollama MCP on :5000)

Use **only** these names via native tool_calls (never print XML in chat/thought text):

| Task | MCP tool | Example args |
|------|----------|----------------|
| Find files | `glob_files` | `pattern: "**/config.yaml"` |
| List directory | `list_dir` | `path: "continue"` or `path: "."` |
| Read file | `read_file` | `path: "continue/config.yaml"` |
| Shell | `run_command` | `command: "dir continue"` |

**Wrong names (do not use):** `file_glob_search`, `ls`, `file_read`, `<tool_call>`, `<function=...>`.

For "where is config.yaml": call `glob_files` with `**/config.yaml` — answer is usually `continue/config.yaml`.

Prefer small, correct diffs. Run terminal commands when they unblock the task.
