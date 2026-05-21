"""Free library documentation lookup (no Context7 / paid API)."""

from __future__ import annotations

import hashlib
import json
import os
import re
import time
from pathlib import Path
from typing import Any

import httpx


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, str(default)))
    except ValueError:
        return default


def _strip_html(text: str) -> str:
    import html as html_mod

    text = re.sub(r"(?is)<script.*?>.*?</script>", " ", text)
    text = re.sub(r"(?is)<style.*?>.*?</style>", " ", text)
    text = re.sub(r"<[^>]+>", " ", text)
    return html_mod.unescape(re.sub(r"\s+", " ", text)).strip()


async def _fetch_url_short(url: str, max_chars: int = 4000) -> str:
    async with httpx.AsyncClient(timeout=25.0, follow_redirects=True) as client:
        r = await client.get(url, headers={"User-Agent": _UA})
        r.raise_for_status()
        body = _strip_html(r.text) if "html" in (r.headers.get("content-type") or "") else r.text
    if len(body) > max_chars:
        body = body[:max_chars] + "\n... [truncated]"
    return body

_UA = "AI.DEN-ollama-mcp/1.0"
_CACHE_TTL = _env_int("AIDEN_DOCS_CACHE_TTL_SEC", 86400)


def _cache_dir(workspace: Path) -> Path:
    d = workspace / ".aiden" / "docs-cache"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _cache_key(library: str, ecosystem: str, version: str) -> str:
    raw = f"{ecosystem}:{library}:{version}".lower()
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def _read_cache(workspace: Path, library: str, ecosystem: str, version: str) -> str | None:
    if os.environ.get("AIDEN_DOCS_CACHE", "1").lower() in ("0", "false", "off", "no"):
        return None
    path = _cache_dir(workspace) / f"{_cache_key(library, ecosystem, version)}.txt"
    if not path.is_file():
        return None
    age = time.time() - path.stat().st_mtime
    if age > _CACHE_TTL:
        return None
    return path.read_text(encoding="utf-8", errors="replace")


def _write_cache(workspace: Path, library: str, ecosystem: str, version: str, body: str) -> None:
    if os.environ.get("AIDEN_DOCS_CACHE", "1").lower() in ("0", "false", "off", "no"):
        return
    path = _cache_dir(workspace) / f"{_cache_key(library, ecosystem, version)}.txt"
    path.write_text(body, encoding="utf-8")


def _extract_relevant(text: str, query: str, max_chars: int) -> str:
    """Keep lines/paragraphs that mention query terms."""
    if not query.strip():
        return text[:max_chars]
    terms = [t.lower() for t in re.findall(r"\w{3,}", query) if len(t) > 2][:8]
    if not terms:
        return text[:max_chars]
    chunks: list[str] = []
    for para in re.split(r"\n\s*\n", text):
        low = para.lower()
        if any(t in low for t in terms):
            chunks.append(para.strip())
    body = "\n\n".join(chunks) if chunks else text
    if len(body) > max_chars:
        body = body[:max_chars] + "\n... [truncated]"
    return body


async def _http_get_json(client: httpx.AsyncClient, url: str) -> Any:
    r = await client.get(url, headers={"User-Agent": _UA})
    r.raise_for_status()
    return r.json()


async def _fetch_pypi(client: httpx.AsyncClient, name: str, version: str) -> tuple[str, str]:
    pkg = name.strip().lower().replace("_", "-")
    ver = version.strip()
    url = f"https://pypi.org/pypi/{pkg}/json" if not ver else f"https://pypi.org/pypi/{pkg}/{ver}/json"
    data = await _http_get_json(client, url)
    info = data.get("info") or {}
    parts: list[str] = [
        f"package: {info.get('name', pkg)}",
        f"version: {info.get('version', ver or 'latest')}",
        f"summary: {info.get('summary', '')}",
    ]
    urls = info.get("project_urls") or {}
    doc_url = (
        urls.get("Documentation")
        or urls.get("Docs")
        or urls.get("Homepage")
        or info.get("home_page")
        or ""
    )
    if doc_url:
        parts.append(f"documentation_url: {doc_url}")
    desc = (info.get("description") or "").strip()
    if desc:
        parts.append("\n--- PyPI readme / description ---\n")
        parts.append(desc)
    return "\n".join(parts), str(doc_url or "")


