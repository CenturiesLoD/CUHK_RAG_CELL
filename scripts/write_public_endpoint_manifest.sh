#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
HOST_ID="$(hostname -s)"
URLFILE="${PUBLIC_DEMO_TUNNEL_URLFILE:-$ROOT/logs/public_demo_tunnel.$HOST_ID.url}"
OUTFILE="${PUBLIC_ENDPOINT_MANIFEST_PATH:-$ROOT/docs/current_endpoint.json}"

if [[ ! -s "$URLFILE" ]]; then
    echo "Public demo URL file missing: $URLFILE" >&2
    exit 1
fi

URL="$(cat "$URLFILE" | tr -d '[:space:]')"
if [[ ! "$URL" =~ ^https://[-a-zA-Z0-9.]+trycloudflare.com$ ]]; then
    echo "Unexpected public demo URL: $URL" >&2
    exit 1
fi

UPDATED_AT="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
mkdir -p "$(dirname "$OUTFILE")"
cat > "$OUTFILE" <<JSON
{
  "base_url": "$URL",
  "status_url": "$URL/health",
  "updated_at_utc": "$UPDATED_AT",
  "backend": "CCI Cloudflare quick tunnel",
  "note": "This URL is discovered through this stable GitHub manifest. If the quick tunnel restarts, update this file with the new URL."
}
JSON

echo "Wrote endpoint manifest: $OUTFILE"
echo "Endpoint: $URL"
