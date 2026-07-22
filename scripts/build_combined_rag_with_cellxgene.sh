#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON="${PYTHON:-$ROOT/qwen_env/bin/python}"

cd "$ROOT"

chunk_files=(
  chunks/cl_chunks.jsonl
  chunks/uberon_anatomy_chunks.jsonl
  chunks/go_ontology_chunks.jsonl
  chunks/pato_quality_chunks.jsonl
  chunks/cellxgene_census_human_primary_chunks.jsonl
  chunks/hgnc_chunks.jsonl
  chunks/ncbi_gene_human_chunks.jsonl
  chunks/uniprot_human_reviewed_chunks.jsonl
  chunks/cellmarker3_chunks.jsonl
  chunks/panglaodb_chunks.jsonl
)

alias_files=(
  processed/cl_aliases.jsonl
  processed/uberon_anatomy_aliases.jsonl
  processed/go_ontology_aliases.jsonl
  processed/pato_quality_aliases.jsonl
  processed/cellxgene_census_human_primary_aliases.jsonl
  processed/hgnc_aliases.jsonl
  processed/ncbi_gene_human_aliases.jsonl
  processed/uniprot_human_reviewed_aliases.jsonl
  processed/cellmarker3_aliases.jsonl
  processed/panglaodb_aliases.jsonl
)

for file in "${chunk_files[@]}" "${alias_files[@]}"; do
  if [[ ! -f "$file" ]]; then
    echo "Missing required file: $file" >&2
    exit 2
  fi
done

cat "${chunk_files[@]}" > chunks/rag_chunks.jsonl
cat "${alias_files[@]}" > processed/rag_aliases.jsonl

"$PYTHON" src/embed_qwen_chunks.py \
  --chunks chunks/rag_chunks.jsonl \
  --model models/Qwen3-Embedding-8B \
  --out-dir embeddings \
  --name rag_qwen3_embedding_8b

echo "Built combined RAG corpus with CELLxGENE Census, HGNC, NCBI Gene, UniProt, CellMarker, and PanglaoDB:"
echo "  RAG_CHUNKS_PATH=chunks/rag_chunks.jsonl"
echo "  RAG_ALIASES_PATH=processed/rag_aliases.jsonl"
echo "  RAG_EMBEDDINGS_PATH=embeddings/rag_qwen3_embedding_8b.npz"
echo "  RAG_METADATA_PATH=embeddings/rag_qwen3_embedding_8b.metadata.json"
