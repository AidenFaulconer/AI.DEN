"""
Ollama MCP server: exposes local Ollama API as MCP tools for Cursor, Claude, etc.

Run with:
  uv run server.py                          # stdio (default)
  uv run server.py --transport sse          # SSE over HTTP
  uv run server.py --transport streamable-http  # Streamable HTTP (MCP 2025-03-26)

Options:
  --transport  stdio | sse | streamable-http  (env: OLLAMA_MCP_TRANSPORT)
  --host       bind address                   (env: OLLAMA_MCP_HOST, default 127.0.0.1)
  --port       bind port                      (env: OLLAMA_MCP_PORT, default 8000)

Use stderr for logging (stdio is used for MCP protocol).
"""
import argparse
import asyncio
import fnmatch
import json
import logging
import os
import re
import subprocess
from pathlib import Path
from typing import Any

import httpx
from mcp.server.fastmcp import FastMCP

# Tools the model may call via OpenAI tool_calls (exclude meta / recursion)
CHAT_EXCLUDED_TOOLS = frozenset({"chat", "generate", "agent_chat"})
ALLOWED_TOOL_NAMES = frozenset({
    "read_file", "write_file", "edit_file",
    "list_dir", "grep_search", "glob_files", "run_command",
    "list_models", "list_running_models", "show_model",
    "embed", "pull_model", "delete_model", "copy_model", "ollama_version",
})
# Tools the agent_chat loop may execute server-side (excludes destructive registry ops)
AGENT_EXECUTABLE_TOOLS = ALLOWED_TOOL_NAMES - frozenset({"pull_model", "delete_model", "copy_model"})


def _tool_schema(
    name: str,
    description: str,
    properties: dict[str, Any],
    required: list[str] | None = None,
) -> dict[str, Any]:
    """Build OpenAI tool schema. llama.cpp rejects empty required:[] — omit when no args."""
    params: dict[str, Any] = {"type": "object", "properties": properties}
    if required is None and properties:
        params["required"] = list(properties.keys())
    elif required:
        params["required"] = required
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": params,
        },
    }


def get_tool_definitions() -> list[dict[str, Any]]:
    """OpenAI-style tool list sent to llama.cpp — must match caveman allowlist."""
    return [
        _tool_schema(
            "list_models",
            "List installed models. Use for 'what models', 'list models'. No arguments.",
            {},
        ),
        _tool_schema(
            "list_running_models",
            "List models currently loaded in VRAM/RAM.",
            {},
        ),
        _tool_schema(
            "show_model",
            "Show metadata for one model.",
            {"model": {"type": "string", "description": "Model name or GGUF id"}},
        ),
        _tool_schema(
            "ollama_version",
            "Health check — is inference reachable.",
            {},
        ),
        _tool_schema(
            "read_file",
            "Read a workspace file. Not for listing models.",
            {"path": {"type": "string", "description": "Absolute or relative file path"}},
        ),
        _tool_schema(
            "write_file",
            "Create or overwrite a file with full content. Never use to fake other tools.",
            {
                "path": {"type": "string"},
                "content": {"type": "string"},
            },
        ),
        _tool_schema(
            "edit_file",
            "Replace first occurrence of old_string with new_string in a file.",
            {
                "path": {"type": "string"},
                "old_string": {"type": "string"},
                "new_string": {"type": "string"},
            },
        ),
        _tool_schema(
            "list_dir",
            "List files and directories under a workspace path (non-recursive unless recursive=true).",
            {
                "path": {"type": "string", "description": "Directory path relative to workspace root"},
                "recursive": {"type": "boolean", "description": "List recursively (max depth 4)"},
            },
            ["path"],
        ),
        _tool_schema(
            "grep_search",
            "Search file contents under workspace (regex). Returns matching paths and line snippets.",
            {
                "pattern": {"type": "string", "description": "Regex pattern"},
                "path": {"type": "string", "description": "File or directory to search (default workspace root)"},
                "glob": {"type": "string", "description": "Optional glob filter e.g. *.py"},
                "max_results": {"type": "integer", "description": "Max matches (default 50)"},
            },
            ["pattern"],
        ),
        _tool_schema(
            "glob_files",
            "Find files by glob pattern under workspace (e.g. **/*.py).",
            {
                "pattern": {"type": "string", "description": "Glob pattern"},
                "path": {"type": "string", "description": "Base directory (default workspace root)"},
                "max_results": {"type": "integer", "description": "Max paths (default 100)"},
            },
            ["pattern"],
        ),
        _tool_schema(
            "run_command",
            "Run a shell command in the workspace (tests, builds, git status). Destructive commands blocked.",
            {
                "command": {"type": "string", "description": "Shell command"},
                "cwd": {"type": "string", "description": "Working directory relative to workspace"},
                "timeout_sec": {"type": "integer", "description": "Timeout seconds (default 120, max 600)"},
            },
            ["command"],
        ),
        _tool_schema(
            "generate",
            "Single-turn completion (no history). Prefer chat for conversations.",
            {
                "model": {"type": "string"},
                "prompt": {"type": "string"},
                "system": {"type": "string"},
            },
            ["model", "prompt"],
        ),
        _tool_schema(
            "embed",
            "Embedding vectors for text.",
            {
                "model": {"type": "string"},
                "text": {"type": "string", "description": "String or JSON array of strings"},
            },
        ),
        _tool_schema(
            "pull_model",
            "Download a model from registry.",
            {"name": {"type": "string"}, "insecure": {"type": "boolean"}},
            ["name"],
        ),
        _tool_schema(
            "delete_model",
            "Delete an installed model.",
            {"name": {"type": "string"}},
        ),
        _tool_schema(
            "copy_model",
            "Copy model to new name.",
            {
                "source": {"type": "string"},
                "destination": {"type": "string"},
            },
        ),
    ]


def _tools_for_chat_payload() -> list[dict[str, Any]]:
    return [t for t in get_tool_definitions() if t["function"]["name"] not in CHAT_EXCLUDED_TOOLS]

# Load .env from project root so OLLAMA_BASE_URL etc. can be set there
try:
    from dotenv import load_dotenv
    _env = Path(__file__).resolve().parent / ".env"
    if _env.exists():
        load_dotenv(_env)
except ImportError:
    pass

def _log_level() -> int:
    raw = os.environ.get("OLLAMA_MCP_LOG_LEVEL", "INFO").upper()
    return getattr(logging, raw, logging.INFO)


_log_fmt = "%(levelname)s %(name)s %(message)s"
_stderr = __import__("sys").stderr
logging.basicConfig(level=_log_level(), format=_log_fmt, stream=_stderr)
logger = logging.getLogger("ollama-mcp")

