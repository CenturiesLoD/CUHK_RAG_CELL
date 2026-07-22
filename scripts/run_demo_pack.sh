#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON="${PYTHON:-$ROOT/qwen_env/bin/python}"
STAMP="${DEMO_STAMP:-$(date -u +%Y%m%dT%H%M%SZ)}"
OUT_DIR="${1:-reports/demos/$STAMP}"

cd "$ROOT"
mkdir -p "$OUT_DIR"

echo "Demo output: $OUT_DIR"

echo "== start stack =="
scripts/start_all.sh > "$OUT_DIR/00_start_all.log" 2>&1

echo "== initial status =="
scripts/status_all.sh > "$OUT_DIR/01_status_initial.log" 2>&1

echo "== run showcase queries =="
"$PYTHON" src/run_demo_queries.py \
  --cases demo/showcase_queries.jsonl \
  --output-dir "$OUT_DIR" \
  > "$OUT_DIR/02_run_demo_queries.log" 2>&1

echo "== final status =="
scripts/status_all.sh > "$OUT_DIR/03_status_final.log" 2>&1

{
    echo "Demo pack complete."
    echo "output_dir: $OUT_DIR"
    echo
    cat "$OUT_DIR/summary.txt"
} | tee "$OUT_DIR/console_summary.txt"
