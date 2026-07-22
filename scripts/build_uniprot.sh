#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON="${PYTHON:-$ROOT/qwen_env/bin/python}"

cd "$ROOT"
"$PYTHON" src/build_uniprot_corpus.py \
  --raw-out raw/uniprot_human_reviewed.tsv \
  --records-out processed/uniprot_human_reviewed_records.jsonl \
  --aliases-out processed/uniprot_human_reviewed_aliases.jsonl \
  --chunks-out chunks/uniprot_human_reviewed_chunks.jsonl \
  --report-out processed/uniprot_human_reviewed_report.json
