# Hardware tuning (AI.DEN)

Profiles for **Qwen3.6-27B-MTP** via `llamacpp` + **model-router** + **MCP**.

## Your machine (auto-detected baseline)

| Resource | Value |
|----------|--------|
| GPU | NVIDIA GeForce RTX 3050 Ti Laptop (4 GB VRAM) |
| RAM | ~64 GB |
| CPU | 14 cores / 20 threads |

**Do not** apply 12 GB VRAM guides verbatim (`ctx 131072`, `--fit 1536` only) — they will OOM on 4 GB.

## What is already optimal

| Setting | Value | Why |
|---------|--------|-----|
| `LLAMACPP_SPEC_MODE` | `mtp` | Built-in MTP heads in your GGUF |
| `LLAMACPP_SPEC_DRAFT_N_MAX` | `3` | Best speed/acceptance for dense 27B |
| `LLAMACPP_CACHE_K/V` | `q8_0` | Smaller KV → longer ctx on limited VRAM |
| `-np 1` | (entrypoint) | MTP requires single parallel slot |
| `LLAMACPP_GGUF` | `*-MTP-*.gguf` | Non-MTP files cannot use MTP |

## 4 GB VRAM profile (current `.env`)

```env
LLAMACPP_FIT_TARGET=512
LLAMACPP_CTX_SIZE=16384
LLAMACPP_THREADS=14
PROMPT_PIPELINE=caveman
OLLAMA_MCP_MAX_TOKENS=1536
```

- **`LLAMACPP_FIT_TARGET=512`** — leaves headroom for Windows, display, and MTP draft KV (vs `1536` on 12 GB cards).
- **`PROMPT_PIPELINE=caveman`** — drops the extra claw system block (~1–2k tokens). Use `claw,caveman` for hard multi-file agent tasks.
- **MCP `temperature=0.15`** — overrides server defaults for tool calls (accuracy over creativity).

## 12 GB+ VRAM profile (e.g. RTX 4070 Super)

```env
LLAMACPP_FIT_TARGET=1536
LLAMACPP_CTX_SIZE=32768
LLAMACPP_TEMP=0.6
PROMPT_PIPELINE=claw,caveman
OLLAMA_MCP_MAX_TOKENS=2048
```

Higher context is safe; online guides citing ~80 tok/s assume this tier.

## Sampling (Qwen3.6 recommendations)

| Layer | temp | top_p | top_k | min_p | repeat |
|--------|------|-------|-------|-------|--------|
| **llama-server** (chat/UI) | 0.45–0.6 | 0.95 | 20 | 0.0 | 1.0 |
| **MCP / tools** | 0.15 | 0.9 | 20 | 0.0 | 1.0 |

Coding agents should stay **low temperature**; raise `LLAMACPP_TEMP` only for open-ended chat in WebUI.

## Token waste controls

| Variable | Role |
|----------|------|
| `AIDEN_MAX_PROMPT_TOKENS` | Hard cap on prompt size (7680 on 4GB) — avoids 9k+ full reprocess |
| `AIDEN_CTX_RESERVE` | Tokens left for model reply (5120) |
| `AIDEN_MAX_MSG_CHARS` | Per-message cap before router trim (6000) |
| `AIDEN_TOOL_RESULT_MAX_CHARS` | Old tool output compression |
| `LLAMACPP_UBATCH_SIZE` | Physical batch for prompt eval (256 on 4GB) |
| `OLLAMA_MCP_COMPACT_THRESHOLD` | Summarize history earlier (0.72) |
| `OLLAMA_MCP_PRESERVE_RECENT` | Turns kept verbatim (3) |
| `OLLAMA_MCP_MAX_TOKENS` | Cap completion length per MCP step |

Watch response headers: `X-AIDEN-Prompt-Tokens-Est` (every request), `X-AIDEN-Context-Truncated`, `X-AIDEN-Context-Tier` (router).

## Caveman vs context compression

| Use | What caveman does here | Effective? |
|-----|------------------------|------------|
| **Every chat** (`PROMPT_PIPELINE=caveman`) | Router injects `proxy/caveman-system.txt` → model replies **terser** (fewer **output** tokens) | Yes for completions |
| **Cost** | That system block adds ~1–2k **input** tokens per request | Tradeoff on 4GB |
| **Context compaction** | Separate ladder (tool shrink → LLM summary → emergency) | Yes for long agent runs |
| **Session summaries** | Tier 1/2 summaries now ask for **caveman-style** text when `PROMPT_PIPELINE` includes `caveman` | Yes — denser rollups |

Caveman is **not** the same as `caveman-compress/` in the repo (that skill targets Anthropic API for file compression). Local stack uses **style instructions**, not that script.

`claw,caveman` adds claw planning block + caveman — more input tokens, use only for hard multi-file tasks.

## Context overflow failover (automatic)

| Tier | MCP / agent_chat | model-router (Continue chat) |
|------|------------------|----------------------------|
| 0 | Compress old tool outputs; drop middle turns | Same + per-message shrink |
| 1 | LLM **summary** (~400 words) + keep recent turns | Drop oldest turns |
| 2 | **Shorter** summary (~120 words) + fewer preserved tools | Tighter tool/msg caps |
| 3 | **Emergency**: system + last 3 turns + re-read hint | Emergency strip |

Proactive at **72%** of prompt budget (`OLLAMA_MCP_COMPACT_THRESHOLD`). On llama **overflow**, tiers escalate (up to 3 retries). Tune via `OLLAMA_MCP_COMPACT_MAX_TIERS`, `OLLAMA_MCP_SUMMARY_WORDS*`.

### Slow logs (`prompt eval` 180s+, `tg` ~1.1 t/s)

Usually **~9500 prompt tokens** from Continue (`@repo-map`, long history). Router now trims harder; Continue config uses **8192** context and **repo-map off**. If llama.cpp logs `forcing full prompt re-processing`, the next turn did not match the cached 9k prompt — keep prompts under ~7k tokens.

## Vision

Do **not** use MTP for image inputs (known crashes). Use a separate vision model/backend without `--spec-type draft-mtp`.

## Apply changes

```powershell
docker compose up -d --force-recreate llamacpp model-router mcp-server
```

Or: `start-aiden.bat stop` then `start-aiden.bat`.
