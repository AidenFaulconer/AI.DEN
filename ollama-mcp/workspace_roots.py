"""Resolve MCP workspace from the client's roots/list (VS Code / Continue / Cursor)."""
from __future__ import annotations

import logging
import os
import time
from contextlib import asynccontextmanager
from contextvars import ContextVar
from pathlib import Path
from typing import TYPE_CHECKING
from urllib.parse import unquote, urlparse

if TYPE_CHECKING:
    from mcp.server.fastmcp import Context
    from mcp.server.session import ServerSession

logger = logging.getLogger(__name__)

# Container mount (Docker) or default when client does not send roots
MOUNT_CONTAINER = Path(
    os.environ.get("OLLAMA_MCP_WORKSPACE", os.environ.get("OLLAMA_MCP_MOUNT_CONTAINER", "/workspace"))
).resolve()

_mount_host_raw = (
    os.environ.get("OLLAMA_MCP_MOUNT_HOST")
    or os.environ.get("AIDEN_MCP_WORKSPACE_HOST")
    or "."
)
MOUNT_HOST = Path(_mount_host_raw).expanduser().resolve()

_STATIC_FALLBACK = MOUNT_CONTAINER
_active: ContextVar[Path | None] = ContextVar("aiden_active_workspace", default=None)

# session_key -> (monotonic_time, Path)
_cache: dict[str, tuple[float, Path]] = {}
_CACHE_TTL_SEC = 8.0


def static_workspace_root() -> Path:
    return _STATIC_FALLBACK


def active_workspace_root() -> Path:
    return _active.get() or _STATIC_FALLBACK


def _norm(p: Path) -> str:
    try:
        return str(p.resolve()).replace("\\", "/").lower()
    except OSError:
        return str(p).replace("\\", "/").lower()


def file_uri_to_path(uri: str) -> Path | None:
    raw = (uri or "").strip()
    if not raw:
        return None
    if raw.startswith("file:"):
        parsed = urlparse(raw)
        path = unquote(parsed.path or "")
        if not path:
            return None
        # file:///C:/Users/... on Windows
        if len(path) >= 3 and path[0] == "/" and path[2] == ":":
            path = path[1:]
        return Path(path)
    if len(raw) >= 2 and raw[1] == ":":
        return Path(raw)
    if raw.startswith("/"):
        return Path(raw)
    return None


def map_host_path_to_mount(host_path: Path) -> Path | None:
    """Map a client workspace folder to a path visible inside the MCP server process."""
    host_path = host_path.expanduser()
    try:
        host_resolved = host_path.resolve()
    except OSError:
        host_resolved = host_path

    try:
        rel = host_resolved.relative_to(MOUNT_HOST)
        candidate = (MOUNT_CONTAINER / rel).resolve()
        if candidate.exists():
            return candidate
        # allow new projects under mount before first file touch
        return candidate
    except ValueError:
        pass

    # stdio / local run: host path is directly readable
    if host_resolved.exists():
        return host_resolved

    # last resort: strip to path under container mount by tail match
    parts = [p for p in host_resolved.parts if p not in (".", "..")]
    if not parts:
        return None
    for depth in range(min(6, len(parts)), 0, -1):
        tail = Path(*parts[-depth:])
        candidate = (MOUNT_CONTAINER / tail).resolve()
        if candidate.exists():
            return candidate
    return None


def _cache_key(session: ServerSession | None, context: Context | None) -> str:
    if context is not None:
        cid = getattr(getattr(context, "request_context", None), "meta", None)
        client = getattr(cid, "client_id", None) if cid else None
        if client:
            return str(client)
    if session is not None:
        return str(id(session))
    return "default"


async def resolve_workspace_from_client(
    session: ServerSession | None,
    *,
    context: Context | None = None,
) -> Path:
    """Pick workspace root from MCP client roots, else static mount."""
    key = _cache_key(session, context)
    now = time.monotonic()
    cached = _cache.get(key)
    if cached and (now - cached[0]) < _CACHE_TTL_SEC:
        return cached[1]

    root = _STATIC_FALLBACK
    if session is None:
        _cache[key] = (now, root)
        return root

    try:
        from mcp.types import ClientCapabilities, RootsCapability

        if not session.check_client_capability(ClientCapabilities(roots=RootsCapability())):
            _cache[key] = (now, root)
            return root
    except Exception:
        _cache[key] = (now, root)
        return root

    try:
        result = await session.list_roots()
        roots = getattr(result, "roots", None) or []
    except Exception as exc:
        logger.debug("list_roots failed: %s", exc)
        _cache[key] = (now, root)
        return root

    for item in roots:
        uri = getattr(item, "uri", None)
        if uri is None:
            continue
        host = file_uri_to_path(str(uri))
        if host is None:
            continue
        mapped = map_host_path_to_mount(host)
        if mapped is not None:
            root = mapped.resolve()
            break

    _cache[key] = (now, root)
    return root


@asynccontextmanager
async def workspace_scope(context: Context | None):
    """Bind active_workspace_root() for the duration of a tool call."""
    session = context.session if context is not None else None
    root = await resolve_workspace_from_client(session, context=context)
    token = _active.set(root)
    try:
        yield root
    finally:
        _active.reset(token)


def workspace_info_lines() -> list[str]:
    active = active_workspace_root()
    lines = [
        f"workspace_root: {active}",
        f"mount_container: {MOUNT_CONTAINER}",
        f"mount_host: {MOUNT_HOST}",
        "top_level:",
    ]
    try:
        for entry in sorted(active.iterdir(), key=lambda e: e.name.lower())[:40]:
            tag = "dir" if entry.is_dir() else "file"
            lines.append(f"  [{tag}] {entry.name}")
    except OSError as e:
        lines.append(f"  (list failed: {e})")
    if _norm(active) != _norm(MOUNT_CONTAINER):
        lines.append(
            "Active root follows the VS Code/Continue workspace (MCP roots). "
            "Paths in read_file are relative to workspace_root."
        )
    else:
        lines.append(
            "Paths in read_file/grep_search are relative to workspace_root. "
            "Open your project in VS Code/Continue so MCP roots point at it, "
            "or widen the Docker mount (AIDEN_MCP_WORKSPACE_HOST parent folder)."
        )
    return lines
