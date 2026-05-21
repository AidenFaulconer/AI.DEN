"""Online research + project symbol search for ollama-mcp."""

from __future__ import annotations

import ast
import html
import json
import os
import re
import subprocess
from pathlib import Path
from typing import Any

import httpx

_SKIP_DIRS = frozenset(
    {
        ".git",
        "node_modules",
        ".venv",
        "venv",
        "__pycache__",
        "target",
        "dist",
        "build",
        ".next",
        "models",
        ".aiden-agent-sessions",
    }
)

# Per-language definition heuristics (not full LSP — fast, no extra deps)
_DEF_PATTERNS: dict[str, list[tuple[str, re.Pattern[str]]]] = {
    "python": [
        ("function", re.compile(r"^\s*(?:async\s+)?def\s+(\w+)\s*\(")),
        ("class", re.compile(r"^\s*class\s+(\w+)\s*[\(:]")),
    ],
    "typescript": [
        ("function", re.compile(r"^\s*(?:export\s+)?(?:async\s+)?function\s+(\w+)\s*[\(<]")),
        ("class", re.compile(r"^\s*(?:export\s+)?class\s+(\w+)\s*")),
        ("interface", re.compile(r"^\s*(?:export\s+)?interface\s+(\w+)\s*")),
        ("type", re.compile(r"^\s*(?:export\s+)?type\s+(\w+)\s*=")),
    ],
    "javascript": [
        ("function", re.compile(r"^\s*(?:export\s+)?(?:async\s+)?function\s+(\w+)\s*\(")),
        ("class", re.compile(r"^\s*(?:export\s+)?class\s+(\w+)\s*")),
    ],
    "rust": [
        ("function", re.compile(r"^\s*(?:pub\s+)?fn\s+(\w+)\s*[\(<]")),
        ("struct", re.compile(r"^\s*(?:pub\s+)?struct\s+(\w+)\s*")),
        ("enum", re.compile(r"^\s*(?:pub\s+)?enum\s+(\w+)\s*")),
        ("trait", re.compile(r"^\s*(?:pub\s+)?trait\s+(\w+)\s*")),
    ],
    "go": [
        ("function", re.compile(r"^\s*func\s+(?:\([^)]*\)\s+)?(\w+)\s*\(")),
        ("type", re.compile(r"^\s*type\s+(\w+)\s+")),
    ],
}

_EXT_LANG = {
    ".py": "python",
    ".pyi": "python",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".js": "javascript",
    ".jsx": "javascript",
    ".rs": "rust",
    ".go": "go",
}


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, str(default)))
    except ValueError:
        return default


def _strip_html(text: str) -> str:
    text = re.sub(r"(?is)<script.*?>.*?</script>", " ", text)
    text = re.sub(r"(?is)<style.*?>.*?</style>", " ", text)
    text = re.sub(r"<[^>]+>", " ", text)
    return html.unescape(re.sub(r"\s+", " ", text)).strip()


async def web_search_impl(query: str, max_results: int = 5) -> str:
    """DuckDuckGo instant answers + related topics (no API key)."""
    query = (query or "").strip()
    if not query:
        return "Error: query required"
    max_results = max(1, min(max_results, _env_int("OLLAMA_MCP_WEB_SEARCH_MAX", 5)))

    async with httpx.AsyncClient(timeout=20.0, follow_redirects=True) as client:
        r = await client.get(
            "https://api.duckduckgo.com/",
            params={"q": query, "format": "json", "no_redirect": 1, "no_html": 1},
        )
        r.raise_for_status()
        data = r.json()

    lines: list[str] = [f"query: {query}"]
    if data.get("AbstractText"):
        lines.append(f"summary: {data['AbstractText']}")
        if data.get("AbstractURL"):
            lines.append(f"url: {data['AbstractURL']}")
    for topic in (data.get("RelatedTopics") or [])[:max_results]:
        if isinstance(topic, dict) and topic.get("Text"):
            lines.append(f"- {topic['Text']}")
            if topic.get("FirstURL"):
                lines.append(f"  {topic['FirstURL']}")
        elif isinstance(topic, dict) and topic.get("Topics"):
            for sub in topic["Topics"][:3]:
                if sub.get("Text"):
                    lines.append(f"- {sub['Text']}")

    if len(lines) == 1:
        lines.append(
            "No instant answer. Try library_docs or fetch_url on official documentation."
        )
    return "\n".join(lines)


