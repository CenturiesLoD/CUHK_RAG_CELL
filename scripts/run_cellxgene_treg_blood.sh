#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON="${PYTHON:-$ROOT/qwen_env/bin/python}"

cd "$ROOT"
"$PYTHON" src/build_cellxgene_census_corpus.py \
  --value-filter "is_primary_data == True and cell_type_ontology_term_id == 'CL:0000815' and tissue_ontology_term_id == 'UBERON:0000178'" \
  --raw-out raw/cellxgene_census_treg_blood.parquet \
  --processed-out processed/cellxgene_census_treg_blood_counts.jsonl \
  --aliases-out processed/cellxgene_census_treg_blood_aliases.jsonl \
  --chunks-out chunks/cellxgene_census_treg_blood_chunks.jsonl \
  --report-out processed/cellxgene_census_treg_blood_report.json