async def _fetch_npm(client: httpx.AsyncClient, name: str, version: str) -> tuple[str, str]:
    pkg = name.strip()
    enc = pkg.replace("/", "%2f")
    url = f"https://registry.npmjs.org/{enc}"
    if version:
        url = f"https://registry.npmjs.org/{enc}/{version}"
    data = await _http_get_json(client, url)
    if version:
        latest = data
    else:
        ver = (data.get("dist-tags") or {}).get("latest") or ""
        latest = (data.get("versions") or {}).get(ver) or data
    parts = [
        f"package: {latest.get('name', pkg)}",
        f"version: {latest.get('version', version or 'latest')}",
        f"description: {latest.get('description', '')}",
    ]
    doc_url = latest.get("homepage") or ""
    repo = latest.get("repository") or {}
    if isinstance(repo, dict):
        repo_url = repo.get("url", "")
        if repo_url:
            parts.append(f"repository: {repo_url}")
            if not doc_url:
                doc_url = repo_url.replace("git+", "").replace(".git", "")
    readme = latest.get("readme") or ""
    if isinstance(readme, str) and readme.strip():
        parts.append("\n--- npm readme ---\n")
        parts.append(readme)
    return "\n".join(parts), doc_url


async def _fetch_crates(client: httpx.AsyncClient, name: str, version: str) -> tuple[str, str]:
    crate = name.strip()
    url = f"https://crates.io/api/v1/crates/{crate}"
    if version:
        url += f"/{version}"
    data = await _http_get_json(client, url)
    c = data.get("crate") or data
    parts = [
        f"crate: {c.get('name', crate)}",
        f"version: {c.get('max_version') or c.get('newest_version') or version}",
        f"description: {c.get('description', '')}",
    ]
    doc_url = c.get("documentation") or ""
    if doc_url:
        parts.append(f"documentation: {doc_url}")
    return "\n".join(parts), doc_url


async def _fetch_go_docs(client: httpx.AsyncClient, import_path: str) -> tuple[str, str]:
    path = import_path.strip().strip("/")
    url = f"https://pkg.go.dev/{path}@latest"
    r = await client.get(url, headers={"User-Agent": _UA})
    r.raise_for_status()
    body = _strip_html(r.text)
    return f"source: {url}\n\n{body}", url


def _guess_ecosystem(library: str, hint: str) -> str:
    if hint and hint != "auto":
        return hint.lower()
    lib = library.strip()
    if "/" in lib and not lib.startswith("@"):
        return "go"
    if lib.startswith("@"):
        return "npm"
    if re.match(r"^[A-Z][a-zA-Z0-9]*$", lib) and "_" not in lib:
        return "rust"
    return "python"


def _detect_deps(workspace: Path) -> list[tuple[str, str]]:
    """Return (ecosystem, name) from lockfiles."""
    found: list[tuple[str, str]] = []
    req = workspace / "requirements.txt"
    if req.is_file():
        for line in req.read_text(encoding="utf-8", errors="replace").splitlines():
            line = line.split("#")[0].strip()
            if line and not line.startswith("-"):
                pkg = re.split(r"[<>=!~\[]", line)[0].strip()
                if pkg:
                    found.append(("python", pkg))
    pkg_json = workspace / "package.json"
    if pkg_json.is_file():
        try:
            data = json.loads(pkg_json.read_text(encoding="utf-8"))
            for section in ("dependencies", "devDependencies"):
                for name in (data.get(section) or {}):
                    found.append(("npm", name))
        except json.JSONDecodeError:
            pass
    cargo = workspace / "Cargo.toml"
    if cargo.is_file():
        in_deps = False
        for line in cargo.read_text(encoding="utf-8", errors="replace").splitlines():
            if line.strip() == "[dependencies]":
                in_deps = True
                continue
            if in_deps and line.startswith("["):
                break
            if in_deps:
                m = re.match(r"^([a-zA-Z0-9_-]+)\s*=", line)
                if m:
                    found.append(("rust", m.group(1)))
    return found[:40]