async def fetch_url_impl(url: str, max_chars: int = 0) -> str:
    """Fetch a URL and return plain text (for docs, release notes, error pages)."""
    url = (url or "").strip()
    if not url:
        return "Error: url required"
    if not url.startswith(("http://", "https://")):
        return "Error: only http(s) URLs supported"
    cap = max_chars or _env_int("OLLAMA_MCP_FETCH_MAX_CHARS", 12000)
    cap = max(1000, min(cap, 50000))

    async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
        r = await client.get(url, headers={"User-Agent": "AI.DEN-ollama-mcp/1.0"})
        r.raise_for_status()
        ctype = (r.headers.get("content-type") or "").lower()
        body = r.text
        if "html" in ctype:
            body = _strip_html(body)
        elif "json" in ctype:
            try:
                body = json.dumps(r.json(), indent=2)[:cap]
            except json.JSONDecodeError:
                pass

    if len(body) > cap:
        body = body[:cap] + "\n... [truncated]"
    return f"url: {url}\n\n{body}"


async def context7_docs_impl(
    query: str,
    library: str = "",
    library_id: str = "",
    *,
    workspace: Path | None = None,
) -> str:
    """Backward-compatible alias → free library_docs (Context7 not required)."""
    if library_id and not library:
        # /vercel/next.js → npm package name guess
        parts = [p for p in library_id.strip("/").split("/") if p and p not in ("websites", "packages", "npm")]
        if parts:
            library = parts[-1]
    from library_docs import library_docs_impl

    root = workspace or Path(os.environ.get("OLLAMA_MCP_WORKSPACE", "/workspace"))
    return await library_docs_impl(root, query, library=library, ecosystem="auto")


def _lang_for_path(fp: Path) -> str | None:
    return _EXT_LANG.get(fp.suffix.lower())


def _ctags_tags_path(workspace: Path) -> Path:
    raw = (os.environ.get("CTAGS_TAGS_FILE") or "").strip()
    if raw:
        p = Path(raw)
        return p if p.is_absolute() else workspace / p
    return workspace / ".aiden" / "tags"


def _ctags_search(workspace: Path, query: str, max_results: int) -> list[str] | None:
    """Lookup symbols via readtags + ctags-indexer output (.aiden/tags)."""
    tags_file = _ctags_tags_path(workspace)
    if not tags_file.is_file() or tags_file.stat().st_size < 8:
        return None
    kinds = os.environ.get("CTAGS_KINDS", "fcm")
    hits: list[str] = []
    for case_insensitive in (False, True):
        try:
            cmd = ["readtags", "-t", kinds, "-n", query, "-f", str(tags_file)]
            if case_insensitive:
                cmd.insert(1, "-i")
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=15,
                check=False,
            )
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return None
        for line in (proc.stdout or "").splitlines():
            if not line.strip() or line.startswith("!"):
                continue
            # name<TAB>file<TAB>line;"<TAB>kind
            parts = line.split("\t")
            if len(parts) < 3:
                continue
            name, fpath, exc = parts[0], parts[1], parts[2]
            line_no = exc.split(";", 1)[0] if exc else "?"
            kind = ""
            if 'kind:' in exc:
                kind = re.search(r"kind:(\w+)", exc)
                kind = kind.group(1) if kind else ""
            try:
                rel = Path(fpath).resolve().relative_to(workspace.resolve()).as_posix()
            except ValueError:
                rel = fpath
            hits.append(f"{rel}:{line_no}: ctags {kind or 'symbol'} {name}")
            if len(hits) >= max_results:
                return hits
        if hits:
            return hits
    return hits if hits else None


