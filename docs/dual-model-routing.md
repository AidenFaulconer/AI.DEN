# Dual MTP models (fast + quality)

AI.DEN can run **two** llama.cpp MTP servers and let **model-router** pick the right one per request.

| Tier | Default model | Container | When used |
|------|---------------|-----------|-----------|
| **quality** | `CODER_MODEL` (Qwen3.6-27B-MTP) | `llamacpp` | Agent tools, long context, “critical” keywords, explicit model name |
| **fast** | `CODER_FAST_MODEL` (Qwen3.5-9B-MTP) | `llamacpp-fast` | Short chat, small prompts, autocomplete-style tasks |

Same **caveman/claw pipeline**, MCP, and prompt caps apply to both.

## Setup

1. Download the fast GGUF (~6 GB):

   ```powershell
   .\scripts\download-fast-mtp.ps1
   ```

2. Enable the fast profile and restart:

   ```powershell
   $env:COMPOSE_PROFILES = "fast"
   docker compose up -d --force-recreate llamacpp-fast model-router
   ```

   Or set in `.env`: `COMPOSE_PROFILES=fast` (append `hermes` if you use Hermes).

3. Sync Continue:

   ```powershell
   .\scripts\sync-continue-config.ps1
   ```

4. Reload Continue — you will see **AI.DEN Fast** and **AI.DEN Coder (quality)**.

## Routing (`AIDEN_MODEL_ROUTING`)

| Value | Behavior |
|-------|----------|
| `auto` (default) | Router picks fast vs quality from heuristics below |
| `fast` | Always `llamacpp-fast` |
| `quality` | Always `llamacpp` (27B) |
| `off` | Same as `quality` (no fast upstream) |

Set `AIDEN_FAST_ENABLED=0` if the fast container is not running (router never calls `llamacpp-fast`).

### Auto → quality (27B) when any of:

- Messages include **tools** (`role: tool` or `tool_calls`)
- Estimated prompt **> `AIDEN_FAST_MAX_PROMPT_TOKENS`** (default 2048)
- More than **`AIDEN_FAST_MAX_MESSAGES`** turns (default 10)
- `max_tokens` **> `AIDEN_FAST_MAX_COMPLETION_TOKENS`** (default 512)
- User text matches critical keywords (refactor, security, migration, …)

### Force a tier

- Request header: `X-AIDEN-Model-Tier: fast` or `quality`
- Explicit `model` in JSON: `Qwen3.5-9B-UD-Q4_K_XL.gguf` vs `Qwen3.6-27B-MTP-UD-Q4_K_XL.gguf`

Response headers: `X-AIDEN-Model-Tier`, `X-AIDEN-Model-Selected`.

## VRAM note (RTX 3050 Ti 4GB)

Both models load in **separate** processes (~18 GB + ~6 GB RAM). GPU is shared; fast uses `LLAMACPP_FAST_FIT_TARGET=2048` so more layers stay on GPU. If you hit OOM, set `AIDEN_FAST_ENABLED=0` or stop `llamacpp-fast` and use 27B only.

## Why Qwen3.5-9B MTP?

Qwen3.6 MTP GGUFs are published for **27B** and **35B-A3B** only. **Qwen3.5-9B-MTP** is the closest smaller MTP build (same llama.cpp `--spec-type draft-mtp` stack, tool-friendly, same router design).
