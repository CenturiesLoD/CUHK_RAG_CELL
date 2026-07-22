#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 1 ]]; then
  echo "Usage: scripts/build_extra_jsonl_corpus.sh PATH_TO_DOCS_JSONL"
  exit 2
fi

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON="${PYTHON:-$ROOT/qwen_env/bin/python}"
INPUT="$1"
NAME="${EXTRA_CORPUS_NAME:-extra}"

cd "$ROOT"

"$PYTHON" src/build_jsonl_corpus.py \
  --input "$INPUT" \
  --chunks-out "chunks/${NAME}_chunks.jsonl" \
  --aliases-out "processed/${NAME}_aliases.jsonl" \
  --source-id "$NAME"

cat chunks/cl_chunks.jsonl "chunks/${NAME}_chunks.jsonl" > "chunks/rag_chunks.jsonl"
cat processed/cl_aliases.jsonl "processed/${NAME}_aliases.jsonl" > "processed/rag_aliases.jsonl"

"$PYTHON" src/embed_qwen_chunks.py \
  --chunks chunks/rag_chunks.jsonl \
  --model models/Qwen3-Embedding-8B \
  --out-dir embeddings \
  --name rag_qwen3_embedding_8b

echo "Built expanded corpus:"
echo "  RAG_CHUNKS_PATH=chunks/rag_chunks.jsonl"
echo "  RAG_ALIASES_PATH=processed/rag_aliases.jsonl"
echo "  RAG_EMBEDDINGS_PATH=embeddings/rag_qwen3_embedding_8b.npz"
echo "  RAG_METADATA_PATH=embeddings/rag_qwen3_embedding_8b.metadata.json"
