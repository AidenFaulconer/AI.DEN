# Continue repo context (smart limits)

Continue does **not** expose `maxDepth` on `@repo-map`. Depth control is done by **what you attach**, **ignore files**, and **hardware-aware defaults** synced from AI.DEN `.env`.

## What each provider does

| Provider | Content | Token cost |
|----------|---------|------------|
| `@tree` | Directory tree (folders/files) | Lower — good default structure |
| `@repo-map` | File list + top-level class/function **signatures** | High with `includeSignatures: true` |
| `@code` | Specific symbols you pick | Targeted |

**`node_modules` is not fully “mapped”** when it is ignored — Continue’s indexer and repo-map respect **`.gitignore`** and **`.continueignore`**.

## Ignore heavy folders

AI.DEN ships `continue/.continueignore`. `sync-continue-config.ps1` copies it to your **workspace root** as `.continueignore` if missing.

Typical patterns already listed:

- `node_modules/`, `dist/`, `build/`, `target/`, `.venv/`, `models/`, `*.gguf`

Add project-specific paths (e.g. `generated/`).

## Hardware profiles (auto on sync)

Controlled by `LLAMACPP_FIT_TARGET` in `.env`:

| Profile | `FIT_TARGET` | `contextLength` | `@repo-map` signatures |
|---------|--------------|-----------------|------------------------|
| **4GB laptop** | ≤ 768 | `16384` (`AIDEN_CONTINUE_CONTEXT_LENGTH`, same as llama ctx) | **off** (`includeSignatures: false`) |
| **12GB+** | > 768 | from `.env` | **on** |

Override anytime:

```env
AIDEN_REPO_MAP_SIGNATURES=false
```

Then re-run `.\scripts\sync-continue-config.ps1`.

## How to limit “depth” in practice

1. **Prefer `@tree`** for “what’s in the repo?” — already enabled in `continue/config.yaml`.
2. **Use `@repo-map` on a subfolder** — in the `@` menu choose repo-map, then pick a **subfolder** (e.g. `frontend/`), not “Entire codebase”.
3. **Turn off signatures** on 4GB (`includeSignatures: false`) — saves thousands of tokens vs full API outlines.
4. **Router cap** — `AIDEN_MAX_PROMPT_TOKENS=6144` trims oversized prompts before llama.cpp (see `docs/hardware-tuning.md`).
5. **MCP fallback** — `workspace_info`, `list_dir`, `glob_files` for paths when you skip `@repo-map`.

## When repo-map was disabled

It was commented out only to stop **~9k-token** prompts on 4GB VRAM. With ignores + no signatures + subfolder selection, re-enable it via sync (default in template).

Check router header **`X-AIDEN-Prompt-Tokens-Est`** after a message; aim for **&lt; 6144** on a 3050 Ti.

## `read_file` too large (8215 vs 8192)

Continue rejects reads when the **whole file** exceeds `contextLength`. Fix:

1. **`AIDEN_CONTINUE_CONTEXT_LENGTH=16384`** in `.env` (not 8192) — then `sync-continue-config.ps1`
2. MCP **`read_file`** auto-chunks large files; use `start_line` / `end_line` for the rest
3. Or **`grep_search`** for a symbol instead of reading the whole file
