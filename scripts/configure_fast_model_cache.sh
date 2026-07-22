#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="${CELL_RAG_ENV_FILE:-$ROOT/.env}"
PYTHON="${PYTHON:-$ROOT/qwen_env/bin/python}"
MODEL_SOURCE_PATH="${LLM_MODEL_SOURCE_PATH:-$ROOT/models/Qwen3-32B}"
FAST_MODEL_CACHE_PATH="${1:-${LLM_FAST_MODEL_CACHE_PATH:-/dev/shm/cell_rag_models/Qwen3-32B}}"

"$PYTHON" - "$ENV_FILE" "$MODEL_SOURCE_PATH" "$FAST_MODEL_CACHE_PATH" <<'PY'
from __future__ import annotations

import sys
from pathlib import Path

env_path = Path(sys.argv[1])
model_source_path = sys.argv[2]
fast_model_cache_path = sys.argv[3]

updates = {
    "LLM_MODEL_SOURCE_PATH": model_source_path,
    "LLM_FAST_MODEL_CACHE_ENABLED": "true",
    "LLM_FAST_MODEL_CACHE_PATH": fast_model_cache_path,
}

lines = env_path.read_text(encoding="utf-8").splitlines() if env_path.exists() else []
seen: set[str] = set()
output: list[str] = []

for line in lines:
    stripped = line.strip()
    if not stripped or stripped.startswith("#") or "=" not in line:
        output.append(line)
        continue
    key = line.split("=", 1)[0].strip()
    if key in updates:
        output.append(f"{key}={updates[key]}")
        seen.add(key)
    else:
        output.append(line)

for key, value in updates.items():
    if key not in seen:
        output.append(f"{key}={value}")

env_path.write_text("\n".join(output).rstrip() + "\n", encoding="utf-8")
PY

echo "Fast model cache configuration written to $ENV_FILE"
echo "LLM_MODEL_SOURCE_PATH=$MODEL_SOURCE_PATH"
echo "LLM_FAST_MODEL_CACHE_ENABLED=true"
echo "LLM_FAST_MODEL_CACHE_PATH=$FAST_MODEL_CACHE_PATH"
echo
echo "Prepare the cache now with:"
echo "  scripts/prepare_fast_model_cache.sh \"$FAST_MODEL_CACHE_PATH\""
