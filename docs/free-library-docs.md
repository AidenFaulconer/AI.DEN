# Free library docs (Context7 alternative)

AI.DEN includes **`library_docs`** — no API key, no Context7 subscription.

## What it does

For a package name + question, the MCP server:

1. **Registry metadata** (free public APIs)
   - **Python** — PyPI JSON (readme, `project_urls`, version)
   - **npm** — registry.npmjs.org (readme, homepage, repo)
   - **Rust** — crates.io API
   - **Go** — pkg.go.dev page text
2. **`llms.txt`** on the project docs site (when published)
3. **Fetch** the official documentation URL if the readme is short
4. **`web_search`** fallback (DuckDuckGo) scoped to readthedocs / official docs
5. **Cache** results under `.aiden/docs-cache/` for 24h (configurable)

## MCP tools

| Tool | Use |
|------|-----|
| `library_docs` | Main — `library=fastapi`, `query=Depends deprecation` |
| `project_dependencies` | List deps from `requirements.txt` / `package.json` / `Cargo.toml` |
| `web_search` | Errors, blog posts, Stack Overflow summaries |
| `fetch_url` | Known doc URL |
| `context7_docs` | **Alias** for `library_docs` (same free path) |

## Example agent flow

```
DeprecationWarning: X removed in pydantic v2
→ library_docs(query="migration field_validator", library="pydantic", ecosystem="python")
→ symbol_search(query="BaseModel") in your repo
→ edit_file / run_command
```

## vs Context7

| | Context7 (paid) | AI.DEN `library_docs` (free) |
|--|-----------------|-------------------------------|
| Version-pinned snippets | Strong | Best-effort via `version=` param |
| Private repos | Yes | No |
| Ranking / reranking | LLM-ranked | Keyword extract + registry readme |
| Rate limits | Plan-based | Your network only |

Good enough for compile errors, deprecations, and “how do I use API X” on public packages.

## Configuration (`.env`)

```env
AIDEN_DOCS_CACHE=1
AIDEN_DOCS_CACHE_TTL_SEC=86400
OLLAMA_MCP_FETCH_MAX_CHARS=10000
```

## Disable paid Context7

Leave `CONTEXT7_API_KEY` unset. Do not add the Context7 MCP server in Cursor.

## Apply

```powershell
docker compose up -d --build mcp-server
```
