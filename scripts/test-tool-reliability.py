#!/usr/bin/env python3
"""Score local MCP chat tool-calling reliability (run after stack is up)."""
from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

# ollama-mcp on path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ollama-mcp"))

import server  # noqa: E402

MODEL = os.environ.get("CODER_MODEL", "Qwen3.6-27B-MTP-UD-Q4_K_XL.gguf")

CASES = [
    {
        "name": "list_models_direct",
        "messages": [{"role": "user", "content": "Call list_models. Reply only with tool_calls, no prose."}],
        "expect_tool": "list_models",
    },
    {
        "name": "list_models_natural",
        "messages": [{"role": "user", "content": "What models are installed? Use the list_models tool."}],
        "expect_tool": "list_models",
    },
    {
        "name": "no_tool_plain",
        "messages": [{"role": "user", "content": "Say exactly: HELLO_ONLY (no tools)."}],
        "expect_tool": None,
    },
]


def _first_tool_name(result: str) -> str | None:
    text = result.strip()
    if not text.startswith("{"):
        return None
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return None
    calls = data.get("tool_calls") or []
    if not calls:
        return None
    fn = calls[0].get("function") or {}
    return fn.get("name")


async def run_case(case: dict) -> tuple[bool, str]:
    out = await server.chat(
        model=MODEL,
        messages=case["messages"],
        stream=False,
        options={"temperature": 0.1},
    )
    got = _first_tool_name(out)
    expected = case.get("expect_tool")
    if expected is None:
        ok = got is None and "HELLO" in out.upper()
        return ok, f"got_tool={got!r} text={out[:120]!r}"
    ok = got == expected
    return ok, f"got_tool={got!r} expected={expected!r} snippet={out[:160]!r}"


async def main() -> int:
    print(f"Model: {MODEL}")
    print(f"Backend: {server.OLLAMA_BASE} ({server.OLLAMA_API_STYLE})\n")
    passed = 0
    for case in CASES:
        try:
            ok, detail = await run_case(case)
        except Exception as e:
            ok, detail = False, str(e)
        status = "PASS" if ok else "FAIL"
        print(f"[{status}] {case['name']}: {detail}")
        if ok:
            passed += 1
    pct = 100 * passed / len(CASES) if CASES else 0
    print(f"\n{passed}/{len(CASES)} passed ({pct:.0f}%)")
    return 0 if passed == len(CASES) else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
