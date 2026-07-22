#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON="${PYTHON:-$ROOT/qwen_env/bin/python}"

cd "$ROOT"
"$PYTHON" src/build_cellxgene_census_top_celltypes.py \
  --census-version "${CELLXGENE_CENSUS_VERSION:-2025-11-17}" \
  --organism homo_sapiens \
  --max-cell-types "${CELLXGENE_MAX_CELL_TYPES:-200}" \
  --top-n-per-cell-type "${CELLXGENE_TOP_N_PER_CELL_TYPE:-5}" \
  --min-unique-cells "${CELLXGENE_MIN_UNIQUE_CELLS:-1000}" \
  --raw-out raw/cellxgene_census_human_primary_top_groups.parquet \
  --processed-out processed/cellxgene_census_human_primary_counts.jsonl \
  --aliases-out processed/cellxgene_census_human_primary_aliases.jsonl \
  --chunks-out chunks/cellxgene_census_human_primary_chunks.jsonl \
  --report-out processed/cellxgene_census_human_primary_report.json
