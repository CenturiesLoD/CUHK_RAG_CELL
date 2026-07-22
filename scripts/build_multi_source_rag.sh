#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON="${PYTHON:-$ROOT/qwen_env/bin/python}"
MANIFEST="${1:-$ROOT/sources/ontology_sources.tsv}"

cd "$ROOT"

if [[ ! -f "$MANIFEST" ]]; then
  echo "Missing source manifest: $MANIFEST" >&2
  exit 2
fi

mkdir -p raw chunks processed embeddings

chunk_files=("chunks/cl_chunks.jsonl")
alias_files=("processed/cl_aliases.jsonl")

while IFS=$'\t' read -r source_id source_type source_url id_prefixes enabled; do
  [[ -z "${source_id:-}" || "$source_id" =~ ^# ]] && continue
  [[ "${enabled:-1}" == "0" ]] && continue

  echo "== Building $source_id from $source_url =="
  prefix_args=()
  IFS=',' read -ra prefixes <<< "${id_prefixes:-}"
  for prefix in "${prefixes[@]}"; do
    [[ -n "$prefix" ]] && prefix_args+=(--id-prefix "$prefix")
  done

  "$PYTHON" src/build_obo_corpus.py \
    --source-url "$source_url" \
    --raw-out "raw/${source_id}.obo" \
    --chunks-out "chunks/${source_id}_chunks.jsonl" \
    --terms-out "processed/${source_id}_terms.jsonl" \
    --aliases-out "processed/${source_id}_aliases.jsonl" \
    --source-id "$source_id" \
    --source-type "$source_type" \
    "${prefix_args[@]}"

  chunk_files+=("chunks/${source_id}_chunks.jsonl")
  alias_files+=("processed/${source_id}_aliases.jsonl")
done < "$MANIFEST"

cat "${chunk_files[@]}" > chunks/rag_chunks.jsonl
cat "${alias_files[@]}" > processed/rag_aliases.jsonl

"$PYTHON" src/embed_qwen_chunks.py \
  --chunks chunks/rag_chunks.jsonl \
  --model models/Qwen3-Embedding-8B \
  --out-dir embeddings \
  --name rag_qwen3_embedding_8b

echo "Built expanded multi-source corpus:"
echo "  RAG_CHUNKS_PATH=chunks/rag_chunks.jsonl"
echo "  RAG_ALIASES_PATH=processed/rag_aliases.jsonl"
echo "  RAG_EMBEDDINGS_PATH=embeddings/rag_qwen3_embedding_8b.npz"
echo "  RAG_METADATA_PATH=embeddings/rag_qwen3_embedding_8b.metadata.json"
