#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON="${PYTHON:-$ROOT/qwen_env/bin/python}"
SOURCE_OBO="${CL_OBO_PATH:-}"
SOURCE_URL="${CL_OBO_URL:-http://purl.obolibrary.org/obo/cl.obo}"

cd "$ROOT"

if [[ -n "$SOURCE_OBO" ]]; then
  "$PYTHON" src/build_cell_ontology_corpus.py --obo "$SOURCE_OBO"
else
  "$PYTHON" src/build_cell_ontology_corpus.py --source-url "$SOURCE_URL"
fi

"$PYTHON" src/embed_qwen_chunks.py \
  --chunks chunks/cl_chunks.jsonl \
  --model models/Qwen3-Embedding-8B \
  --out-dir embeddings \
  --name cl_qwen3_embedding_8b

echo "Rebuilt Cell Ontology corpus and embeddings."
