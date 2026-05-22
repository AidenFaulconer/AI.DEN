# Model benchmark results

Run locally:

```powershell
python scripts/benchmark-model-eval.py --quick          # fast + quality tiers
python scripts/benchmark-model-eval.py --tier auto      # routing checks only
```

Report written to `.aiden/benchmark-report.json`.

## Latest run (RTX 3050 Ti 4GB, MTP, `PROMPT_PIPELINE=caveman`)

| Tier | Pass rate | Notes |
|------|-----------|--------|
| **9B fast** | 8/10 (80%) | ~6–42s per case; failed hard bsearch/logic (scoring), not empty replies |
| **27B quality** | 9/10 (90%) | ~15–55s per case |
| **Auto routing** | 1/2 | Earlier failure: benchmark sent explicit 27B `model` (forces quality). Use empty `model` for auto “hi” tests. |

### Root cause fixed during this run

Qwen3 models put tokens in `reasoning_content` when **thinking** is on, leaving `content` empty. Fixes:

1. Router injects `chat_template_kwargs.enable_thinking=false` on chat bodies (`LLAMACPP_ENABLE_THINKING=0`).
2. Benchmark + MCP chat send the same flags.
3. Do not POST JSON with a UTF-8 BOM (breaks router `cjson.decode` → no patch).

### Tuning recommendations

| Issue | Suggestion |
|-------|------------|
| Auto routes “hi” to 27B | Set `proxy/prompt-pipeline.json` to `["caveman"]` only, or raise `AIDEN_FAST_MAX_PROMPT_TOKENS` (e.g. 4096) |
| Slow prefill (~15–25s on easy) | Expected on 4GB + 27B; use **fast** tier or 9B model for chat |
| `hard_bsearch` false negative | Pseudocode used `length` not `low`/`high` — benchmark scorer updated |
| Tok/s below 80 | 4GB VRAM + CPU offload; 9B fast tier is closer for small prompts |

### Logs to watch

```powershell
docker logs model-router --tail 50
docker logs llamacpp --tail 30
docker logs llamacpp-fast --tail 30
```

Look for: `aiden: patched thinking off` (router), OOM/`exit 137`, `predicted_per_second` in completion `timings`.
