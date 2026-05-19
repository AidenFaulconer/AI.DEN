# AI.DEN — Local AI Cluster

A self-hosted private AI cluster on your laptop via Docker, with a **`model-router`** that injects a configurable **`prompt-pipeline`** (optional **claw-stage** prose + **[Caveman](https://github.com/JuliusBrussee/caveman)**) on routed LLM calls. Models default from `.env`; `caveman/` in this folder is an optional clone for reference/skills (`git clone …/caveman.git`).

| Port | Service | Model |
|------|---------|-------|
| `8765` | Coder API + pipeline (`CODER_PORT`) | `CODER_MODEL` (default **`qwen2.5-coder:7b`**) |
| `8766` | General + pipeline (`LLAMA_PORT`) | `LLAMA_MODEL` (default **`llama3.1:8b`**) |
| `8767` | Vision + pipeline (`VISION_PORT`) | `VISION_MODEL` (default **`gemma4`**) |
| `8080` | Open WebUI (`WEBUI_PORT`) | All models (browser UI → `model-router:11434` inside Docker stack) |
| `11434` | Ollama-compatible API + pipeline | Host entry point (`OLLAMA_PORT` / `CODER`-style gateway; routed through **`model-router`**, not Docker-internal Ollama) |
| `8081` | llama.cpp MTP (optional) | `LLAMACPP_PORT` — direct OpenAI API when `COMPOSE_PROFILES=mtp` |
| `8642` | Hermes Agent gateway (optional) | `HERMES_GATEWAY_PORT` — when `COMPOSE_PROFILES=hermes` |

**Browsers (Chrome / Chromium):** Ports in **`kRestrictedPorts`** (e.g. **6665–6669**) return **`ERR_UNSAFE_PORT`** for navigations — see Chromium `net/base/port_util.cc`. Defaults **8765 / 8766 / 8767** avoid those and other common clashes. **`start-aiden`** prints the exact **`/_aiden/*`** URLs (do not guess **16666** — use **`CODER_PORT`** from **`.env`** / READY banner). After changing ports, recreate **`model-router`**: **`docker compose up -d --force-recreate model-router`**.

Ports and model IDs are **`CODER_PORT`**, **`CODER_MODEL`**, etc. from **`.env`**. **`start-aiden.bat`** and **`launch-claw.bat`** read `.env`; the READY banner reflects your live host ports and models.

## Prerequisites

- [Docker Desktop](https://www.docker.com/products/docker-desktop/) with WSL2 backend
- Enough RAM for your chosen models plus Docker overhead (~16–25 GB RAM typical for defaults)
- Enough disk space for model weights (~25–40 GB typical for defaults)

## Quick Start

### 1. Start the cluster

Double-click **`start-aiden.bat`** / **`start-app.bat`** or run either from a terminal. The window stays open while AI.DEN runs — closing the window or pressing Ctrl+C automatically shuts down all containers.

```
start-aiden.bat          Start (GPU by default where available)
start-app.bat            Same launcher (alias)
start-aiden.bat cpu      Force CPU-only (no GPU reservations)
start-aiden.bat stop     Shut down all containers
start-aiden.bat status   Show container health + models
start-aiden.bat logs     Tail live logs
start-aiden.bat pull     Download / update models
start-aiden.bat help     Show all commands
```

### 2. Pull models (first time only)

Open a second terminal:

```
start-aiden.bat pull
```

### 3. Open the Web UI

Navigate to **http://localhost:8080** (or your **`WEBUI_PORT`**) and start chatting. Open WebUI is configured with `OLLAMA_BASE_URL=http://model-router:11434`, so chats use the **same routed prompt pipeline** as the host APIs.

---

## Caveman / prompt pipeline (router-injected stages)

Upstream Caveman semantics: **[JuliusBrussee/caveman](https://github.com/JuliusBrussee/caveman)** (“why use many token when few do trick”).

This stack injects configurable **prompt pipeline stages** on every routed request (same paths as before: **`/v1/chat/completions`**, **`/api/chat`**, **`/v1/completions`**, **`/api/generate`**):

| Stage (`stages[]` token) | Source file | Typical role |
|--------------------------|-------------|---------------|
| `claw` | `proxy/claw-system.txt` (override on disk) | First-stage harness: agent-like, precise, verbose OK |
| `caveman` | `proxy/caveman-system.txt` | Late-stage terse “dumb it down”: fewer fluff tokens |

**Order matters**: `["claw","caveman"]` concatenates claw first, Caveman second (recommended). Use `["caveman"]` for legacy terse-only behaviour, `["claw"]` without Caveman if you drop the blunt instrument, or `"stages":[]` to disable injections entirely until you change config again.

**Where it applies:** Ports **`OLLAMA_PORT`**, **`CODER_PORT`**, **`LLAMA_PORT`**, **`VISION_PORT`** (defaults **11434, 8765, 8766, 8767**; anything through `model-router`).

### Configure the pipeline

1. **`proxy/prompt-pipeline.json`** (tracked default; rewritten by POST) — JSON `{"stages":["claw","caveman"]}`.
2. **`PROMPT_PIPELINE`** in **`.env`** — comma-separated fallback when the JSON file is missing or malformed (e.g. `PROMPT_PIPELINE=caveman` or `claw` or empty list via JSON only).
3. **HTTP API** on any router listener (examples use **`CODER_PORT`**, usually **8765**):

   ```bash
   curl -s http://localhost:8765/_aiden/pipeline
   ```

   Swap **`8765`** for your **`CODER_PORT`** if you moved it.

   ```powershell
   # Use your `CODER_PORT` if not 8765 (see READY banner or `.env`).
   Invoke-RestMethod -Method POST -Uri http://localhost:8765/_aiden/pipeline `
     -ContentType application/json `
     -Body '{"stages":["caveman"]}'
   ```

   If **`AIDEN_ADMIN_TOKEN`** is set in `.env`, POST must send header **`Authorization: Bearer <same token>`**.

**Idempotency:** Combined injection ends with **`[AIDEN-PIPE:v1]`**; router skips re-injection if any `system` message already contains **`[AIDEN-CAVEMAN]`** or **`[AIDEN-PIPE:v1]`**.

### OpenAPI & Swagger UI

Canonical spec (**repository copy**): [`proxy/router-openapi.yaml`](proxy/router-openapi.yaml). Served live from **`model-router`** on every listener:

| Purpose | URL (any router port works) |
|--------|------------------------------|
| **Swagger UI** (browser) | `http://localhost:<CODER_PORT>/_aiden/swagger` ([default **8765**](http://localhost:8765/_aiden/swagger)) |
| **OpenAPI YAML** (tooling / import) | `http://localhost:<CODER_PORT>/_aiden/openapi.yaml` ([default](http://localhost:8765/_aiden/openapi.yaml)) |

---

### Editing stage text on disk

- **Claw stage:** Edit `proxy/claw-system.txt` and restart **`model-router`** (`docker compose up -d model-router`).
- **Caveman stage:** Edit `proxy/caveman-system.txt` similarly.

### Startup + Claw window

Starting via **`start-aiden.bat`** / **`start-app.bat`** opens an extra **`AIDEN — Claw`** terminal once services are READY (wired to **`launch-claw.bat`**). Set **`AUTO_LAUNCH_CLAW=false`** (or **`0`** / **`off`**) in `.env` to disable.

---

## Hermes Agent + llama.cpp MTP (optional)

[Nous Hermes Agent](https://hermes-agent.nousresearch.com/) runs as an autonomous gateway; **llama.cpp** inference uses speculative decoding when enabled.

**Speculative decoding** (MTP, separate draft model, n-gram): see **[docs/speculative-decoding.md](docs/speculative-decoding.md)**. Default on your laptop: **`LLAMACPP_SPEC_MODE=mtp`** (single Qwen3.6-MTP GGUF). For **3–4B draft + 27B/70B target**, set `LLAMACPP_SPEC_MODE=draft` (70B needs a high-RAM/VRAM machine).

Default MTP build: [havenoammo/llama](https://huggingface.co/havenoammo/Qwen3.6-27B-MTP-UD-GGUF) with `--spec-type draft-mtp`.

### Quick start

1. Download an MTP GGUF into **`models/`** (see **`models/README.md`**).
2. In **`.env`** enable:
   ```env
   COMPOSE_PROFILES=mtp,hermes
   LLAMA_BACKEND=llamacpp
   LLAMACPP_GGUF=Qwen3.6-27B-MTP-UD-Q4_K_XL.gguf
   ```
3. Start: **`start-aiden.bat mtp`** (or `docker compose -f docker-compose.yml -f docker-compose.hermes-mtp.yml up -d`).

| Endpoint | Role |
|----------|------|
| `http://localhost:8766/v1` | LLAMA port → **llamacpp** when `LLAMA_BACKEND=llamacpp` (pipeline still applied) |
| `http://localhost:8081/v1` | Direct llama-server (no router) |
| `http://localhost:8642` | Hermes gateway + OpenAI-compatible API (`HERMES_API_SERVER_KEY` in `.env`) |

Hermes inference URL is configured in **`hermes-data/config.yaml`** (default: `http://model-router:8766/v1`). Run setup once if needed:

```powershell
docker run -it --rm -v "${PWD}/hermes-data:/opt/data" nousresearch/hermes-agent:latest setup
```

---

### Original Caveman integration details

Integration specifics (still accurate beyond the claw stage):

- **Where:** OpenResty `model-router` prepends or merges a system block per stage on every routed request listed above across **`OLLAMA_PORT`**, **`CODER_PORT`**, **`LLAMA_PORT`**, **`VISION_PORT`** (defaults **11434, 8765, 8766, 8767**).
- **Text:** `caveman` stage mounts from **`proxy/caveman-system.txt`** (fallback distilled text is embedded in `nginx.conf` if missing). Matches Caveman terse intent; override with **`"stop caveman"`** / **`"normal mode"`** per upstream semantics ([README](https://github.com/JuliusBrussee/caveman)).
- **IDE / Cursor:** Point OpenAI Base URL at `http://localhost:8765/v1`, etc.; the full pipeline applies the same way.

---

## API Usage

All endpoints are **OpenAI API compatible** (`/v1/chat/completions`, `/v1/completions`, etc.).

### Port-based routing (model auto-selected)

The **`CODER_PORT`** and **`LLAMA_PORT`** listeners inject the default model if none is specified in your request:

```bash
# Coding query → default coder model from .env (`CODER_PORT`, default host 8765)
curl http://localhost:8765/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "messages": [{"role": "user", "content": "Write a Python quicksort"}],
    "stream": true
  }'

# General query → default general model from .env (`LLAMA_PORT`, default host 8766)
curl http://localhost:8766/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "messages": [{"role": "user", "content": "Explain quantum entanglement"}],
    "stream": true
  }'
```

You can still override the model explicitly on any port:

```bash
# Force llama on the coder port — this works fine
curl http://localhost:8765/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "llama3.1:8b",
    "messages": [{"role": "user", "content": "Hello"}]
  }'
```

### Unified Ollama / OpenAI API on port 11434 (router + pipeline)

Traffic on **11434 goes through `model-router`**, not straight to Ollama, so the **prompt pipeline** applies the same way as on **8765** / **8766** / **8767**.

```bash
curl http://localhost:11434/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "qwen2.5-coder:7b",
    "messages": [{"role": "user", "content": "Hello"}]
  }'
```

### Ollama native API (non-OpenAI)

```bash
curl http://localhost:11434/api/chat \
  -d '{"model": "qwen2.5-coder:7b", "messages": [{"role": "user", "content": "Hi"}]}'
```

---

## Git repository

AI.DEN is a **single monorepo** (one `.git` at the root). Vendored projects no longer keep their own `.git` folders — see **`UPSTREAM.md`** for origins and pinned commits.

```powershell
copy .env.example .env   # required — .env is not committed (secrets)
git status
```

Details: **`docs/GIT.md`**. If you re-clone a subproject inside the tree, run **`scripts/remove-nested-git.ps1`**.

---

## Cursor IDE Integration

Use your local AI cluster as the backend for Cursor's AI features.

### Option A: Override OpenAI Base URL (recommended for coding)

1. Open **Cursor Settings** (not VS Code settings) → **Models**
2. Scroll to **OpenAI API Key** and enter any non-empty string, e.g. `ollama`
3. Check **Override OpenAI Base URL** and set it to:
   - `http://localhost:8765/v1` — routed pipeline + default coder model from `.env`
   - `http://localhost:8766/v1` — routed pipeline + default general model
   - `http://localhost:8767/v1` — routed pipeline + default vision model
   - `http://localhost:11434/v1` — routed pipeline + you pick model in payload
4. Under **Model Names**, add the names matching your `.env` (for example `qwen2.5-coder:7b`, `llama3.1:8b`, `gemma4`)
5. Select one of these models from the model dropdown when chatting

### Option B: Add as OpenAI-compatible provider

In your `~/.cursor/config/settings.json` or via the GUI:

```json
{
  "cursor.ai.openai.apiBase": "http://localhost:8765/v1",
  "cursor.ai.openai.apiKey": "ollama"
}
```

### Tips for Cursor

- Use **`CODER_PORT`** (default **8765**) for coding tasks (Qwen 2.5 Coder is optimized for code)
- Use **`LLAMA_PORT`** (default **8766**) for general reasoning / architecture discussions
- If responses feel slow, check that only one model is loaded (`MAX_LOADED_MODELS=1`)
- For faster Cursor responses, set `OLLAMA_KEEP_ALIVE=24h` in `.env` to keep the model warm

---

## VS Code Continue extension

Continue uses the same **OpenAI-compatible** router as Cursor, with optional **MCP** for tools.

### One-time setup

1. Start the stack: `start-aiden.bat`
2. Sync config from `.env` into your user profile:

```powershell
.\scripts\sync-continue-config.ps1
```

This writes `%USERPROFILE%\.continue\config.yaml` (on your machine: `C:\Users\aidenleefaulconer\.continue\config.yaml`).

3. In VS Code, install the **Continue** extension and reload the window.
4. In Continue, pick **AI.DEN Coder (Qwen3.6 + pipeline)** as the chat model.

### What is configured

| Continue model | API base | Notes |
|----------------|----------|--------|
| **AI.DEN Coder** | `http://localhost:8765/v1` | claw + caveman pipeline, `CODER_MODEL` |
| **AI.DEN General** | `http://localhost:8766/v1` | same pipeline, `LLAMA_MODEL` |
| **MCP** | `http://localhost:5000/mcp` | streamable-http — `list_models`, file tools, etc. |

- **`apiKey`**: `ollama` (any non-empty string; router does not validate)
- **`model`**: must match `GET http://localhost:8765/v1/models` (GGUF filename for llama.cpp)
- **Autocomplete** is **disabled** by default (27B is too slow for tab completion); set `autocompleteOptions.disable: false` in config if you want it anyway
- **embed / rerank** are not configured — this stack does not expose a local embedding model on the coder port

### After changing `.env`

Re-run `.\scripts\sync-continue-config.ps1` and reload Continue.

Template lives in-repo: `continue/config.yaml` and `continue/rules.md`.

---

## Claw Code CLI (terminal agent)

[Claw Code](https://github.com/ultraworkers/claw-code) is an open-source Rust CLI agent harness. AI.DEN integrates it via **`launch-claw.bat`**, which points Claw at this stack’s **OpenAI-compatible** proxies (same routed **prompt pipeline** as Cursor): `OPENAI_BASE_URL=http://127.0.0.1:<port>/v1` with **no** API key, matching upstream [USAGE.md](https://github.com/ultraworkers/claw-code/blob/main/USAGE.md) Ollama-style setup.

### One-time setup

**Option A — Docker (recommended if you skip local Rust):** from the AI.DEN repo root, build the image once (first build is slow):

```powershell
docker compose --profile claw build openclaw
```

**`launch-claw.bat`** then runs **`aiden-openclaw:local`** when `claw.exe` is missing, with `OPENAI_BASE_URL=http://host.docker.internal:<port>/v1` so the container can reach the proxies on the host.

**Option B — Native build:**

```powershell
cd AI.DEN
git clone https://github.com/ultraworkers/claw-code.git
cd claw-code\rust
cargo build --workspace --release
.\target\release\claw.exe doctor
```

Ports and model names follow **`.env`** (`CODER_*`, `LLAMA_*`, `VISION_*`, `OLLAMA_PORT`). Default profile is **coder** → **`CODER_PORT`** (**8765**) + **`CODER_MODEL`**.

**`--model` syntax:** Claw expects `provider/model` (or **`opus`** / **`sonnet`** / **`haiku`**). **`launch-claw.bat`** prefixes Ollama IDs with **`openai/`** (e.g. **`openai/qwen2.5-coder:7b`**); that prefix is stripped on the wire so the router still sees **`qwen2.5-coder:7b`**.

### Run (after `start-aiden.bat`)

```powershell
launch-claw.bat help
launch-claw.bat prompt "say hello"
launch-claw.bat general prompt "summarize README.md"
launch-claw.bat vision prompt "describe this image"   # when your workflow uses vision
```

Optional: set `CLAW_BIN` to a full path to `claw.exe` to force the native binary instead of Docker.

---

## Concurrency Control

Edit `.env` to control whether both models can be loaded simultaneously:

```env
# Only one model in memory at a time (saves RAM, swaps on demand)
MAX_LOADED_MODELS=1

# Both models loaded simultaneously (needs more RAM / VRAM headroom)
MAX_LOADED_MODELS=2
```

After changing, restart the cluster:

```powershell
docker compose down && docker compose up -d
```

### How it works

- With `MAX_LOADED_MODELS=1`: switching models unloads the previous one (short delay).
- With `MAX_LOADED_MODELS=2`: faster switching where RAM / VRAM allows.

---

## GPU Acceleration

GPU device reservations ship in **default `docker-compose.yml`**. Verify with `docker run --rm --gpus all nvidia/cuda:12.6.0-base-ubuntu24.04 nvidia-smi`.

If GPUs are unavailable, use **`start-aiden.bat cpu`** (uses `docker-compose.cpu.yml`). Optional override file `docker-compose.gpu.yml` is legacy / redundant.

### Windows Setup (first-time)

If you have an NVIDIA GPU:

1. Install the latest [NVIDIA drivers](https://www.nvidia.com/download/index.aspx)
2. Ensure Docker Desktop uses the **WSL2 backend** (Settings → General)
3. In WSL2, install the NVIDIA Container Toolkit:

```bash
# Inside WSL2 terminal
curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey \
  | sudo gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg
curl -s -L https://nvidia.github.io/libnvidia-container/stable/deb/nvidia-container-toolkit.list \
  | sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' \
  | sudo tee /etc/apt/sources.list.d/nvidia-container-toolkit.list
sudo apt-get update && sudo apt-get install -y nvidia-container-toolkit
sudo nvidia-ctk runtime configure --runtime=docker
```

4. Restart Docker Desktop, then **`docker compose up -d`** (or `start-aiden.bat`)

---

## Management Commands

```powershell
# Start the cluster
docker compose up -d

# Stop the cluster
docker compose down

# View logs
docker compose logs -f

# View Ollama logs only
docker compose logs -f ollama

# Check which models are loaded
docker exec ollama ollama ps

# List downloaded models
docker exec ollama ollama list

# Pull a new model
docker exec ollama ollama pull <model-name>

# Remove a model
docker exec ollama ollama rm <model-name>

# Restart after .env changes
docker compose down && docker compose up -d

# Full reset (removes all data including models)
docker compose down -v
```

---

## Routing for Other Apps

Any app that supports the **OpenAI API** can point at your local cluster:

| Setting | Value |
|---------|-------|
| API Base URL | `http://localhost:8765/v1`, `8766/v1`, `8767/v1`, … (each runs the routed pipeline when enabled; match your **`CODER_PORT`** / **`LLAMA_PORT`** / **`VISION_PORT`** if changed) |
| API Key | Any non-empty string (e.g. `ollama`, `sk-local`, `unused`) |
| Model | Match names in `.env` (coder / llama / vision) |

Compatible apps include: Cursor, Continue, VS Code + CodeGPT, Tabby, LibreChat, TypingMind, BoltAI, Chatbox, and any OpenAI SDK client.

### Python SDK example

```python
from openai import OpenAI

client = OpenAI(
    base_url="http://localhost:8765/v1",
    api_key="ollama",
)

response = client.chat.completions.create(
    model="qwen2.5-coder:7b",
    messages=[{"role": "user", "content": "Write a Python fibonacci generator"}],
)
print(response.choices[0].message.content)
```

---

## Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│ Host 8765 / 8766 / 8767 / 11434  →  model-router (OpenResty + pipeline)
└─────────────────────────────┬────────────────────────────────────┘
                              ▼
  Open WebUI (8080)  →  OLLAMA_BASE_URL=http://model-router:11434
                              │
                              ▼
                         ollama:11434  (Docker-internal only — not on host)

`localhost:11434` exposes the pipeline-aware proxy only — not bare Ollama.
```

To hit **raw Ollama** without the router/pipeline for debugging:

```powershell
docker exec -it ollama ollama run llama3.1:8b
```

## Troubleshooting

### "Model not found" error
Run `docker exec ollama ollama pull <model-name>` to download the model first.

### Slow responses
- Check `docker exec ollama ollama ps` to see if the model is loaded
- Set `OLLAMA_KEEP_ALIVE=24h` in `.env` to prevent unloading
- If running CPU-only (`start-aiden.bat cpu`), throughput depends on CPU and model size; keep GPU enabled when possible (`docker-compose.yml`).

### Out of memory
- Set `MAX_LOADED_MODELS=1`
- Reduce `OLLAMA_MAX_VRAM` or model size / quantization

### Connection refused on `CODER_PORT` / `LLAMA_PORT` / `VISION_PORT` (defaults **8765 / 8766 / 8767**)
- **Wrong URL:** The pipeline runs on **`CODER_PORT`**, not an arbitrary port (e.g. **16666** is invalid unless you explicitly set **`CODER_PORT=16666`** and recreated **`model-router`**).
- **`docker compose ps`** — **`model-router`** should publish **`8765->8765/tcp`** (etc.) matching **`.env`**. Old containers may still bind previous ports until recreated.
- **Recreate after port changes:** `docker compose up -d --force-recreate model-router`
- Check logs: `docker compose logs model-router`

### Open WebUI can't find Ollama
- `docker compose ps` — **`model-router` and `open-webui` healthy**
- The WebUI uses `OLLAMA_BASE_URL=http://model-router:11434` inside Docker (same pipeline path as localhost:11434)
