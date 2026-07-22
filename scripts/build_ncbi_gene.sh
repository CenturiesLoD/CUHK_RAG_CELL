#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON="${PYTHON:-$ROOT/qwen_env/bin/python}"

cd "$ROOT"
"$PYTHON" src/build_ncbi_gene_corpus.py
