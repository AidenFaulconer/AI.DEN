# GGUF models for llama.cpp

The **llamacpp** service loads models from this folder. Speculative decoding mode is set in `.env` as `LLAMACPP_SPEC_MODE` (see **`docs/speculative-decoding.md`**).

## Mode: MTP (default — one file)

Multi-Token Prediction (MTP) GGUF — built-in draft heads, best fit for **64 GB RAM / 4 GB VRAM** laptops.

## Recommended (havenoammo + Unsloth UD)

Download from [havenoammo/Qwen3.6-27B-MTP-UD-GGUF](https://huggingface.co/havenoammo/Qwen3.6-27B-MTP-UD-GGUF) (pick a quant that fits your VRAM).

Example (adjust filename to match `.env` `LLAMACPP_GGUF`):

```powershell
# Requires huggingface-cli: pip install huggingface_hub
huggingface-cli download havenoammo/Qwen3.6-27B-MTP-UD-GGUF Qwen3.6-27B-MTP-UD-Q4_K_XL.gguf --local-dir .
```

On **4 GB VRAM** (e.g. RTX 3050 laptop), prefer **Q4_K_XL** or smaller and lower `LLAMACPP_CTX_SIZE` in `.env`.

## Enable in AI.DEN

1. Place the `.gguf` file here.
2. In `.env` set:
   - `COMPOSE_PROFILES=mtp,hermes` (optional `hermes` for the agent gateway)
   - `LLAMA_BACKEND=llamacpp`
   - `LLAMACPP_GGUF=YourFile.gguf`
   - `LLAMA_MODEL` to the served model id (check `http://localhost:8081/v1/models` after start)
3. `docker compose up -d` or `start-aiden.bat`

Direct llama.cpp API (no pipeline): `http://localhost:8081/v1` (`LLAMACPP_PORT`).

## Mode: draft (target + small draft model)

For **27B + 4B** or **70B + 4B** (when hardware allows):

1. `.\scripts\download-spec-draft.ps1`
2. Set in `.env`: `LLAMACPP_SPEC_MODE=draft`, `LLAMACPP_DRAFT_GGUF=...`
3. Use a **non-MTP** target GGUF for the large model (MTP + external draft is redundant)
4. `docker compose up -d --force-recreate llamacpp`
