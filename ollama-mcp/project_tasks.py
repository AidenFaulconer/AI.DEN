"""Detect how to build, test, and run this repo (for MCP + Continue agents)."""

from __future__ import annotations

import json
import re
from pathlib import Path


def _read_text(path: Path, limit: int = 200_000) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")[:limit]
    except OSError:
        return ""


def project_tasks_impl(workspace: Path) -> str:
    """Return suggested commands for this workspace (JSON-ish text for the model)."""
    tasks: dict[str, list[str]] = {
        "stack": [],
        "test": [],
        "lint": [],
        "dev": [],
        "notes": [],
    }

    root = workspace.resolve()
    if (root / "start-aiden.bat").is_file():
        tasks["stack"].append("start-aiden.bat")
        tasks["stack"].append("start-aiden.bat status")
        tasks["stack"].append("start-aiden.bat logs")
        tasks["notes"].append("AI.DEN stack launcher (Windows host).")

    if (root / "docker-compose.yml").is_file():
        tasks["stack"].append("docker compose ps")
        tasks["stack"].append("docker compose up -d")
        tasks["stack"].append("docker compose logs -f mcp-server llamacpp")
        tasks["test"].append("docker compose config")
        if (root / "docker-compose.resources.yml").is_file():
            tasks["stack"].append(
                "docker compose -f docker-compose.yml -f docker-compose.resources.yml up -d"
            )

    pkg = root / "package.json"
    if pkg.is_file():
        try:
            data = json.loads(_read_text(pkg))
            scripts = data.get("scripts") or {}
            for key in ("test", "lint", "build", "dev", "start"):
                if key in scripts:
                    bucket = "test" if key == "test" else "lint" if key == "lint" else "dev"
                    tasks[bucket].append(f"npm run {key}")
        except json.JSONDecodeError:
            pass
        tasks["notes"].append("npm scripts run on HOST unless Node is in MCP container.")

    if (root / "pyproject.toml").is_file() or (root / "requirements.txt").is_file():
        tasks["test"].append("python -m pytest -q")
        tasks["lint"].append("python -m ruff check .")
        tasks["notes"].append("Python tests: prefer run_tests tool or host terminal.")

    if (root / "Makefile").is_file():
        for line in _read_text(root / "Makefile").splitlines():
            if re.match(r"^test\s*:", line):
                tasks["test"].append("make test")
            if re.match(r"^lint\s*:", line):
                tasks["lint"].append("make lint")

    if (root / "launch-claw.bat").is_file():
        tasks["dev"].append("launch-claw.bat")

    tasks["notes"].append(
        "Continue @problems = VS Code diagnostics. Continue @terminal = last IDE terminal output."
    )
    tasks["notes"].append(
        "MCP run_command runs inside Linux mcp-server container; use docker compose for AI.DEN services."
    )

    lines = ["Project tasks (pick one command per step):"]
    for section in ("stack", "dev", "test", "lint", "notes"):
        items = tasks.get(section) or []
        if items:
            lines.append(f"\n{section}:")
            for item in items:
                lines.append(f"  - {item}")
    return "\n".join(lines)


def default_test_command(workspace: Path) -> str | None:
    """Best-effort single test command for run_tests."""
    if (workspace / "docker-compose.yml").is_file():
        return "docker compose config"
    if (workspace / "ollama-mcp" / "server.py").is_file():
        return (
            "python -m py_compile ollama-mcp/server.py ollama-mcp/research_tools.py "
            "ollama-mcp/library_docs.py ollama-mcp/project_tasks.py"
        )
    for prefer in ("npm run test", "make test", "python -m pytest"):
        text = project_tasks_impl(workspace)
        for line in text.splitlines():
            if line.strip().startswith("- ") and prefer in line:
                return line.strip()[2:]
    return None
