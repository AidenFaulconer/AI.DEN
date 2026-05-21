# Research tools (web + symbols + library docs)

> **Context7 is optional and not required.** Use free **`library_docs`** instead — see [free-library-docs.md](free-library-docs.md).

## Free stack (default)

| Tool | Purpose |
|------|---------|
| `library_docs` | PyPI / npm / crates.io / pkg.go.dev + doc fetch + cache |
| `project_dependencies` | List packages in this repo |
| `web_search` | DuckDuckGo (errors, deprecations) |
| `fetch_url` | Read a documentation URL |
| `symbol_search` | Project symbols via **ctags** (`.aiden/tags`) + fallback |
| `grep_search` | Text search in source |

Start: `start-aiden.bat` (includes `ctags-indexer` + `mcp-server`).

## Paid Context7 (optional)

Only if you want their hosted reranking and private libraries. Otherwise skip entirely.