OLLAMA_BASE = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_API_STYLE = os.environ.get("OLLAMA_API_STYLE", "ollama").lower()
_base = OLLAMA_BASE.rstrip("/")
# openai: llama.cpp / model-router on :8765 — use /v1/chat/completions (pipeline injected)
OLLAMA_API = _base if OLLAMA_API_STYLE == "openai" else f"{_base}/api"

# HTTP/SSE server defaults (overridden by CLI args in main())
_MCP_HOST = os.environ.get("OLLAMA_MCP_HOST", "127.0.0.1")
_MCP_PORT = int(os.environ.get("OLLAMA_MCP_PORT", "8000"))
_MCP_TRANSPORT = os.environ.get("OLLAMA_MCP_TRANSPORT", "stdio")


def _timeout_sec() -> float:
    raw = os.environ.get("OLLAMA_TIMEOUT", "120")
    try:
        return max(5.0, float(raw))
    except ValueError:
        return 120.0


def _stream_read_timeout() -> float:
    """Longer read timeout for streaming (chat/generate) so slow tokens don't trip the default."""
    raw = os.environ.get("OLLAMA_STREAM_READ_TIMEOUT", "")
    if raw:
        try:
            return max(5.0, float(raw))
        except ValueError:
            pass
    return _timeout_sec() * 3


# Lazy singleton HTTP client (reused for all requests)
_http_client: httpx.AsyncClient | None = None


async def _get_client() -> httpx.AsyncClient:
    global _http_client
    if _http_client is None:
        _http_client = httpx.AsyncClient(timeout=_timeout_sec())
    return _http_client


mcp = FastMCP("ollama", host=_MCP_HOST, port=_MCP_PORT)


@mcp.custom_route("/health", methods=["GET"])
async def health_check(request):  # noqa: ARG001
    """Liveness probe for Docker and load balancers."""
    from starlette.responses import JSONResponse

    return JSONResponse({"status": "ok"})


def _api_url(path: str) -> str:
    return f"{OLLAMA_API.rstrip('/')}/{path.lstrip('/')}"


def _chat_path() -> str:
    return "v1/chat/completions" if OLLAMA_API_STYLE == "openai" else "chat"


def _parse_chat_response(data: dict[str, Any]) -> tuple[dict[str, Any], str, list[Any] | None]:
    """Return (message_dict, content, tool_calls) from Ollama or OpenAI-shaped JSON."""
    if OLLAMA_API_STYLE == "openai":
        choices = data.get("choices") or []
        if not choices:
            return {}, "", None
        msg = choices[0].get("message") or {}
        content = (msg.get("content") or "").strip()
        if not content:
            content = (msg.get("reasoning_content") or "").strip()
        tool_calls = msg.get("tool_calls")
        return msg, content, tool_calls
    msg = data.get("message") or {}
    return msg, msg.get("content") or "", msg.get("tool_calls")


async def _request(
    method: str,
    path: str,
    **kwargs: Any,
) -> dict[str, Any] | list[Any]:
    url = _api_url(path)
    client = await _get_client()
    resp = await client.request(method, url, **kwargs)
    resp.raise_for_status()
    if resp.content:
        return resp.json()
    return {}


async def _request_stream(
    path: str,
    payload: dict[str, Any],
    content_key: str,
) -> str:
    """Call a streaming endpoint; accumulate content from each NDJSON chunk and return full text."""
    url = _api_url(path)
    payload = {**payload, "stream": True}
    content_parts: list[str] = []
    thinking_parts: list[str] = []
    client = await _get_client()
    stream_timeout = httpx.Timeout(_stream_read_timeout())
    async with client.stream("POST", url, json=payload, timeout=stream_timeout) as resp:
        resp.raise_for_status()
        async for line in resp.aiter_lines():
            line = line.strip()
            if not line:
                continue
            try:
                chunk = json.loads(line)
            except json.JSONDecodeError:
                continue
            # Thinking: chat has message.thinking, generate has top-level thinking (avoid double-count)
            msg = chunk.get("message") or {}
            if isinstance(msg, dict) and msg.get("thinking"):
                thinking_parts.append(msg["thinking"])
            elif chunk.get("thinking"):
                thinking_parts.append(chunk["thinking"])
            # Content: chat has message.content, generate has response
            if isinstance(msg, dict) and content_key in msg:
                content_parts.append(msg[content_key] or "")
            elif content_key in chunk:
                content_parts.append(chunk[content_key] or "")
    content = "".join(content_parts)
    if thinking_parts:
        content = f"[Thinking] {' '.join(thinking_parts).strip()}\n\n{content}"
    return content