def _python_symbols(fp: Path, query: str, max_results: int) -> list[str]:
    out: list[str] = []
    try:
        tree = ast.parse(fp.read_text(encoding="utf-8", errors="replace"))
    except (SyntaxError, OSError):
        return out
    q = query.lower()
    for node in ast.walk(tree):
        name = getattr(node, "name", None)
        if not name or (q and q not in name.lower()):
            continue
        kind = type(node).__name__
        if kind in ("FunctionDef", "AsyncFunctionDef", "ClassDef"):
            rel = fp.as_posix()
            out.append(f"{rel}:{getattr(node, 'lineno', '?')}: {kind} {name}")
            if len(out) >= max_results:
                break
    return out


def symbol_search_impl(
    workspace: Path,
    query: str,
    path: str = ".",
    language: str = "",
    include_vendor: bool = False,
    max_results: int = 60,
) -> str:
    """Find definitions/symbols in the workspace (stdlib/3rd-party via context7_docs or vendor dirs)."""
    query = (query or "").strip()
    if not query:
        return "Error: query required (symbol name or regex)"
    base = workspace / path if path and path != "." else workspace
    if not base.exists():
        return f"Error: path not found: {path}"
    max_results = max(1, min(max_results, _env_int("OLLAMA_MCP_SYMBOL_MAX", 80)))
    ctags_hits = _ctags_search(workspace, query, max_results)
    if ctags_hits:
        return "\n".join(ctags_hits)

    lang_filter = (language or "all").lower().strip()
    use_regex = False
    try:
        name_re = re.compile(query)
        use_regex = True
    except re.error:
        name_re = re.compile(re.escape(query), re.IGNORECASE)

    hits: list[str] = []
    vendor_roots = ("node_modules", "site-packages", ".venv", "venv") if include_vendor else ()

    def scan_file(fp: Path) -> None:
        if len(hits) >= max_results:
            return
        if any(part in _SKIP_DIRS for part in fp.parts):
            return
        if not include_vendor and any(part in vendor_roots for part in fp.parts):
            return
        lang = _lang_for_path(fp)
        if lang_filter != "all" and lang and lang != lang_filter:
            return
        if lang == "python" and not use_regex:
            for line in _python_symbols(fp, query, max_results - len(hits)):
                hits.append(line)
                if len(hits) >= max_results:
                    return
            return
        try:
            if fp.stat().st_size > 2_000_000:
                return
            patterns = _DEF_PATTERNS.get(lang or "", [])
            for i, line in enumerate(
                fp.read_text(encoding="utf-8", errors="replace").splitlines(), 1
            ):
                if len(hits) >= max_results:
                    return
                if use_regex and not name_re.search(line):
                    continue
                matched = False
                for kind, pat in patterns:
                    m = pat.match(line)
                    if m and (not use_regex or name_re.search(m.group(1))):
                        rel = fp.relative_to(workspace).as_posix()
                        hits.append(f"{rel}:{i}: {kind} {m.group(1)}")
                        matched = True
                        break
                if not matched and not patterns and use_regex and name_re.search(line):
                    rel = fp.relative_to(workspace).as_posix()
                    hits.append(f"{rel}:{i}: {line.strip()[:120]}")
        except OSError:
            pass

    if base.is_file():
        scan_file(base.resolve())
    else:
        for fp in base.rglob("*"):
            if len(hits) >= max_results:
                break
            if fp.is_file() and fp.suffix.lower() in _EXT_LANG:
                scan_file(fp)

    if not hits:
        hint = (
            "No symbols found. Wait for ctags-indexer (.aiden/tags), try grep_search, "
            "library_docs for library APIs, or include_vendor=true for node_modules."
        )
        return hint
    return "\n".join(hits)
