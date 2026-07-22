#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON="${PYTHON:-$ROOT/qwen_env/bin/python}"

cd "$ROOT"
"$PYTHON" src/build_hgnc_corpus.py \
  --source-url "${HGNC_SOURCE_URL:-https://storage.googleapis.com/public-download-files/hgnc/json/json/hgnc_complete_set.json}" \
  --raw-out raw/hgnc_complete_set.json \
  --genes-out processed/hgnc_genes.jsonl \
  --aliases-out processed/hgnc_aliases.jsonl \
  --chunks-out chunks/hgnc_chunks.jsonl \
  --report-out processed/hgnc_report.json