async def _request_pull_stream(path: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Consume pull NDJSON stream and return the last chunk (status, digest, etc.)."""
    url = _api_url(path)
    payload = {**payload, "stream": True}
    client = await _get_client()
    stream_timeout = httpx.Timeout(_stream_read_timeout())
    last: dict[str, Any] = {}
    async with client.stream("POST", url, json=payload, timeout=stream_timeout) as resp:
        resp.raise_for_status()
        async for line in resp.aiter_lines():
            line = line.strip()
            if not line:
                continue
            try:
                chunk = json.loads(line)
                last = chunk
            except json.JSONDecodeError:
                continue
    return last


def _env_float(name: str, default: float) -> float:
    raw = os.environ.get(name, "")
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name, "")
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


# Workspace root: repo mount in Docker (/workspace) or AI.DEN parent when running via stdio on host
_default_ws = Path(__file__).resolve().parent.parent
WORKSPACE_ROOT = Path(os.environ.get("OLLAMA_MCP_WORKSPACE", str(_default_ws))).resolve()
WORKSPACE_ROOT.mkdir(parents=True, exist_ok=True)

_CMD_TIMEOUT_DEFAULT = max(5, _env_int("OLLAMA_MCP_CMD_TIMEOUT", 120))
_CMD_TIMEOUT_MAX = 600
_AGENT_MAX_STEPS_DEFAULT = max(1, min(_env_int("OLLAMA_MCP_AGENT_MAX_STEPS", 8), 20))
_GREP_MAX_DEFAULT = max(10, min(_env_int("OLLAMA_MCP_GREP_MAX", 50), 200))
_GLOB_MAX_DEFAULT = max(10, min(_env_int("OLLAMA_MCP_GLOB_MAX", 100), 500))

_CMD_DENYLIST = tuple(
    s.lower()
    for s in (
        "rm -rf /",
        "rm -rf ~",
        "format c:",
        "format /",
        "mkfs.",
        "dd if=",
        ":(){",
        "shutdown",
        "reboot",
        "diskpart",
        "chmod 777 /",
    )
)

_CTX_SIZE = _env_int("OLLAMA_MCP_CTX_SIZE", _env_int("AIDEN_CTX_SIZE", 16384))
_CTX_RESERVE = _env_int("OLLAMA_MCP_CTX_RESERVE", _env_int("AIDEN_CTX_RESERVE", 3072))
_TOOL_RESULT_MAX = _env_int("OLLAMA_MCP_TOOL_RESULT_MAX", 4000)
_COMPACT_THRESHOLD = _env_float("OLLAMA_MCP_COMPACT_THRESHOLD", 0.82)
_PRESERVE_RECENT = max(2, _env_int("OLLAMA_MCP_PRESERVE_RECENT", 6))
_SESSION_DIR = WORKSPACE_ROOT / ".aiden-agent-sessions"


def _max_prompt_tokens() -> int:
    reserve = max(1024, _CTX_RESERVE)
    return max(4096, _CTX_SIZE - reserve)


def _message_text(m: dict[str, Any]) -> str:
    c = m.get("content")
    if isinstance(c, str):
        return c
    if isinstance(c, list):
        parts: list[str] = []
        for p in c:
            if isinstance(p, dict) and isinstance(p.get("text"), str):
                parts.append(p["text"])
        return "\n".join(parts)
    return ""


def _estimate_messages_tokens(messages: list[dict[str, Any]]) -> int:
    chars = sum(len(_message_text(m)) + 24 for m in messages)
    return max(1, chars // 4)


def _shrink_text(text: str, max_chars: int, marker: str) -> str:
    if len(text) <= max_chars:
        return text
    head = int(max_chars * 0.5)
    tail = max_chars - head - len(marker)
    if tail < 120:
        return text[:max_chars] + marker
    return text[:head] + marker + text[-tail:]


def _compress_tool_results(messages: list[dict[str, Any]], keep_recent_tools: int = 4) -> bool:
    """Shrink old tool outputs so the loop can continue without losing the latest results."""
    changed = False
    tool_idxs = [i for i, m in enumerate(messages) if m.get("role") == "tool"]
    for i in tool_idxs[:-keep_recent_tools] if len(tool_idxs) > keep_recent_tools else []:
        m = messages[i]
        text = _message_text(m)
        if len(text) > _TOOL_RESULT_MAX:
            m["content"] = _shrink_text(
                text,
                _TOOL_RESULT_MAX,
                f"\n\n[AIDEN: earlier tool output compressed — was {len(text)} chars]",
            )
            changed = True
    return changed


def _drop_middle_with_summary(messages: list[dict[str, Any]], max_prompt: int) -> bool:
    """Remove oldest non-system turns; insert a short marker so the model knows history was rolled."""
    changed = False
    est = _estimate_messages_tokens(messages)
    dropped = 0
    while est > max_prompt and len(messages) > 3:
        drop_idx = None
        for i in range(1, len(messages) - 1):
            if messages[i].get("role") not in ("system", "developer"):
                drop_idx = i
                break
        if drop_idx is None:
            break
        removed = messages.pop(drop_idx)
        dropped += 1
        changed = True
        est = _estimate_messages_tokens(messages)
        if dropped > 400:
            break
    if changed and dropped > 0:
        summary = {
            "role": "user",
            "content": (
                f"[AIDEN-CONTEXT] {dropped} earlier message(s) removed to stay within context. "
                "Continue from recent tool results and the original task. "
                "Re-read files or re-run commands if you need dropped detail."
            ),
        }
        insert_at = 1
        for i, m in enumerate(messages):
            if m.get("role") in ("system", "developer"):
                insert_at = i + 1
            else:
                break
        messages.insert(insert_at, summary)
    return changed


def _heuristic_compress_messages(messages: list[dict[str, Any]]) -> bool:
    max_prompt = _max_prompt_tokens()
    if _estimate_messages_tokens(messages) <= int(max_prompt * _COMPACT_THRESHOLD):
        return False
    changed = _compress_tool_results(messages)
    changed = _drop_middle_with_summary(messages, max_prompt) or changed
    return changed


async def _summarize_transcript(
    model: str,
    messages: list[dict[str, Any]],
    options: dict[str, Any] | None,
) -> str:
    """LLM summary of dropped history (no tools)."""
    lines: list[str] = []
    for m in messages:
        role = m.get("role", "?")
        text = _message_text(m).strip()
        if not text:
            continue
        if len(text) > 1500:
            text = _shrink_text(text, 1500, "…")
        lines.append(f"{role}: {text}")
    blob = "\n".join(lines[-40:])
    prompt = (
        "Summarize this agent conversation for continuation. Include: goal, files touched, "
        "commands run, errors, fixes applied, and what remains. Be dense, under 400 words.\n\n"
        + blob
    )
    payload = _apply_generation_controls(
        {"model": model, "messages": [{"role": "user", "content": prompt}]},
        options=options,
    )
    _apply_chat_defaults(payload)
    if OLLAMA_API_STYLE == "openai":
        payload["max_tokens"] = min(900, _env_int("OLLAMA_MCP_MAX_TOKENS", 2048))
    _, content, _ = await _chat_completion(payload)
    return content.strip() or "Prior work occurred; details omitted for context limit."


async def _compact_messages(
    model: str,
    messages: list[dict[str, Any]],
    options: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    """Heuristic shrink, then LLM summary + keep recent tail."""
    _heuristic_compress_messages(messages)
    if _estimate_messages_tokens(messages) <= _max_prompt_tokens():
        return messages

    system_msgs = [m for m in messages if m.get("role") in ("system", "developer")]
    tail = messages[-_PRESERVE_RECENT:]
    middle = messages[len(system_msgs) : len(messages) - len(tail)]
    if not middle:
        return messages

    summary = await _summarize_transcript(model, middle, options)
    compacted: list[dict[str, Any]] = []
    compacted.extend(system_msgs)
    compacted.append(
        {
            "role": "user",
            "content": f"[AIDEN-SESSION-SUMMARY]\n{summary}\n\nContinue the task from here.",
        }
    )
    compacted.extend(tail)
    logger.info(
        "compacted context: %d -> %d msgs, ~%d tok",
        len(messages),
        len(compacted),
        _estimate_messages_tokens(compacted),
    )
    return compacted


def _is_context_overflow_error(exc: BaseException) -> bool:
    text = str(exc).lower()
    return (
        "exceed_context" in text
        or "context size" in text
        or "n_ctx" in text
        or "exceeds the available context" in text
    )


async def _chat_completion_safe(
    model: str,
    messages: list[dict[str, Any]],
    options: dict[str, Any] | None,
    *,
    tools: list[dict[str, Any]] | None = None,
) -> tuple[dict[str, Any], str, list[Any] | None]:
    """Chat with automatic compress + one retry on context overflow."""
    working = [dict(m) for m in messages]
    _heuristic_compress_messages(working)

    payload = _apply_generation_controls({"model": model, "messages": working}, options=options)
    _apply_chat_defaults(payload)
    if tools:
        payload["tools"] = tools
        payload["tool_choice"] = "auto"

    try:
        return await _chat_completion(payload)
    except httpx.HTTPStatusError as e:
        if not _is_context_overflow_error(e):
            raise
        logger.warning("context overflow, compacting and retrying")
        compacted = await _compact_messages(model, working, options)
        payload["messages"] = compacted
        return await _chat_completion(payload)


def _session_path(session_id: str) -> Path:
    safe = re.sub(r"[^a-zA-Z0-9_-]+", "_", session_id.strip())[:64]
    _SESSION_DIR.mkdir(parents=True, exist_ok=True)
    return _SESSION_DIR / f"{safe}.json"


def _load_session(session_id: str) -> list[dict[str, Any]] | None:
    path = _session_path(session_id)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        msgs = data.get("messages")
        return msgs if isinstance(msgs, list) else None
    except (OSError, json.JSONDecodeError):
        return None


def _save_session(session_id: str, messages: list[dict[str, Any]], meta: dict[str, Any] | None = None) -> None:
    path = _session_path(session_id)
    payload = {
        "messages": messages,
        "updated": __import__("datetime").datetime.utcnow().isoformat() + "Z",
        "meta": meta or {},
    }
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _resolve_workspace_path(path: str, *, must_exist: bool = False) -> Path:
    """Resolve path inside WORKSPACE_ROOT; reject escapes."""
    raw = (path or ".").strip()
    if not raw:
        raw = "."
    p = Path(raw).expanduser()
    # Windows path inside Linux container: use basename chain under workspace if clearly foreign
    if re.match(r"^[a-zA-Z]:[\\/]", raw):
        parts = [x for x in re.split(r"[\\/]+", raw) if x and x not in (".", "..")]
        p = WORKSPACE_ROOT.joinpath(*parts) if parts else WORKSPACE_ROOT
    elif not p.is_absolute():
        p = WORKSPACE_ROOT / p
    else:
        p = p.resolve()
        try:
            p.relative_to(WORKSPACE_ROOT)
        except ValueError:
            parts = [x for x in p.parts if x not in (".", "..")]
            p = WORKSPACE_ROOT.joinpath(*parts) if parts else WORKSPACE_ROOT
    p = p.resolve()
    try:
        p.relative_to(WORKSPACE_ROOT)
    except ValueError as exc:
        raise ValueError(f"Path outside workspace ({WORKSPACE_ROOT}): {path}") from exc
    if must_exist and not p.exists():
        raise FileNotFoundError(f"Not found: {p}")
    return p


def _command_is_safe(command: str) -> str | None:
    """Return error message if command is blocked, else None."""
    low = command.lower().strip()
    for bad in _CMD_DENYLIST:
        if bad in low:
            return f"Blocked command pattern: {bad!r}"
    return None


def _apply_generation_controls(
    payload: dict[str, Any],
    *,
    options: dict[str, Any] | None = None,
    format: str | dict[str, Any] | None = None,
    keep_alive: str | None = None,
) -> dict[str, Any]:
    """Attach generation controls (Ollama options or OpenAI top-level fields)."""
    if options:
        if OLLAMA_API_STYLE == "openai":
            for key in ("temperature", "top_p", "seed", "max_tokens", "presence_penalty", "frequency_penalty"):
                if key in options:
                    payload[key] = options[key]
        else:
            payload["options"] = options
    if format is not None:
        payload["format"] = format
    if keep_alive:
        payload["keep_alive"] = keep_alive
    return payload


def _apply_chat_defaults(payload: dict[str, Any]) -> dict[str, Any]:
    """Low-variance defaults for reliable tool routing (override via options=)."""
    if OLLAMA_API_STYLE == "openai":
        payload.setdefault("temperature", _env_float("OLLAMA_MCP_TEMPERATURE", 0.15))
        payload.setdefault("top_p", _env_float("OLLAMA_MCP_TOP_P", 0.9))
        payload.setdefault("max_tokens", _env_int("OLLAMA_MCP_MAX_TOKENS", 2048))
    else:
        opts = dict(payload.get("options") or {})
        opts.setdefault("temperature", _env_float("OLLAMA_MCP_TEMPERATURE", 0.15))
        opts.setdefault("top_p", _env_float("OLLAMA_MCP_TOP_P", 0.9))
        payload["options"] = opts
    return payload


def _parse_tool_json(text: str) -> dict[str, Any] | None:
    import re

    if not text or not text.strip():
        return None
    text = text.strip()
    # Qwen / Hermes wrappers
    for pat in (
        r"<tool_call>\s*(\{.*?\})\s*</tool_call>",
        r"<function=([^>]+)>\s*(\{.*?\})\s*</function>",
    ):
        m = re.search(pat, text, re.DOTALL | re.IGNORECASE)
        if m:
            try:
                if m.lastindex and m.lastindex >= 2:
                    return {"name": m.group(1).strip(), "arguments": json.loads(m.group(2))}
                return json.loads(m.group(1))
            except (json.JSONDecodeError, IndexError):
                pass
    m = re.search(r"\{[^{}]*\"name\"\s*:\s*\"[^\"]+\"[^{}]*\"arguments\"\s*:\s*\{.*\}[^{}]*\}", text, re.DOTALL)
    if not m:
        m = re.search(r"\{.*\}", text, re.DOTALL)
    if not m:
        return None
    try:
        obj = json.loads(m.group(0))
    except json.JSONDecodeError:
        return None
    if isinstance(obj, dict) and "name" in obj:
        return obj
    return None


def _tool_call_dict(name: str, arguments: dict[str, Any], call_id: str | None = None) -> dict[str, Any]:
    return {
        "id": call_id or f"call_{name}_{abs(hash(json.dumps(arguments, sort_keys=True))) % 10**8}",
        "type": "function",
        "function": {
            "name": name,
            "arguments": json.dumps(arguments) if isinstance(arguments, dict) else str(arguments),
        },
    }


def _normalize_tool_calls(tool_calls: list[Any]) -> list[dict[str, Any]]:
    """Fix common Qwen mistakes: write_file smuggling, unknown tools, nested JSON."""
    out: list[dict[str, Any]] = []
    for raw in tool_calls or []:
        if not isinstance(raw, dict):
            continue
        fn = raw.get("function") or {}
        name = (fn.get("name") or "").strip()
        args_raw = fn.get("arguments") or "{}"
        try:
            args = json.loads(args_raw) if isinstance(args_raw, str) else dict(args_raw)
        except (json.JSONDecodeError, TypeError):
            args = {}

        # Unwrap write_file used to stash another tool call
        if name == "write_file":
            path = str(args.get("path") or "")
            content = str(args.get("content") or "")
            if "tool_call" in path or path.startswith("/.tmp") or '{"name"' in content:
                nested = _parse_tool_json(content)
                if nested and nested.get("name") in ALLOWED_TOOL_NAMES:
                    out.append(_tool_call_dict(nested["name"], nested.get("arguments") or {}))
                    continue

        if name not in ALLOWED_TOOL_NAMES:
            nested = _parse_tool_json(json.dumps(args) if args else name)
            if nested and nested.get("name") in ALLOWED_TOOL_NAMES:
                out.append(_tool_call_dict(nested["name"], nested.get("arguments") or {}))
                continue
            logger.warning("dropping unknown tool call: %s", name)
            continue

        tc = _tool_call_dict(name, args if isinstance(args, dict) else {})
        if raw.get("id"):
            tc["id"] = raw["id"]
        out.append(tc)
    return out


def _tool_calls_from_content(content: str) -> list[dict[str, Any]] | None:
    parsed = _parse_tool_json(content)
    if not parsed or parsed.get("name") not in ALLOWED_TOOL_NAMES:
        return None
    return [_tool_call_dict(parsed["name"], parsed.get("arguments") or {})]


def _format_tool_response(tool_calls: list[dict[str, Any]]) -> str:
    return json.dumps({"role": "assistant", "tool_calls": tool_calls}, indent=2)


async def _dispatch_tool(name: str, arguments: dict[str, Any]) -> str:
    """Execute one tool server-side (used by agent_chat)."""
    if name not in AGENT_EXECUTABLE_TOOLS:
        return f"Error: tool {name!r} not allowed in agent loop"
    args = arguments if isinstance(arguments, dict) else {}
    try:
        if name == "read_file":
            return await _read_file_impl(str(args.get("path", "")))
        if name == "write_file":
            return await _write_file_impl(str(args.get("path", "")), str(args.get("content", "")))
        if name == "edit_file":
            return await _edit_file_impl(
                str(args.get("path", "")),
                str(args.get("old_string", "")),
                str(args.get("new_string", "")),
            )
        if name == "list_dir":
            return await _list_dir_impl(
                str(args.get("path", ".")),
                bool(args.get("recursive", False)),
            )
        if name == "grep_search":
            return await _grep_search_impl(
                str(args.get("pattern", "")),
                str(args.get("path", ".")),
                str(args.get("glob", "")),
                int(args.get("max_results") or _GREP_MAX_DEFAULT),
            )
        if name == "glob_files":
            return await _glob_files_impl(
                str(args.get("pattern", "*")),
                str(args.get("path", ".")),
                int(args.get("max_results") or _GLOB_MAX_DEFAULT),
            )
        if name == "run_command":
            return await _run_command_impl(
                str(args.get("command", "")),
                str(args.get("cwd", ".")),
                int(args.get("timeout_sec") or _CMD_TIMEOUT_DEFAULT),
            )
        if name == "ollama_version":
            return await ollama_version()
        if name == "list_models":
            return await list_models()
        if name == "list_running_models":
            return await list_running_models()
        if name == "show_model":
            return await show_model(str(args.get("model", "")))
        if name == "embed":
            text = args.get("text", "")
            return await embed(str(args.get("model", "")), text)
        return f"Error: unimplemented tool {name}"
    except Exception as e:
        logger.exception("dispatch %s", name)
        return f"Error: {e}"


async def _agent_loop(
    model: str,
    messages: list[dict[str, Any]],
    max_steps: int,
    options: dict[str, Any] | None = None,
    *,
    session_id: str | None = None,
) -> str:
    """Multi-turn tool loop: LLM → execute tools → feed results → repeat."""
    tool_defs = _tools_for_chat_payload()
    transcript: list[str] = []
    compacted_once = False

    for step in range(1, max_steps + 1):
        _heuristic_compress_messages(messages)

        try:
            msg, content, tool_calls = await _chat_completion_safe(
                model, messages, options, tools=tool_defs or None
            )
        except httpx.HTTPError as e:
            if not compacted_once and _is_context_overflow_error(e):
                messages[:] = await _compact_messages(model, messages, options)
                compacted_once = True
                msg, content, tool_calls = await _chat_completion_safe(
                    model, messages, options, tools=tool_defs or None
                )
            else:
                return f"Agent stopped at step {step}: {e}\n\n" + "\n".join(transcript)

        tool_calls = _normalize_tool_calls(tool_calls) if tool_calls else None
        if not tool_calls and content.strip():
            tool_calls = _tool_calls_from_content(content)

        if not tool_calls:
            if msg.get("thinking") and content:
                content = f"[Thinking] {msg.get('thinking')}\n\n{content}"
            header = f"[agent step {step}/{max_steps} complete]\n" if step > 1 else ""
            body = content or "(no content)"
            if session_id:
                _save_session(session_id, messages, {"last_step": step, "status": "done"})
            return header + body + ("\n\n---\n" + "\n".join(transcript) if transcript else "")

        assistant_msg: dict[str, Any] = {"role": "assistant", "content": content or None, "tool_calls": tool_calls}
        messages.append(assistant_msg)

        for tc in tool_calls:
            fn = tc.get("function") or {}
            tname = fn.get("name") or ""
            try:
                targs = json.loads(fn.get("arguments") or "{}")
            except json.JSONDecodeError:
                targs = {}
            result = await _dispatch_tool(tname, targs)
            transcript.append(f"[{tname}] {result[:500]}{'...' if len(result) > 500 else ''}")
            stored = result
            if len(stored) > _TOOL_RESULT_MAX:
                stored = _shrink_text(
                    stored,
                    _TOOL_RESULT_MAX,
                    f"\n[AIDEN: full output {len(result)} chars — re-run tool if needed]",
                )
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tc.get("id") or f"call_{step}_{tname}",
                    "content": stored,
                }
            )

        if session_id:
            _save_session(
                session_id,
                messages,
                {"last_step": step, "status": "running", "est_tokens": _estimate_messages_tokens(messages)},
            )

    if session_id:
        _save_session(session_id, messages, {"last_step": max_steps, "status": "max_steps"})
    return (
        f"Agent stopped after {max_steps} steps (max reached).\n\n"
        + "\n".join(transcript)
    )


# ---- Info ----

@mcp.tool()
async def ollama_version() -> str:
    """Check if Ollama is reachable and return its version (e.g. for health checks).
    Fails with a clear message if Ollama is not running or not reachable.
    """
    try:
        if OLLAMA_API_STYLE == "openai":
            data = await _request("GET", "v1/models")
            models = data.get("data") or data.get("models") or []
            return f"Inference reachable at {OLLAMA_BASE}. Models: {len(models)}"
        data = await _request("GET", "version")
        version = data.get("version", "unknown")
        return f"Ollama is reachable at {OLLAMA_BASE}. Version: {version}"
    except httpx.HTTPError as e:
        return f"Ollama request failed: {e}. Is Ollama running at {OLLAMA_BASE}?"
    except Exception as e:
        logger.exception("ollama_version")
        return f"Error: {e}"


# ---- Models ----

@mcp.tool()
async def list_models() -> str:
    """List all installed Ollama models (name, size, modified)."""
    try:
        if OLLAMA_API_STYLE == "openai":
            data = await _request("GET", "v1/models")
            models = data.get("data") or data.get("models") or []
        else:
            data = await _request("GET", "tags")
            models = data.get("models") or []
        if not models:
            return "No models installed. Use pull_model to pull a model (e.g. llama3.2)."
        lines = []
        for m in models:
            name = m.get("name") or m.get("id", "?")
            size = m.get("size")
            size_mb = f"{size / (1024**2):.0f} MB" if size else "?"
            lines.append(f"- {name} ({size_mb})")
        return "\n".join(lines)
    except httpx.HTTPError as e:
        return f"Ollama request failed: {e}. Is Ollama running at {OLLAMA_BASE}?"
    except Exception as e:
        logger.exception("list_models")
        return f"Error: {e}"


@mcp.tool()
async def list_running_models() -> str:
    """List models currently loaded in Ollama (running)."""
    try:
        data = await _request("GET", "ps")
        models = data.get("models") or []
        if not models:
            return "No models currently loaded."
        return "\n".join(f"- {m.get('name', '?')}" for m in models)
    except httpx.HTTPError as e:
        return f"Ollama request failed: {e}"
    except Exception as e:
        logger.exception("list_running_models")
        return f"Error: {e}"


@mcp.tool()
async def show_model(model: str) -> str:
    """Get details for an installed model (parameters, family, size, etc.).
    Args:
        model: Model name (e.g. llama3.2, gemma3).
    """
    try:
        data = await _request("POST", "show", json={"name": model})
        return json.dumps(data, indent=2)
    except httpx.HTTPError as e:
        return f"Ollama request failed: {e}"
    except Exception as e:
        logger.exception("show_model")
        return f"Error: {e}"


# ---- Chat & Generate ----
async def _chat_completion(payload: dict[str, Any]) -> tuple[dict[str, Any], str, list[Any] | None]:
    chat_path = _chat_path()
    payload = {**payload, "stream": False}
    data = await _request("POST", chat_path, json=payload)
    return _parse_chat_response(data)


@mcp.tool()
async def chat(
    model: str,
    messages: list[dict[str, str]],
    stream: bool = False,
    options: dict[str, Any] | None = None,
    format: str | dict[str, Any] | None = None,
    keep_alive: str | None = None,
) -> str:
    """Chat with Ollama model. Returns tool calls if the model requests them."""
    try:
        payload = _apply_generation_controls(
            {"model": model, "messages": messages},
            options=options,
            format=format,
            keep_alive=keep_alive,
        )
        _apply_chat_defaults(payload)
        tool_defs = _tools_for_chat_payload()
        if tool_defs:
            payload["tools"] = tool_defs
            payload["tool_choice"] = "auto"

        if stream and not tool_defs:
            return await _request_stream(_chat_path(), payload, content_key="content")

        msg, content, tool_calls = await _chat_completion(payload)
        tool_calls = _normalize_tool_calls(tool_calls) if tool_calls else None

        if not tool_calls and content.strip():
            tool_calls = _tool_calls_from_content(content)

        # One retry with lower temperature if model returned text but user clearly wanted a tool
        if not tool_calls and tool_defs and _env_int("OLLAMA_MCP_TOOL_RETRY", 1):
            last_user = ""
            for m in reversed(messages):
                if m.get("role") == "user":
                    last_user = (m.get("content") or "").lower()
                    break
            hints = (
                "list model", "list_models", "read file", "read_file", "which model", "show model",
                "run test", "run_command", "grep", "terminal", "debug",
            )
            if any(h in last_user for h in hints):
                retry = {**payload, "temperature": 0.05, "messages": messages}
                _, content2, tool_calls2 = await _chat_completion(retry)
                tool_calls2 = _normalize_tool_calls(tool_calls2) if tool_calls2 else None
                if not tool_calls2 and content2.strip():
                    tool_calls2 = _tool_calls_from_content(content2)
                if tool_calls2:
                    return _format_tool_response(tool_calls2)
                content = content2 or content

        if tool_calls:
            return _format_tool_response(tool_calls)

        if msg.get("thinking"):
            content = f"[Thinking] {msg.get('thinking')}\n\n{content}"
        return content

    except httpx.HTTPError as e:
        return f"Ollama request failed: {e}"
    except Exception as e:
        logger.exception("chat")
        return f"Error: {e}"


@mcp.tool()
async def agent_chat(
    model: str,
    message: str,
    max_steps: int | None = None,
    options: dict[str, Any] | None = None,
    session_id: str | None = None,
    continue_session: bool = False,
) -> str:
    """Run a multi-step coding agent: calls the local model, executes tools, loops until done.

    Use for tasks that need read_file + run_command + grep (tests, debug, refactors).
    Context is compressed automatically when near the limit so the loop can keep going.

    Args:
        model: Model id (e.g. from list_models).
        message: User task / question.
        max_steps: Max tool rounds (default OLLAMA_MCP_AGENT_MAX_STEPS, cap 20).
        options: Optional generation overrides (temperature, max_tokens, etc.).
        session_id: Optional id to resume/save transcript under .aiden-agent-sessions/.
        continue_session: If true and session_id set, append to saved messages instead of fresh start.
    """
    try:
        steps = max_steps if max_steps is not None else _AGENT_MAX_STEPS_DEFAULT
        steps = max(1, min(int(steps), 20))
        messages: list[dict[str, Any]]
        if session_id and continue_session:
            loaded = _load_session(session_id)
            messages = loaded if loaded else []
            messages.append({"role": "user", "content": message})
        else:
            messages = [{"role": "user", "content": message}]
        out = await _agent_loop(
            model, messages, steps, options=options, session_id=session_id
        )
        if session_id:
            out += f"\n\n[session_id={session_id}]"
        return out
    except httpx.HTTPError as e:
        return f"Ollama request failed: {e}"
    except Exception as e:
        logger.exception("agent_chat")
        return f"Error: {e}"


@mcp.tool()
async def generate(
    model: str,
    prompt: str,
    system: str | None = None,
    stream: bool = False,
    options: dict[str, Any] | None = None,
    format: str | dict[str, Any] | None = None,
    keep_alive: str | None = None,
) -> str:
    """Generate a completion for a single prompt (no conversation history).
    Args:
        model: Model name (e.g. llama3.2, gemma3).
        prompt: The user prompt text.
        system: Optional system prompt.
        stream: If true, Ollama streams tokens (we accumulate and return the full reply). If false, Ollama returns one JSON response.
        options: Optional Ollama runtime options (for example temperature, seed, num_ctx).
        format: Optional response format. Use "json" or a JSON schema object for structured outputs.
        keep_alive: Optional Ollama keep_alive value (for example "30m" or "0").
    """
    try:
        payload = _apply_generation_controls(
            {"model": model, "prompt": prompt},
            options=options,
            format=format,
            keep_alive=keep_alive,
        )
        if system:
            payload["system"] = system
        if stream:
            return await _request_stream("generate", payload, content_key="response")
        payload["stream"] = False
        data = await _request("POST", "generate", json=payload)
        response = data.get("response") or ""
        if data.get("thinking"):
            response = f"[Thinking] {data.get('thinking')}\n\n{response}"
        return response
    except httpx.HTTPError as e:
        return f"Ollama request failed: {e}"
    except Exception as e:
        logger.exception("generate")
        return f"Error: {e}"


# ---- Embeddings ----

@mcp.tool()
async def embed(model: str, text: str | list[str]) -> str:
    """Get embeddings for text. Text can be a string or list of strings.
    Args:
        model: Embedding model name (e.g. nomic-embed-text).
        text: Single string or list of strings to embed.
    """
    try:
        inputs = [text] if isinstance(text, str) else text
        payload = {"model": model, "input": inputs}
        data = await _request("POST", "embed", json=payload)
        embeddings = data.get("embeddings") or []
        return json.dumps({"embeddings": embeddings, "count": len(embeddings)})
    except httpx.HTTPError as e:
        return f"Ollama request failed: {e}"
    except Exception as e:
        logger.exception("embed")
        return f"Error: {e}"


# ---- Model lifecycle ----

@mcp.tool()
async def copy_model(source: str, destination: str) -> str:
    """Copy an existing model to a new name (e.g. for a backup or variant).
    Args:
        source: Existing model name to copy from.
        destination: New model name to create.
    """
    try:
        await _request("POST", "copy", json={"source": source, "destination": destination})
        return f"Copied model '{source}' to '{destination}'."
    except httpx.HTTPError as e:
        return f"Ollama request failed: {e}"
    except Exception as e:
        logger.exception("copy_model")
        return f"Error: {e}"


@mcp.tool()
async def pull_model(name: str, insecure: bool = False) -> str:
    """Pull a model from the registry (e.g. llama3.2, gemma3). Consumes the full stream and returns the final status.
    Args:
        name: Model name to pull (e.g. llama3.2, mistral).
        insecure: Allow insecure connections to the registry.
    """
    try:
        payload: dict[str, Any] = {"name": name}
        if insecure:
            payload["insecure"] = True
        data = await _request_pull_stream("pull", payload)
        status = data.get("status", "unknown")
        digest = data.get("digest", "")
        out = f"Pull finished: {status}."
        if digest:
            out += f" (digest: {digest[:16]}...)" if len(digest) > 16 else f" (digest: {digest})"
        return out
    except httpx.HTTPError as e:
        return f"Ollama request failed: {e}"
    except Exception as e:
        logger.exception("pull_model")
        return f"Error: {e}"


@mcp.tool()
async def delete_model(name: str) -> str:
    """Delete an installed model from Ollama.
    Args:
        name: Exact model name to delete.
    """
    try:
        await _request("DELETE", "delete", json={"name": name})
        return f"Deleted model: {name}"
    except httpx.HTTPError as e:
        return f"Ollama request failed: {e}"
    except Exception as e:
        logger.exception("delete_model")
        return f"Error: {e}"


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Ollama MCP server",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--transport",
        choices=["stdio", "sse", "streamable-http"],
        default=_MCP_TRANSPORT,
        help="Transport protocol (default: %(default)s, env: OLLAMA_MCP_TRANSPORT)",
    )
    parser.add_argument(
        "--host",
        default=_MCP_HOST,
        help="Bind host for HTTP/SSE transports (default: %(default)s, env: OLLAMA_MCP_HOST)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=_MCP_PORT,
        help="Bind port for HTTP/SSE transports (default: %(default)s, env: OLLAMA_MCP_PORT)",
    )
    return parser.parse_args()


def main() -> None:
    args = _parse_args()

    # Update host/port on the already-constructed mcp instance if overridden via CLI
    mcp.settings.host = args.host
    mcp.settings.port = args.port

    transport = args.transport
    if transport in ("sse", "streamable-http"):
        logger.info(
            "Starting Ollama MCP server (%s) on http://%s:%d",
            transport,
            args.host,
            args.port,
        )
        if transport == "sse":
            logger.info("SSE endpoint: http://%s:%d/sse", args.host, args.port)
        else:
            logger.info("MCP endpoint: http://%s:%d/mcp", args.host, args.port)

    mcp.run(transport=transport)


# edited tool calls added for ollama
# @mcp.tool()
# async def write_file(path: str, content: str) -> str:
#     """Write content to a file (overwrites existing)."""
#     try:
#         from pathlib import Path
#         Path(path).write_text(content)
#         return f"Written to {path}"
#     except Exception as e:
#         return f"Error: {e}"

# @mcp.tool()
# async def edit_file(path: str, old_string: str, new_string: str) -> str:
#     """Replace first occurrence of old_string with new_string in a file."""
#     try:
#         from pathlib import Path
#         content = Path(path).read_text()
#         if old_string not in content:
#             return "Error: old_string not found"
#         new_content = content.replace(old_string, new_string, 1)
#         Path(path).write_text(new_content)
#         return f"Edited {path}"
#     except Exception as e:
#         return f"Error: {e}"


async def _read_file_impl(path: str) -> str:
    p = _resolve_workspace_path(path, must_exist=True)
    if p.is_dir():
        return f"Error: {p} is a directory, not a file"
    text = p.read_text(encoding="utf-8")
    if len(text) > 200_000:
        return text[:200_000] + f"\n\n... truncated ({len(text)} chars total)"
    return text


async def _write_file_impl(path: str, content: str) -> str:
    p = _resolve_workspace_path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    return f"Successfully wrote to {p}"


async def _edit_file_impl(path: str, old_string: str, new_string: str) -> str:
    p = _resolve_workspace_path(path, must_exist=True)
    body = p.read_text(encoding="utf-8")
    if old_string not in body:
        return f"Error: Could not find old_string in {p}"
    p.write_text(body.replace(old_string, new_string, 1), encoding="utf-8")
    return f"Successfully edited {p}"


async def _list_dir_impl(path: str, recursive: bool = False) -> str:
    root = _resolve_workspace_path(path, must_exist=True)
    if not root.is_dir():
        return f"Error: not a directory: {root}"
    lines: list[str] = []
    max_entries = 500

    def add_entry(entry: Path) -> None:
        rel = entry.relative_to(WORKSPACE_ROOT)
        kind = "dir" if entry.is_dir() else "file"
        lines.append(f"{kind}\t{rel.as_posix()}")

    if recursive:
        depth = 0
        for dirpath, dirnames, filenames in os.walk(root):
            depth = dirpath.replace(str(root), "").count(os.sep)
            if depth > 4:
                dirnames.clear()
                continue
            for name in sorted(dirnames + filenames):
                if len(lines) >= max_entries:
                    lines.append("... truncated")
                    return "\n".join(lines)
                add_entry(Path(dirpath) / name)
    else:
        for entry in sorted(root.iterdir(), key=lambda x: (not x.is_dir(), x.name.lower())):
            if len(lines) >= max_entries:
                lines.append("... truncated")
                break
            add_entry(entry)
    return "\n".join(lines) if lines else "(empty directory)"


async def _grep_search_impl(
    pattern: str,
    path: str = ".",
    glob_pattern: str = "",
    max_results: int = 50,
) -> str:
    if not pattern.strip():
        return "Error: pattern required"
    try:
        regex = re.compile(pattern)
    except re.error as e:
        return f"Error: invalid regex: {e}"
    base = _resolve_workspace_path(path, must_exist=True)
    max_results = max(1, min(max_results, _GREP_MAX_DEFAULT))
    matches: list[str] = []
    skip_dirs = {".git", "node_modules", ".venv", "__pycache__", "target"}

    def scan_file(fp: Path) -> None:
        if len(matches) >= max_results:
            return
        try:
            if fp.stat().st_size > 2_000_000:
                return
            for i, line in enumerate(fp.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
                if regex.search(line):
                    rel = fp.relative_to(WORKSPACE_ROOT)
                    matches.append(f"{rel.as_posix()}:{i}:{line[:200]}")
                    if len(matches) >= max_results:
                        return
        except (OSError, UnicodeError):
            pass

    if base.is_file():
        scan_file(base)
    else:
        for fp in base.rglob("*"):
            if len(matches) >= max_results:
                break
            if not fp.is_file():
                continue
            if any(part in skip_dirs for part in fp.parts):
                continue
            if glob_pattern and not fnmatch.fnmatch(fp.name, glob_pattern):
                continue
            scan_file(fp)

    return "\n".join(matches) if matches else "No matches"


async def _glob_files_impl(pattern: str, path: str = ".", max_results: int = 100) -> str:
    base = _resolve_workspace_path(path, must_exist=True)
    if not base.is_dir():
        return f"Error: not a directory: {base}"
    max_results = max(1, min(max_results, _GLOB_MAX_DEFAULT))
    found: list[str] = []
    for fp in base.glob(pattern):
        if len(found) >= max_results:
            found.append("... truncated")
            break
        if fp.is_file() or fp.is_dir():
            found.append(fp.relative_to(WORKSPACE_ROOT).as_posix())
    return "\n".join(found) if found else "No matches"


async def _run_command_impl(command: str, cwd: str = ".", timeout_sec: int = 120) -> str:
    command = command.strip()
    if not command:
        return "Error: empty command"
    blocked = _command_is_safe(command)
    if blocked:
        return blocked
    timeout_sec = max(5, min(int(timeout_sec), _CMD_TIMEOUT_MAX))
    workdir = _resolve_workspace_path(cwd)
    if not workdir.is_dir():
        return f"Error: cwd is not a directory: {workdir}"

    def run() -> str:
        proc = subprocess.run(
            command,
            shell=True,
            cwd=str(workdir),
            capture_output=True,
            text=True,
            timeout=timeout_sec,
            env={**os.environ, "PYTHONIOENCODING": "utf-8"},
        )
        out = (proc.stdout or "") + (proc.stderr or "")
        if len(out) > 100_000:
            out = out[:100_000] + "\n... output truncated"
        header = f"exit_code={proc.returncode} cwd={workdir}\n"
        return header + (out or "(no output)")

    return await asyncio.to_thread(run)


@mcp.tool()
async def write_file(path: str, content: str) -> str:
    """Write content to a file (overwrites existing). Path is relative to workspace root."""
    try:
        return await _write_file_impl(path, content)
    except Exception as e:
        return f"Error writing file: {e}"


@mcp.tool()
async def edit_file(path: str, old_string: str, new_string: str) -> str:
    """Replace the first occurrence of old_string with new_string in a file."""
    try:
        return await _edit_file_impl(path, old_string, new_string)
    except Exception as e:
        return f"Error editing file: {e}"


@mcp.tool()
async def read_file(path: str) -> str:
    """Read the full content of a file under the workspace."""
    try:
        return await _read_file_impl(path)
    except FileNotFoundError as e:
        return f"Error: {e}"
    except Exception as e:
        return f"Error reading file: {e}"


@mcp.tool()
async def list_dir(path: str = ".", recursive: bool = False) -> str:
    """List files and directories under a workspace path."""
    try:
        return await _list_dir_impl(path, recursive)
    except Exception as e:
        return f"Error: {e}"


@mcp.tool()
async def grep_search(
    pattern: str,
    path: str = ".",
    glob: str = "",
    max_results: int = 0,
) -> str:
    """Search file contents under workspace with a regex pattern."""
    try:
        limit = max_results or _GREP_MAX_DEFAULT
        return await _grep_search_impl(pattern, path, glob, limit)
    except Exception as e:
        return f"Error: {e}"


@mcp.tool()
async def glob_files(
    pattern: str,
    path: str = ".",
    max_results: int = 0,
) -> str:
    """Find files by glob pattern (e.g. **/*.py) under workspace."""
    try:
        limit = max_results or _GLOB_MAX_DEFAULT
        return await _glob_files_impl(pattern, path, limit)
    except Exception as e:
        return f"Error: {e}"


@mcp.tool()
async def run_command(
    command: str,
    cwd: str = ".",
    timeout_sec: int = 0,
) -> str:
    """Run a shell command in the workspace (tests, builds, git, docker compose)."""
    try:
        tout = timeout_sec or _CMD_TIMEOUT_DEFAULT
        return await _run_command_impl(command, cwd, tout)
    except Exception as e:
        return f"Error: {e}"

# 

# integrate into cursor

# @mcp.tool()
# async def switch_mode(target_mode_id: str, explanation: str) -> str:
#     """Switch the assistant's operational mode.
#     Args:
#         target_mode_id: One of "ask", "plan", "agent"
#         explanation: Why the mode change is needed
#     """
#     # This tool doesn't need to do anything except return confirmation.
#     # The client (Cursor) will interpret the mode change from the tool call itself.
#     return f"Mode switched to {target_mode_id}. Reason: {explanation}"

# # 

if __name__ == "__main__":
    main()
