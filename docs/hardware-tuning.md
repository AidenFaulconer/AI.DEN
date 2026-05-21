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
| `AIDEN_CTX_RESERVE` | Tokens left for model reply (4096) |
| `AIDEN_MAX_MSG_CHARS` | Per-message cap before router trim |
| `AIDEN_TOOL_RESULT_MAX_CHARS` | Old tool output compression |
| `OLLAMA_MCP_COMPACT_THRESHOLD` | Summarize history earlier (0.78) |
| `OLLAMA_MCP_PRESERVE_RECENT` | Turns kept verbatim (4) |
| `OLLAMA_MCP_MAX_TOKENS` | Cap completion length per MCP step |

Watch response headers: `X-AIDEN-Context-Truncated`, `X-AIDEN-Prompt-Tokens-Est`.

## Vision

Do **not** use MTP for image inputs (known crashes). Use a separate vision model/backend without `--spec-type draft-mtp`.

## Apply changes

```powershell
docker compose up -d --force-recreate llamacpp model-router mcp-server
```

Or: `start-aiden.bat stop` then `start-aiden.bat`.
