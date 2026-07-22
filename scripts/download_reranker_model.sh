#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON="${PYTHON:-$ROOT/qwen_env/bin/python}"
MODEL_ID="${1:-cross-encoder/ms-marco-MiniLM-L-6-v2}"
OUT_DIR="${2:-models/ms-marco-MiniLM-L-6-v2}"

cd "$ROOT"
"$PYTHON" -c '
import sys
import time
from huggingface_hub import snapshot_download

repo_id = sys.argv[1]
local_dir = sys.argv[2]
retries = int(sys.argv[3]) if len(sys.argv) > 3 else 5

last_error = None
for attempt in range(1, retries + 1):
    try:
        snapshot_download(
            repo_id=repo_id,
            local_dir=local_dir,
            max_workers=1,
        )
        break
    except Exception as exc:
        last_error = exc
        print(f"download attempt {attempt}/{retries} failed: {exc}", file=sys.stderr, flush=True)
        if attempt < retries:
            time.sleep(min(30, attempt * 5))
else:
    raise SystemExit(f"download failed after {retries} attempts: {last_error}")
' "$MODEL_ID" "$OUT_DIR" "${RERANKER_DOWNLOAD_RETRIES:-5}"

echo "Downloaded reranker model:"
echo "  model_id: $MODEL_ID"
echo "  path: $OUT_DIR"
