#!/usr/bin/env python3
"""Multi-tier model accuracy/latency benchmark via model-router :8765.

Run after stack is up:
  python scripts/benchmark-model-eval.py
  python scripts/benchmark-model-eval.py --tier fast --quick
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

try:
    import httpx
except ImportError:
    print("pip install httpx", file=sys.stderr)
    raise SystemExit(1)

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BASE = os.environ.get("OPENAI_BASE_URL", "http://localhost:8765/v1").rstrip("/")
QUALITY_MODEL = os.environ.get("CODER_MODEL", "Qwen3.6-27B-MTP-UD-Q4_K_XL.gguf")
FAST_MODEL = os.environ.get("CODER_FAST_MODEL", "Qwen3.5-9B-UD-Q4_K_XL.gguf")


@dataclass
class Case:
    id: str
    tier: str  # easy | medium | hard | expert
    prompt: str
    max_tokens: int
    check: Callable[[str], tuple[bool, str]]
    expect_tier: str | None = None  # for auto-routing cases


@dataclass
class Result:
    case_id: str
    difficulty: str
    route_tier: str
    model_requested: str
    model_selected: str | None
    pipeline_injected: str | None
    prompt_tokens_est: str | None
    latency_s: float
    status: int
    pass_: bool
    detail: str
    answer_snippet: str
    error: str | None = None


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s.strip().lower())


def extract_assistant_text(data: dict[str, Any]) -> str:
    """Content first; fall back to reasoning_content (Qwen3 when thinking eats budget)."""
    choices = data.get("choices") or []
    if not choices:
        return ""
    msg = choices[0].get("message") or {}
    content = (msg.get("content") or "").strip()
    if content:
        return content
    return (msg.get("reasoning_content") or "").strip()


def check_exact(expected: str) -> Callable[[str], tuple[bool, str]]:
    def _fn(text: str) -> tuple[bool, str]:
        ok = expected.lower() in _norm(text)
        return ok, f"want contains {expected!r}"

    return _fn


def check_regex(pattern: str, flags: int = re.I) -> Callable[[str], tuple[bool, str]]:
    rx = re.compile(pattern, flags)

    def _fn(text: str) -> tuple[bool, str]:
        ok = bool(rx.search(text))
        return ok, f"pattern {pattern!r}"

    return _fn


def check_math_391() -> Callable[[str], tuple[bool, str]]:
    def _fn(text: str) -> tuple[bool, str]:
        ok = "391" in text.replace(",", "")
        return ok, "want 391"

    return _fn


def check_json_status_ok() -> Callable[[str], tuple[bool, str]]:
    def _fn(text: str) -> tuple[bool, str]:
        try:
            # strip markdown fences
            t = text.strip()
            if "```" in t:
                t = re.sub(r"^```(?:json)?\s*|\s*```$", "", t, flags=re.M).strip()
            data = json.loads(t)
            ok = data.get("status") == "ok"
        except json.JSONDecodeError:
            ok = '"status"' in text and "ok" in text.lower()
        return ok, "want JSON status ok"

    return _fn


def check_reverse_fn() -> Callable[[str], tuple[bool, str]]:
    def _fn(text: str) -> tuple[bool, str]:
        ok = "[::-1]" in text or "reverse" in text.lower() and "def " in text
        return ok, "want reverse-string solution"

    return _fn


def check_http_413() -> Callable[[str], tuple[bool, str]]:
    def _fn(text: str) -> tuple[bool, str]:
        t = text.lower()
        ok = "413" in text and ("too large" in t or "payload" in t or "entity" in t or "big" in t)
        return ok, "want 413 + too large meaning"

    return _fn


def check_subtraction_bug() -> Callable[[str], tuple[bool, str]]:
    def _fn(text: str) -> tuple[bool, str]:
        ok = "-" in text and ("+" in text or "add" in text.lower() or "subtract" in text.lower())
        return ok, "want minus vs plus fix"

    return _fn


def check_binary_search() -> Callable[[str], tuple[bool, str]]:
    def _fn(text: str) -> tuple[bool, str]:
        t = text.lower()
        ok = ("binary" in t or "mid" in t) and ("mid" in t or "middle" in t) and (
            "low" in t or "high" in t or "left" in t or "length" in t or "target" in t
        )
        return ok, "want binary search structure"

    return _fn


def check_syllogism_no() -> Callable[[str], tuple[bool, str]]:
    def _fn(text: str) -> tuple[bool, str]:
        t = text.lower()
        ok = (
            "cannot" in t
            or "can't" in t
            or "not valid" in t
            or t.strip().startswith("no")
            or "does not follow" in t
            or "disjoint" in t
        ) and ("some" in t or "conclude" in t or "a are c" in t.replace(" ", ""))
        return ok, "want invalid syllogism (some A are C not forced)"

    return _fn


def build_cases(quick: bool) -> list[Case]:
    cases: list[Case] = [
        Case("easy_word", "easy", "Reply with exactly one word, no punctuation: PIPELINE_OK", 16, check_exact("PIPELINE_OK")),
        Case("easy_math", "easy", "What is 17 * 23? Reply with only the number.", 32, check_math_391()),
        Case(
            "easy_json",
            "easy",
            'Output only valid JSON, no markdown: {"status": "ok", "n": 1}',
            64,
            check_json_status_ok(),
        ),
        Case(
            "medium_reverse",
            "medium",
            "Write a one-line Python function reverse_string(s) that reverses a string.",
            128,
            check_reverse_fn(),
        ),
        Case(
            "medium_413",
            "medium",
            "In one sentence: what does HTTP status 413 mean for an API client?",
            96,
            check_http_413(),
        ),
        Case(
            "medium_bug",
            "medium",
            "This function is wrong: def add(a, b): return a - b. One sentence: what is the fix?",
            96,
            check_subtraction_bug(),
        ),
        Case(
            "hard_bsearch",
            "hard",
            "Give 5-line pseudocode for iterative binary search on a sorted array.",
            256,
            check_binary_search(),
        ),
        Case(
            "hard_regex",
            "hard",
            "Give a Python regex pattern that matches a simple email (user@domain.tld). One line only.",
            128,
            check_regex(r"@[\w.-]+\.\w+|[@\\.]"),
        ),
        Case(
            "hard_logic",
            "hard",
            "Logic: All A are B. Some B are C. Can we conclude some A are C? Answer yes or no, one sentence why.",
            128,
            check_syllogism_no(),
        ),
        Case(
            "expert_refactor",
            "expert",
            "Refactor mentally: given async def fetch(ids): return [await get(i) for i in ids], "
            "name the concurrency problem and the standard fix in under 40 words.",
            192,
            check_regex(r"sequential|serial|gather|asyncio\.gather|parallel|concurrent", re.I),
        ),
    ]
    if not quick:
        cases.append(
            Case(
                "expert_complexity",
                "expert",
                "What is the time complexity of merge sort? Give best, average, worst, and space in O() notation only.",
                128,
                check_regex(r"O\(n\s*log\s*n\).*O\(n\)", re.I | re.S),
            ),
        )
    return cases


AUTO_CASES = [
    Case(
        "auto_simple",
        "easy",
        "Say hi in 3 words.",
        24,
        check_regex(r"\b(hi|hello|hey)\b", re.I),
        expect_tier="fast",
    ),
    Case(
        "auto_tools_heavy",
        "hard",
        "Debug integration test plan: list installed models, read a file, run tests. "
        "Reply with bullet list of exactly 3 MCP tool names you would call.",
        256,
        check_regex(r"list_models|read_file|run_tests|glob_files", re.I),
        expect_tier="quality",
    ),
]


def run_one(
    client: httpx.Client,
    base: str,
    case: Case,
    *,
    model: str,
    tier_header: str | None,
) -> Result:
    url = f"{base}/chat/completions"
    headers = {"Content-Type": "application/json"}
    if tier_header:
        headers["X-AIDEN-Model-Tier"] = tier_header
    body: dict[str, Any] = {
        "model": model,
        "messages": [{"role": "user", "content": case.prompt}],
        "max_tokens": case.max_tokens,
        "stream": False,
        "temperature": 0.2,
        "enable_thinking": False,
        "chat_template_kwargs": {"enable_thinking": False},
    }
    t0 = time.perf_counter()
    err: str | None = None
    status = 0
    text = ""
    hdr: dict[str, str] = {}
    try:
        r = client.post(url, json=body, headers=headers)
        status = r.status_code
        hdr = {k.lower(): v for k, v in r.headers.items()}
        if r.is_success:
            data = r.json()
            text = extract_assistant_text(data)
        else:
            err = r.text[:500]
    except Exception as exc:
        err = str(exc)
    latency = time.perf_counter() - t0
    if status == 200 and text:
        ok, why = case.check(text)
        detail = why
    elif status == 200:
        ok, detail = False, "empty content"
    else:
        ok, detail = False, err or f"HTTP {status}"
    route = hdr.get("x-aiden-model-tier") or tier_header or "?"
    return Result(
        case_id=case.id,
        difficulty=case.tier,
        route_tier=route,
        model_requested=model,
        model_selected=hdr.get("x-aiden-model-selected"),
        pipeline_injected=hdr.get("x-aiden-pipeline-injected"),
        prompt_tokens_est=hdr.get("x-aiden-prompt-tokens-est"),
        latency_s=round(latency, 2),
        status=status,
        pass_=ok,
        detail=detail,
        answer_snippet=(text or err or "")[:280],
        error=err if not ok and err else None,
    )


def summarize(results: list[Result]) -> dict[str, Any]:
    by_diff: dict[str, list[Result]] = {}
    for r in results:
        by_diff.setdefault(r.difficulty, []).append(r)
    out: dict[str, Any] = {"total": len(results), "passed": sum(1 for r in results if r.pass_), "by_difficulty": {}}
    for diff, rows in sorted(by_diff.items()):
        passed = sum(1 for r in rows if r.pass_)
        lat = [r.latency_s for r in rows if r.status == 200]
        out["by_difficulty"][diff] = {
            "passed": passed,
            "total": len(rows),
            "pct": round(100 * passed / len(rows), 1) if rows else 0,
            "latency_avg_s": round(sum(lat) / len(lat), 2) if lat else None,
            "latency_max_s": max(lat) if lat else None,
        }
    out["pct"] = round(100 * out["passed"] / out["total"], 1) if out["total"] else 0
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default=DEFAULT_BASE)
    ap.add_argument("--tier", choices=("fast", "quality", "both", "auto"), default="both")
    ap.add_argument("--quick", action="store_true", help="Skip one expert case")
    ap.add_argument("--timeout", type=float, default=180.0)
    ap.add_argument("--out", type=Path, default=ROOT / ".aiden" / "benchmark-report.json")
    args = ap.parse_args()

    cases = build_cases(args.quick)
    results: list[Result] = []
    print(f"Router: {args.base}")
    print(f"Quality: {QUALITY_MODEL}")
    print(f"Fast: {FAST_MODEL}\n")

    with httpx.Client(timeout=args.timeout) as client:
        tiers_to_run: list[tuple[str, str, str | None]] = []
        if args.tier in ("both", "fast"):
            tiers_to_run.append(("fast", FAST_MODEL, "fast"))
        if args.tier in ("both", "quality"):
            tiers_to_run.append(("quality", QUALITY_MODEL, "quality"))
        if args.tier == "auto":
            tiers_to_run.append(("auto", QUALITY_MODEL, None))

        for label, model, hdr in tiers_to_run:
            print(f"=== Tier: {label} (header={hdr!r}) ===")
            for case in cases:
                rid = f"{label}/{case.id}"
                r = run_one(client, args.base, case, model=model, tier_header=hdr)
                r.case_id = rid
                results.append(r)
                mark = "PASS" if r.pass_ else "FAIL"
                print(
                    f"  [{mark}] {rid} ({r.latency_s}s) tier={r.route_tier} model={r.model_selected} — {r.detail}"
                )
                if not r.pass_ and r.answer_snippet:
                    print(f"         snippet: {r.answer_snippet[:120]!r}")

        if args.tier in ("both", "auto"):
            print("=== Auto routing checks ===")
            for case in AUTO_CASES:
                # Empty model id lets router pick tier from prompt size/tools (not force 27B).
                auto_model = "" if case.expect_tier == "fast" else QUALITY_MODEL
                r = run_one(client, args.base, case, model=auto_model, tier_header=None)
                r.case_id = f"auto/{case.id}"
                results.append(r)
                route_ok = case.expect_tier is None or r.route_tier == case.expect_tier
                if case.expect_tier and r.route_tier != case.expect_tier:
                    r.pass_ = False
                    r.detail += f"; routed {r.route_tier} expected {case.expect_tier}"
                elif route_ok and not r.pass_:
                    pass
                elif route_ok:
                    r.pass_ = r.pass_
                mark = "PASS" if r.pass_ else "FAIL"
                print(f"  [{mark}] {r.case_id} route={r.route_tier} ({r.latency_s}s) — {r.detail}")

    summary = summarize(results)
    report = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "base": args.base,
        "models": {"quality": QUALITY_MODEL, "fast": FAST_MODEL},
        "summary": summary,
        "results": [asdict(r) for r in results],
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"\n=== Summary: {summary['passed']}/{summary['total']} ({summary['pct']}%) ===")
    for diff, stats in summary.get("by_difficulty", {}).items():
        print(f"  {diff}: {stats['passed']}/{stats['total']} ({stats['pct']}%) avg={stats['latency_avg_s']}s")
    print(f"\nReport: {args.out}")
    return 0 if summary["passed"] == summary["total"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
