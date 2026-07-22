#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

SRC="${LLM_MODEL_SOURCE_PATH:-$ROOT/models/Qwen3-32B}"
DEST="${1:-${FAST_MODEL_PATH:-/tmp/cell_rag_models/Qwen3-32B}}"
SENTINEL=".cell_rag_fast_model_cache"

if [[ ! -d "$SRC" ]]; then
  echo "Source model directory does not exist: $SRC"
  exit 1
fi

DEST_PARENT="$(dirname "$DEST")"
mkdir -p "$DEST_PARENT"

SRC_BYTES="$(du -sb "$SRC" | awk '{print $1}')"
FREE_BYTES="$(df -PB1 "$DEST_PARENT" | awk 'NR == 2 {print $4}')"
NEEDED_BYTES="$(( SRC_BYTES + SRC_BYTES / 20 ))"

echo "source: $SRC"
echo "destination: $DEST"
echo "source_bytes: $SRC_BYTES"
echo "free_bytes_at_destination_parent: $FREE_BYTES"
echo "needed_bytes_with_5_percent_headroom: $NEEDED_BYTES"

if [[ "$FREE_BYTES" -lt "$NEEDED_BYTES" ]]; then
  echo "Not enough free space at $DEST_PARENT."
  exit 1
fi

if [[ -d "$DEST" && ! -f "$DEST/$SENTINEL" ]]; then
  if find "$DEST" -mindepth 1 -maxdepth 1 | read -r _; then
    echo "Destination exists and is not a Cell RAG cache directory: $DEST"
    echo "Refusing to overwrite it. Choose another destination."
    exit 1
  fi
fi

mkdir -p "$DEST"
touch "$DEST/$SENTINEL"

if command -v rsync >/dev/null 2>&1; then
  rsync -a --delete --exclude "$SENTINEL" "$SRC/" "$DEST/"
else
  cp -a "$SRC/." "$DEST/"
fi
touch "$DEST/$SENTINEL"

SRC_SHARDS="$(find "$SRC" -maxdepth 1 -type f -name '*.safetensors' | wc -l | tr -d ' ')"
DEST_SHARDS="$(find "$DEST" -maxdepth 1 -type f -name '*.safetensors' | wc -l | tr -d ' ')"

if [[ "$SRC_SHARDS" != "$DEST_SHARDS" ]]; then
  echo "Shard count mismatch: source=$SRC_SHARDS destination=$DEST_SHARDS"
  exit 1
fi

if [[ ! -f "$DEST/config.json" ]]; then
  echo "Copied directory is missing config.json: $DEST"
  exit 1
fi

echo
echo "Fast model cache is prepared."
echo "Use it for the next LLM start with:"
echo "  LLM_MODEL_PATH=\"$DEST\" scripts/start_llm_server.sh"
echo
echo "To make it persistent for this project, set this in .env:"
echo "  LLM_MODEL_PATH=$DEST"
