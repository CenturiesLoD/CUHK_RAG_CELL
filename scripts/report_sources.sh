#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON="${PYTHON:-$ROOT/qwen_env/bin/python}"

cd "$ROOT"
"$PYTHON" src/report_sources.py --registry sources/source_registry.json "$@"
