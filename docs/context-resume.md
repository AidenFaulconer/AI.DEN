# Context resume (Continue, Claw, MCP)

Long agent runs hit the prompt budget (`AIDEN_MAX_PROMPT_TOKENS`). AI.DEN compacts in place instead of forcing a blank restart.

## In the same chat thread

1. **Tool shrink** — old tool outputs truncated.
2. **LLM summary** — middle history replaced with `[AIDEN-SESSION-SUMMARY:summary]`.
3. **Aggressive summary** — shorter summary + fewer recent turns kept.
4. **Emergency strip** — hard cap on message sizes.

**Checklist anchor:** Use `- [ ]` / `- [x]` task lists. MCP injects `[AIDEN-CHECKLIST-ANCHOR]` with **CURRENT (resume here)** so the model continues the right step after compaction.

Response headers (router / MCP chat): `X-AIDEN-Context-Truncated`, `X-AIDEN-Context-Tier`.

## Switching UI (Continue ↔ Claw) or new thread

When MCP runs an LLM summary compaction, it also writes:

```text
<workspace>/.aiden/last-session-summary.md
```

- **Continue / MCP:** `get_session_summary` (no args) at the start of a new thread — or `read_file` on that path.
- **Claw:** `claw-system.txt` instructs the model to call `get_session_summary` or read the file when present.
- **Disable disk write:** `OLLAMA_MCP_PERSIST_SUMMARY=0` on `mcp-server`, then recreate the container.

The file is gitignored (`.aiden/`). Regenerate shared rules with `.\scripts\sync-continue-config.ps1` (updates `CLAUDE.md`).

## Related

- [hardware-tuning.md](hardware-tuning.md) — token budgets on 4GB VRAM
- [claw-with-continue.md](claw-with-continue.md) — two UIs, one stack
- [tool-policy.md](tool-policy.md) — MCP tools vs Claw builtins
