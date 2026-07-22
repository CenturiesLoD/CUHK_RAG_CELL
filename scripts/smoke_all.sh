#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

echo "== start stack =="
scripts/start_all.sh

echo
echo "== stack status =="
scripts/status_all.sh

echo
echo "== source registry validation =="
scripts/validate_source_registry.sh

echo
echo "== source report =="
scripts/report_sources.sh

echo
echo "== retrieval eval: main =="
scripts/run_retrieval_eval.sh

echo
echo "== retrieval eval: cellxgene =="
scripts/run_retrieval_eval.sh --cases eval/cellxgene_queries.jsonl

echo
echo "== answer eval: main =="
scripts/run_answer_eval.sh

echo
echo "== answer eval: cellxgene =="
scripts/run_answer_eval.sh --cases eval/cellxgene_answer_cases.jsonl

echo
echo "== final stack status =="
scripts/status_all.sh
