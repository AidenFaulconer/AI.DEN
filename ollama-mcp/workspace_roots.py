"""Resolve MCP workspace from the client's roots/list (VS Code / Continue / Cursor)."""
from __future__ import annotations

import logging
import os
import time
from contextlib import asynccontextmanager
from contextvars import ContextVar
from pathlib import Path, PurePosixPath
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
    or ".."
)


def _docker_bind_source_for_mount(mount_point: str = "/workspace") -> Path | None:
    """Resolve host path bound to mount_point from /proc/mountinfo (Docker Desktop)."""
    try:
        lines = Path("/proc/mountinfo").read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return None
    best: Path | None = None
    needle = f" {mount_point} "
    for line in lines:
        if needle not in line and not line.rstrip().endswith(mount_point):
            continue
        parts = line.split()
        if "-" not in parts:
            continue
        idx = parts.index("-")
        if idx + 2 >= len(parts):
            continue
        source = parts[idx + 2]
        if source.startswith("/run/desktop/mnt/host/"):
            rest = source[len("/run/desktop/mnt/host/") :]
            best = Path("/" + rest)
        elif source.startswith("/host_mnt/"):
            best = Path(source[len("/host_mnt") :])
        else:
            best = Path(source)
    return best


def _init_mount_host() -> Path:
    raw = (_mount_host_raw or "..").strip()
    proc = _docker_bind_source_for_mount()
    if proc is not None:
        logger.info("MOUNT_HOST from /proc/mountinfo: %s", proc)
        return proc
    p = Path(raw).expanduser()
    if not p.is_absolute():
        # In container, "." resolves to /workspace — useless for URI mapping; use mount root
        if (MOUNT_CONTAINER / raw).resolve().exists():
            return MOUNT_CONTAINER.resolve()
        return MOUNT_CONTAINER.resolve()
    return p.resolve()


MOUNT_HOST = _init_mount_host()

_STATIC_FALLBACK = MOUNT_CONTAINER
_active: ContextVar[Path | None] = ContextVar("aiden_active_workspace", default=None)
_mapped_roots: ContextVar[list[Path] | None] = ContextVar("aiden_mapped_roots", default=None)

_cache: dict[str, tuple[float, Path, list[Path]]] = {}
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
        if len(path) >= 3 and path[0] == "/" and path[2] == ":":
            path = path[1:]
        return Path(path)
    if len(raw) >= 2 and raw[1] == ":":
        return Path(raw)
    if raw.startswith("/"):
        return Path(raw)
    return None


def _posix_parts(path: str) -> tuple[str, ...]:
    return tuple(PurePosixPath(path.replace("\\", "/")).parts)


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
        return candidate
    except ValueError:
        pass

    if host_resolved.exists():
        return host_resolved

    parts = [p for p in host_resolved.parts if p not in (".", "..")]
    if not parts:
        return None
    for depth in range(min(8, len(parts)), 0, -1):
        tail = Path(*parts[-depth:])
        candidate = (MOUNT_CONTAINER / tail).resolve()
        if candidate.exists():
            return candidate
    return None


def map_uri_list_to_mounts(roots: list) -> list[Path]:
    """Map MCP client roots to container paths (deduped)."""
    out: list[Path] = []
    seen: set[str] = set()
    for item in roots:
        uri = getattr(item, "uri", None)
        if uri is None:
            continue
        host = file_uri_to_path(str(uri))
        if host is None:
            continue
        mapped = map_host_path_to_mount(host)
        if mapped is None:
            continue
        key = _norm(mapped)
        if key in seen:
            continue
        seen.add(key)
        out.append(mapped.resolve())
    return out


def _cache_key(session: ServerSession | None, context: Context | None) -> str:
    if context is not None:
        cid = getattr(getattr(context, "request_context", None), "meta", None)
        client = getattr(cid, "client_id", None) if cid else None
        if client:
            return str(client)
    if session is not None:
        return str(id(session))
    return "default"


def pick_workspace_for_relative_path(relative_path: str, mapped_roots: list[Path]) -> Path | None:
    """Choose the client root that actually contains relative_path."""
    parts = _posix_parts(relative_path)
    if not parts:
        return None
    hits: list[Path] = []
    for root in mapped_roots:
        candidate = root.joinpath(*parts)
        if candidate.is_file():
            hits.append(root)
        elif candidate.exists() and candidate.is_dir():
            hits.append(root)
    if not hits:
        return None
    if len(hits) == 1:
        return hits[0]
    return min(hits, key=lambda r: len(str(r)))


