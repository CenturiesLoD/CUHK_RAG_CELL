#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON_BIN="${PYTHON_BIN:-python3}"
QWEN_ENV="${QWEN_ENV:-$ROOT/qwen_env}"
VLLM_ENV="${VLLM_ENV:-$ROOT/vllm_env}"
VLLM_PACKAGE="${VLLM_PACKAGE:-vllm}"

cd "$ROOT"

echo "== System packages =="
bash scripts/ensure_system_packages.sh \
  ca-certificates \
  curl \
  git \
  openssh-client \
  procps \
  rsync \
  python3 \
  python3-venv

echo
echo "== Main RAG Python environment =="
if [[ ! -d "$QWEN_ENV" ]]; then
  "$PYTHON_BIN" -m venv "$QWEN_ENV"
fi
"$QWEN_ENV/bin/python" -m pip install --upgrade pip
"$QWEN_ENV/bin/python" -m pip install -r requirements.txt

echo
echo "== vLLM Python environment =="
if [[ ! -d "$VLLM_ENV" ]]; then
  "$PYTHON_BIN" -m venv "$VLLM_ENV"
fi
"$VLLM_ENV/bin/python" -m pip install --upgrade pip
"$VLLM_ENV/bin/python" -m pip install "$VLLM_PACKAGE"

echo
echo "== Directory skeleton =="
mkdir -p models sources raw processed chunks embeddings logs reports secrets

echo
echo "Bootstrap complete."
echo "Next:"
echo "  cp .env.example .env"
echo "  scripts/download_models.sh"
echo "  follow docs/FRESH_MACHINE_REBUILD.md"

