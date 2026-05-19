# Claw Code Local

**Claude Code experience. Local models. Zero API costs.**

Run a full-featured coding agent CLI against Ollama, LM Studio, or any OpenAI-compatible endpoint — entirely on your machine, with your own models.

Built on top of [claw-code-parity](https://github.com/ultraworkers/claw-code-parity), a clean-room Rust reimplementation of the Claude Code harness.

---

## What this is

Claw Code Local patches the `claw` CLI to use any LLM provider, not just Anthropic. The upstream project built a full multi-provider API layer but never wired it into the actual binary — it was hardcoded to require Anthropic credentials. We fixed that, along with a streaming render bug that caused terminal output to smash sections together.

**What you get:**
- Interactive REPL with session persistence, slash commands, markdown rendering
- Tool use: file read/write/edit, grep, glob, bash execution, git integration
- `/commit`, `/diff`, `/pr`, `/review`, `/mcp`, `/agents`, `/skills` and 130+ slash commands
- Works with any model your hardware can run
- Sessions auto-save and can be resumed

## Quickstart

### Prerequisites

- [Rust toolchain](https://rustup.rs/) (1.70+)
- [Ollama](https://ollama.com/) running locally (or any OpenAI-compatible endpoint)
- A model pulled in Ollama (e.g. `ollama pull qwen3:14b`)

### Build

```bash
git clone https://github.com/codetwentyfive/claw-code-local.git
cd claw-code-local/rust
cargo build -p rusty-claude-cli --release
```

The binary is at `rust/target/release/claw.exe` (Windows) or `rust/target/release/claw` (Linux/macOS).

### Configure

Set two environment variables. The API key value doesn't matter for Ollama — it just needs to be non-empty.

**Bash / Zsh:**
```bash
export OPENAI_API_KEY=ollama
export OPENAI_BASE_URL=http://localhost:11434/v1
```

**PowerShell (add to `$PROFILE`):**
```powershell
$env:OPENAI_API_KEY = "ollama"
$env:OPENAI_BASE_URL = "http://localhost:11434/v1"
```

Optionally add the binary to your PATH for global access.

### Run

```bash
# Interactive REPL
claw --model qwen3:14b

# One-shot prompt
claw --model qwen3:14b "explain this codebase"

# Switch models mid-session with /model
/model qwen3.5-35b-uncensored:iq3m

# Resume your last session
claw --resume latest
```

## Supported providers

The CLI auto-detects the provider from the model name and environment variables:

| Provider | Models | Env vars |
|----------|--------|----------|
| **Ollama** | Any model you've pulled | `OPENAI_API_KEY=ollama` `OPENAI_BASE_URL=http://localhost:11434/v1` |
| **LM Studio** | Any loaded model | `OPENAI_API_KEY=lmstudio` `OPENAI_BASE_URL=http://localhost:1234/v1` |
| **OpenAI** | gpt-4o, o1, etc. | `OPENAI_API_KEY=sk-...` |
| **xAI (Grok)** | grok-3, grok-3-mini | `XAI_API_KEY=xai-...` |
| **Anthropic** | claude-opus, sonnet, haiku | `ANTHROPIC_API_KEY=sk-ant-...` |
| **Any OpenAI-compatible** | Depends on provider | `OPENAI_API_KEY=...` `OPENAI_BASE_URL=https://...` |

## What we changed from upstream

Two patches, both original:

1. **Multi-provider CLI wiring** — The `api` crate already had `ProviderClient` with OpenAI-compat and xAI support, but the CLI hardcoded `AnthropicClient` and always required Anthropic credentials. We swapped it to `ProviderClient::from_model_with_anthropic_auth()` so the provider is auto-detected from the model name and env vars.

2. **Streaming markdown render fix** — `render_markdown()` called `trim_end()` which stripped trailing newlines. In streaming mode each chunk is rendered independently, so block separators (between tables, headings, paragraphs) got eaten and everything ran together on one line. Added a streaming-safe render path that preserves block spacing.

## Upstream

This is a fork of [ultraworkers/claw-code-parity](https://github.com/ultraworkers/claw-code-parity), which is itself a clean-room Rust reimplementation of Claude Code's agent harness — **not** a copy of Anthropic's source code. See the upstream README and [PARITY.md](PARITY.md) for the full porting status.

To sync with upstream:
```bash
git fetch upstream
git merge upstream/main
```

## License

MIT — same as upstream.
