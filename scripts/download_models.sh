#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON="${PYTHON:-$ROOT/qwen_env/bin/python}"

cd "$ROOT"
mkdir -p models

download_snapshot() {
  local repo_id="$1"
  local local_dir="$2"
  echo "== Download $repo_id -> $local_dir =="
  "$PYTHON" - "$repo_id" "$local_dir" <<'PY'
import os
import sys
from huggingface_hub import snapshot_download

repo_id = sys.argv[1]
local_dir = sys.argv[2]
token = os.environ.get("HF_TOKEN") or None
snapshot_download(
    repo_id=repo_id,
    local_dir=local_dir,
    local_dir_use_symlinks=False,
    token=token,
)
PY
}

download_snapshot "${LLM_HF_REPO_ID:-Qwen/Qwen3-32B}" "${LLM_MODEL_SOURCE_PATH:-models/Qwen3-32B}"
download_snapshot "${RAG_EMBEDDING_HF_REPO_ID:-Qwen/Qwen3-Embedding-8B}" "${RAG_MODEL_PATH:-models/Qwen3-Embedding-8B}"
download_snapshot "${RAG_RERANKER_HF_REPO_ID:-cross-encoder/ms-marco-MiniLM-L6-v2}" "${RAG_RERANKER_MODEL_PATH:-models/ms-marco-MiniLM-L-6-v2}"

case "${DOWNLOAD_OPTIONAL_BGE_RERANKER:-0}" in
  1|true|TRUE|yes|YES|on|ON)
    download_snapshot "BAAI/bge-reranker-base" "models/bge-reranker-base"
    ;;
esac

echo "Model download step complete."

