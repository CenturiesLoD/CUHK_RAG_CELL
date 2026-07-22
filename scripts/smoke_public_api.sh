#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

PYTHON="${PYTHON:-$ROOT/qwen_env/bin/python}"
HOST="${PUBLIC_API_HOST:-127.0.0.1}"
PORT="${PUBLIC_API_PORT:-8020}"
BASE_URL="${PUBLIC_API_BASE_URL:-http://$HOST:$PORT}"
KEY_FILE="${PUBLIC_API_KEY_FILE:-$ROOT/secrets/public_api_key.txt}"

export CELL_RAG_ROOT="$ROOT"
export PUBLIC_API_KEY_FILE="$KEY_FILE"

"$PYTHON" - <<'PY'
import json
import os
import sys
from pathlib import Path

import requests

root = Path(os.environ.get("CELL_RAG_ROOT", "."))
env_path = root / ".env"
if env_path.exists():
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))

base_url = os.environ.get("PUBLIC_API_BASE_URL") or (
    "http://"
    + os.environ.get("PUBLIC_API_HOST", "127.0.0.1")
    + ":"
    + os.environ.get("PUBLIC_API_PORT", "8020")
)
api_key = os.environ.get("PUBLIC_API_KEY", "").strip()
if not api_key:
    key_file = Path(os.environ.get("PUBLIC_API_KEY_FILE", ""))
    if key_file.exists():
        api_key = key_file.read_text(encoding="utf-8").strip()
headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}

health = requests.get(f"{base_url}/health", timeout=30)
health.raise_for_status()
examples = requests.get(f"{base_url}/examples", timeout=30)
examples.raise_for_status()

ask = requests.post(
    f"{base_url}/ask",
    headers=headers,
    json={"question": "What is a regulatory T cell?", "top_k": 3, "max_tokens": 180},
    timeout=300,
)
ask.raise_for_status()
answer = ask.json()

errors = []
if not answer.get("answer"):
    errors.append("missing answer")
if not answer.get("citation_check", {}).get("passed"):
    errors.append("citation_check did not pass")
if not answer.get("sources"):
    errors.append("missing sources")

summary = {
    "health": health.json(),
    "example_count": len(examples.json().get("examples", [])),
    "answer_preview": str(answer.get("answer", ""))[:220],
    "citation_check": answer.get("citation_check"),
    "source_ids": [source.get("doc_id") for source in answer.get("sources", [])],
    "errors": errors,
}
print(json.dumps(summary, ensure_ascii=False, indent=2))

if errors:
    sys.exit(1)
PY