def project_dependencies_impl(workspace: Path) -> str:
    deps = _detect_deps(workspace)
    if not deps:
        return "No dependencies found in requirements.txt, package.json, or Cargo.toml [dependencies]."
    lines = ["Project dependencies (use library_docs with library= name):"]
    for eco, name in deps:
        lines.append(f"  {eco}: {name}")
    return "\n".join(lines)


async def library_docs_impl(
    workspace: Path,
    query: str,
    library: str = "",
    ecosystem: str = "auto",
    version: str = "",
) -> str:
    """
    Free Context7-style docs: PyPI readme, npm registry, crates.io, pkg.go.dev,
    then optional fetch of official doc URL + web_search fallback.
    """
    query = (query or "").strip()
    if not query:
        return "Error: query required (e.g. 'FastAPI Depends deprecation')"

    lib = (library or "").strip()
    eco = _guess_ecosystem(lib, ecosystem)

    if not lib:
        terms = re.findall(r"\w+", query.lower())[:3]
        for dep_eco, dep_name in _detect_deps(workspace):
            if any(t in dep_name.lower() for t in terms):
                lib, eco = dep_name, dep_eco
                break
        if not lib:
            return (
                "Error: provide library name (e.g. fastapi, react, serde). "
                "Or mention a package from requirements.txt / package.json in the query."
            )

    cached = _read_cache(workspace, lib, eco, version)
    if cached:
        header = f"library: {lib} ({eco}) [cached]\nquery: {query}\n\n"
        return header + _extract_relevant(cached, query, _env_int("OLLAMA_MCP_FETCH_MAX_CHARS", 10000))

    cap = _env_int("OLLAMA_MCP_FETCH_MAX_CHARS", 10000)
    sections: list[str] = [f"library: {lib}", f"ecosystem: {eco}", f"query: {query}", ""]
    doc_url = ""

    try:
        async with httpx.AsyncClient(timeout=35.0, follow_redirects=True) as client:
            if eco == "python":
                body, doc_url = await _fetch_pypi(client, lib, version)
                sections.append(body)
            elif eco == "npm":
                body, doc_url = await _fetch_npm(client, lib, version)
                sections.append(body)
            elif eco == "rust":
                body, doc_url = await _fetch_crates(client, lib, version)
                sections.append(body)
            elif eco == "go":
                body, doc_url = await _fetch_go_docs(client, lib)
                sections.append(body)
            else:
                sections.append(f"Unknown ecosystem {eco!r}; try ecosystem=python|npm|rust|go")
    except httpx.HTTPError as e:
        sections.append(f"registry fetch failed: {e}")

    # llms.txt (many projects publish free LLM-oriented docs)
    if doc_url:
        base = doc_url.rstrip("/")
        for extra in (f"{base}/llms.txt", f"{base}/llms-full.txt"):
            try:
                llm = await _fetch_url_short(extra, 4000)
                sections.append(f"\n--- {extra} ---\n{llm}")
                break
            except Exception:
                pass

    # Fetch official documentation page when registry data is thin
    combined = "\n".join(sections)
    if doc_url and len(combined) < 2500:
        try:
            page = await _fetch_url_short(doc_url, cap)
            sections.append(f"\n--- fetched documentation ---\n{page}")
        except Exception as e:
            sections.append(f"\n(doc page fetch failed: {e})")

    if len("\n".join(sections)) < 1500:
        from research_tools import web_search_impl

        search_q = f"{lib} {query} official documentation"
        if eco == "python":
            search_q += " site:readthedocs.io OR site:python.org"
        try:
            sections.append("\n--- web_search ---\n")
            sections.append(await web_search_impl(search_q, max_results=5))
        except Exception as e:
            sections.append(f"web_search failed: {e}")

    full = "\n".join(sections)
    _write_cache(workspace, lib, eco, version, full)
    relevant = _extract_relevant(full, query, cap)
    return (
        f"source: free registry + fetch (no Context7)\n"
        f"tip: pass ecosystem=python|npm|rust|go if wrong registry was chosen\n\n"
        f"{relevant}"
    )
