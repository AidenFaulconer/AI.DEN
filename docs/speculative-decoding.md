# Speculative decoding in AI.DEN

AI.DEN uses **llama.cpp** speculative decoding to generate multiple candidate tokens cheaply, then verify them in one batch on the **target** model. That raises throughput when drafts are often accepted.

## Modes (`LLAMACPP_SPEC_MODE` in `.env`)

| Mode | What it does | Hardware | Files |
|------|----------------|----------|--------|
| **`mtp`** (default) | MTP heads inside **Qwen3.6-27B-MTP-UD-*.gguf** | 64 GB RAM, 4 GB VRAM (your laptop) | One MTP GGUF |
| **`draft`** | Separate **3–4B draft** + **27B/70B target** | 64 GB+ RAM; 24 GB+ VRAM for 70B+4B | `LLAMACPP_GGUF` + `LLAMACPP_DRAFT_GGUF` |
| **`draft+ngram`** | Draft model + **ngram-simple** (good for code edits) | Same as draft | Two GGUFs |
| **`ngram`** | No extra model; pattern cache only | Low extra RAM | One GGUF |
| **`none`** | Disabled | Any | One GGUF |

Configured via `scripts/llamacpp-entrypoint.sh` (mounted into the `llamacpp` container).

## Your machine vs “70B + 4B”

| Tier | Example stack | Realistic? |
|------|-----------------|------------|
| **Current (recommended)** | `mtp` + Qwen3.6-27B-MTP Q4 | Yes — already active |
| **Upgrade (same RAM)** | `draft` + 27B Q4 + Qwen3-4B Q4 | Maybe — ~20–28 GB RAM; tight on 4 GB VRAM |
| **Workstation** | `draft` + 70B Q4 + 4B Q4 | Needs **~48 GB+ RAM** and **24 GB+ VRAM** (or heavy CPU offload) |

A **70B reasoning model** does not fit a **4 GB GPU** laptop; use **27B** as target or add a machine with more VRAM.

## Enable separate draft model (27B + 4B)

1. Download a small Qwen3-family draft GGUF into `models/`:

```powershell
.\scripts\download-spec-draft.ps1
```

2. In `.env`:

```env
LLAMACPP_SPEC_MODE=draft
LLAMACPP_GGUF=Qwen3.6-27B-MTP-UD-Q4_K_XL.gguf
# Or a non-MTP 27B instruct GGUF as target:
# LLAMACPP_GGUF=Qwen3-30B-A3B-Instruct-Q4_K_M.gguf
LLAMACPP_DRAFT_GGUF=Qwen3-4B-Instruct-2507-Q4_K_M.gguf
LLAMACPP_SPEC_DRAFT_N_MAX=16
LLAMACPP_DRAFT_NGL=-1
CODER_MODEL=Qwen3.6-27B-MTP-UD-Q4_K_XL.gguf
```

Use a **non-MTP** target when using `draft` mode (MTP + external draft is redundant). For coding, a plain **27B Instruct** + **4B** draft is the usual pair.

3. Recreate inference:

```powershell
docker compose up -d --force-recreate llamacpp
```

4. Watch acceptance in logs:

```powershell
docker logs llamacpp 2>&1 | Select-String "draft acceptance"
```

## High-end profile (70B + 4B) — example only

```env
LLAMACPP_SPEC_MODE=draft
LLAMACPP_GGUF=Meta-Llama-3.1-70B-Instruct-Q4_K_M.gguf
LLAMACPP_DRAFT_GGUF=Qwen3-4B-Instruct-2507-Q4_K_M.gguf
LLAMACPP_CTX_SIZE=8192
LLAMACPP_SPEC_DRAFT_N_MAX=16
AIDEN_LLM_MEM_LIMIT=80g
```

Draft and target should share a **compatible tokenizer** (same model family). Qwen draft + Qwen/Llama target may need `--spec-draft-replace` (see llama.cpp docs) — prefer **Qwen target + Qwen draft**.

## Tuning

| Variable | Default | Notes |
|----------|---------|--------|
| `LLAMACPP_SPEC_DRAFT_N_MAX` | `3` (mtp) / `16` (draft) | Max draft tokens per step; **keep 3 for Qwen3.6-27B MTP** |
| `LLAMACPP_FIT_TARGET` | `512` (4GB) / `1536` (12GB) | VRAM margin for `--fit` (MiB) |
| `LLAMACPP_CACHE_K/V` | `q8_0` | KV cache quant |
| `LLAMACPP_TEMP/TOP_P/TOP_K` | see `.env` | Server-wide sampling defaults |
| `LLAMACPP_DRAFT_NGL` | `-1` | GPU layers for draft model |
| `LLAMACPP_NGRAM_SIZE_N` | `12` | ngram lookup length |
| `LLAMACPP_NGRAM_SIZE_M` | `48` | ngram draft length |

Higher `SPEC_DRAFT_N_MAX` → more speed when acceptance is high, more waste when low.

**Hardware profiles:** [hardware-tuning.md](hardware-tuning.md)

## Router / Cursor

No router changes: clients still use `http://localhost:8765/v1`. Only `llamacpp` loading changes.
