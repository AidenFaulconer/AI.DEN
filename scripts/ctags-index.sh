#!/bin/sh
# Background ctags indexer for AI.DEN workspace (runs in ctags-indexer container).
set -eu

WORKSPACE="${CTAGS_WORKSPACE:-/workspace}"
OUT="${CTAGS_OUTPUT:-.aiden/tags}"
INTERVAL="${CTAGS_INTERVAL_SEC:-300}"
CTAGS_BIN="${CTAGS_BIN:-ctags}"

cd "$WORKSPACE"
mkdir -p "$(dirname "$OUT")"

index_once() {
  echo "[ctags] indexing $(date -Iseconds 2>/dev/null || date) -> ${OUT}"
  # universal-ctags: fields + line numbers; skip huge/vendor trees
  "$CTAGS_BIN" -R \
    --fields=+nKz \
    --extras=+q \
    --exclude=.git \
    --exclude=node_modules \
    --exclude=.venv \
    --exclude=venv \
    --exclude=__pycache__ \
    --exclude=target \
    --exclude=dist \
    --exclude=build \
    --exclude=.next \
    --exclude=models \
    --exclude=.aiden-agent-sessions \
    --exclude=unsloth \
    --exclude=claw-code-local/rust/target \
    -f "$OUT" \
    . 2>/dev/null || {
    echo "[ctags] WARN: index run failed (non-fatal)" >&2
    return 0
  }
  if [ -f "$OUT" ]; then
    lines=$(wc -l <"$OUT" 2>/dev/null || echo 0)
    echo "[ctags] wrote ${lines} tags"
  fi
}

index_once
while true; do
  sleep "$INTERVAL"
  index_once
done
