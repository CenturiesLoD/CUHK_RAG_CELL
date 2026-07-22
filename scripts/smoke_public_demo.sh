#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

PYTHON="${PYTHON:-$ROOT/qwen_env/bin/python}"
HOST_ID="$(hostname -s)"
URLFILE="${PUBLIC_DEMO_TUNNEL_URLFILE:-$ROOT/logs/public_demo_tunnel.$HOST_ID.url}"
KEY_FILE="${PUBLIC_API_KEY_FILE:-$ROOT/secrets/public_api_key.txt}"

if [[ ! -s "$URLFILE" ]]; then
    echo "Public demo URL file missing: $URLFILE"
    exit 1
fi

BASE_URL="$(cat "$URLFILE")"
API_KEY="${PUBLIC_API_KEY:-$(cat "$KEY_FILE" 2>/dev/null || true)}"

"$PYTHON" examples/smoke_hosted_demo.py \
    --base-url "$BASE_URL" \
    --api-key "$API_KEY" \
    --question "What is a regulatory T cell?"
