---
name: AI.DEN workspace
---

You run against the local AI.DEN stack (model-router + llama.cpp), not cloud APIs.

- Coder (default): `http://localhost:8765/v1` — claw + caveman pipeline injected automatically.
- General: `http://localhost:8766/v1` — same pipeline, `LLAMA_MODEL` from `.env`.
- Model id must match `GET http://localhost:8765/v1/models` (GGUF filename when using llama.cpp).
- Do not point Continue at bare `:8081` if you want the prompt pipeline.
- For Ollama MCP tools (list_models, read_file, …), use the **AI.DEN MCP** server on port 5000 when enabled in config.

Prefer small, correct diffs. Run terminal commands when they unblock the task.
