#!/bin/sh
# Build llama-server args from env (speculative decoding modes for AI.DEN).
set -e

MODEL="/models/${LLAMACPP_GGUF}"
if [ -z "$LLAMACPP_GGUF" ] || [ ! -f "$MODEL" ]; then
  echo "[llamacpp] ERROR: main model not found: $MODEL" >&2
  exit 1
fi

SPEC_MODE="${LLAMACPP_SPEC_MODE:-mtp}"
SPEC_N_MAX="${LLAMACPP_SPEC_DRAFT_N_MAX:-16}"
CTX="${LLAMACPP_CTX_SIZE:-16384}"
THREADS="${LLAMACPP_THREADS:-8}"
NGL="${LLAMACPP_NGL:--1}"
NGL_DRAFT="${LLAMACPP_DRAFT_NGL:--1}"

ARGS="-m $MODEL --host 0.0.0.0 --port 8080 --fit on -ngl $NGL --flash-attn on --jinja --ctx-size $CTX -t $THREADS -np 1"
ARGS="$ARGS --cache-type-k ${LLAMACPP_CACHE_K:-q8_0} --cache-type-v ${LLAMACPP_CACHE_V:-q8_0}"

case "$SPEC_MODE" in
  mtp)
    ARGS="$ARGS --spec-type draft-mtp --spec-draft-n-max ${LLAMACPP_SPEC_DRAFT_N_MAX:-3}"
    ;;
  draft|draft-model)
    if [ -z "${LLAMACPP_DRAFT_GGUF:-}" ]; then
      echo "[llamacpp] ERROR: set LLAMACPP_DRAFT_GGUF for draft mode" >&2
      exit 1
    fi
    DRAFT="/models/${LLAMACPP_DRAFT_GGUF}"
    if [ ! -f "$DRAFT" ]; then
      echo "[llamacpp] ERROR: draft model not found: $DRAFT" >&2
      exit 1
    fi
    ARGS="$ARGS --spec-draft-model $DRAFT --spec-draft-n-max $SPEC_N_MAX --spec-draft-ngl $NGL_DRAFT"
    if [ -n "${LLAMACPP_SPEC_DRAFT_CTX_SIZE:-}" ]; then
      ARGS="$ARGS --spec-draft-ctx-size $LLAMACPP_SPEC_DRAFT_CTX_SIZE"
    fi
    ;;
  draft+ngram|draft-ngram)
    if [ -z "${LLAMACPP_DRAFT_GGUF:-}" ]; then
      echo "[llamacpp] ERROR: set LLAMACPP_DRAFT_GGUF" >&2
      exit 1
    fi
    DRAFT="/models/${LLAMACPP_DRAFT_GGUF}"
    if [ ! -f "$DRAFT" ]; then
      echo "[llamacpp] ERROR: draft model not found: $DRAFT" >&2
      exit 1
    fi
    ARGS="$ARGS --spec-draft-model $DRAFT --spec-draft-n-max $SPEC_N_MAX --spec-draft-ngl $NGL_DRAFT"
    ARGS="$ARGS --spec-type ngram-simple --spec-ngram-simple-size-n ${LLAMACPP_NGRAM_SIZE_N:-12}"
    ARGS="$ARGS --spec-ngram-simple-size-m ${LLAMACPP_NGRAM_SIZE_M:-48}"
    ;;
  ngram|ngram-simple)
    ARGS="$ARGS --spec-type ngram-simple --spec-draft-n-max $SPEC_N_MAX"
    ARGS="$ARGS --spec-ngram-simple-size-n ${LLAMACPP_NGRAM_SIZE_N:-12}"
    ARGS="$ARGS --spec-ngram-simple-size-m ${LLAMACPP_NGRAM_SIZE_M:-48}"
    ;;
  none|off)
    ;;
  *)
    echo "[llamacpp] WARN: unknown LLAMACPP_SPEC_MODE=$SPEC_MODE, no speculative" >&2
    ;;
esac

echo "[llamacpp] mode=$SPEC_MODE model=$(basename "$MODEL")" >&2
if [ -n "${LLAMACPP_DRAFT_GGUF:-}" ]; then
  echo "[llamacpp] draft=$LLAMACPP_DRAFT_GGUF n_max=$SPEC_N_MAX" >&2
fi

# shellcheck disable=SC2086
exec /app/llama-server $ARGS