def find_file_under_mount(requested: str) -> tuple[Path, Path] | None:
    """
    Locate a file anywhere under MOUNT_CONTAINER.
    Returns (workspace_root, absolute_file_path).
    """
    raw = (requested or "").strip().strip('"').strip("'")
    if not raw:
        return None
    parts = _posix_parts(raw)
    if not parts:
        return None

    mapped = _mapped_roots.get() or []
    root = pick_workspace_for_relative_path(raw, mapped) or active_workspace_root()
    direct = root.joinpath(*parts)
    if direct.is_file():
        return root, direct.resolve()

    suffix = "/".join(parts)
    name = parts[-1]

    # Direct child projects under mount: /workspace/my-app/frontend/...
    for child in sorted(MOUNT_CONTAINER.iterdir(), key=lambda p: p.name.lower()):
        if not child.is_dir() or child.name.startswith("."):
            continue
        cand = child.joinpath(*parts)
        if cand.is_file():
            return child, cand.resolve()

    # Suffix match (handles wrong active root)
    matches: list[Path] = []
    try:
        for hit in MOUNT_CONTAINER.rglob(name):
            if not hit.is_file():
                continue
            rel = hit.relative_to(MOUNT_CONTAINER).as_posix()
            if rel == suffix or rel.endswith("/" + suffix):
                matches.append(hit.resolve())
    except OSError:
        pass

    if len(matches) == 1:
        hit = matches[0]
        wr = hit.parent
        for _ in range(len(parts) - 1):
            wr = wr.parent
        return wr, hit
    if len(matches) > 1:
        # Prefer shortest relative path (closest to mount root)
        hit = min(matches, key=lambda p: len(p.relative_to(MOUNT_CONTAINER).parts))
        wr = hit.parent
        for _ in range(len(parts) - 1):
            wr = wr.parent
        return wr, hit

    return None


async def resolve_workspace_from_client(
    session: ServerSession | None,
    *,
    context: Context | None = None,
    relative_path: str = "",
) -> Path:
    """Pick workspace root from MCP client roots, else static mount."""
    key = _cache_key(session, context)
    now = time.monotonic()
    cached = _cache.get(key)
    if cached and (now - cached[0]) < _CACHE_TTL_SEC and not relative_path:
        _mapped_roots.set(cached[2])
        return cached[1]

    root = _STATIC_FALLBACK
    mapped_list: list[Path] = [MOUNT_CONTAINER]

    if session is not None:
        try:
            from mcp.types import ClientCapabilities, RootsCapability

            if session.check_client_capability(ClientCapabilities(roots=RootsCapability())):
                result = await session.list_roots()
                roots = getattr(result, "roots", None) or []
                mapped_list = map_uri_list_to_mounts(roots)
                if mapped_list:
                    if relative_path:
                        picked = pick_workspace_for_relative_path(relative_path, mapped_list)
                        root = picked or mapped_list[0]
                    else:
                        root = mapped_list[0]
        except Exception as exc:
            logger.debug("list_roots failed: %s", exc)

    _mapped_roots.set(mapped_list)
    _cache[key] = (now, root, mapped_list)
    return root


@asynccontextmanager
async def activate_workspace(root: Path):
    """Temporarily bind active root (e.g. after find_file_under_mount)."""
    token = _active.set(root.resolve())
    try:
        yield root
    finally:
        _active.reset(token)


@asynccontextmanager
async def workspace_scope(context: Context | None, *, relative_path: str = ""):
    """Bind active_workspace_root() for the duration of a tool call."""
    session = context.session if context is not None else None
    root = await resolve_workspace_from_client(
        session, context=context, relative_path=relative_path
    )
    token = _active.set(root)
    try:
        yield root
    finally:
        _active.reset(token)


def workspace_info_lines() -> list[str]:
    active = active_workspace_root()
    mapped = _mapped_roots.get() or []
    lines = [
        f"workspace_root: {active}",
        f"mount_container: {MOUNT_CONTAINER}",
        f"mount_host: {MOUNT_HOST}",
        f"mapped_roots ({len(mapped)}):",
    ]
    for r in mapped[:8]:
        tag = "dir" if r.is_dir() else "path"
        lines.append(f"  - [{tag}] {r}")
    lines.append("top_level (active root):")
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
            "Paths are relative to workspace_root. MCP searches all folders under the Docker mount "
            "when a path is missing from the active root. Set AIDEN_MCP_WORKSPACE_HOST to a parent "
            "folder (e.g. .. or C:/Users/you/projects) and recreate mcp-server."
        )
    return lines
