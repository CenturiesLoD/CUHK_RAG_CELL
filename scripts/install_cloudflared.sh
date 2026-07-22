#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CLOUDFLARED="${CLOUDFLARED:-$ROOT/tools/cloudflared}"
DOWNLOAD_URL="${CLOUDFLARED_DOWNLOAD_URL:-https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64}"

mkdir -p "$(dirname "$CLOUDFLARED")"

if [[ -x "$CLOUDFLARED" ]]; then
    "$CLOUDFLARED" --version
    exit 0
fi

TMP_PATH="$CLOUDFLARED.download"
curl -fsSL --retry 3 --retry-delay 2 "$DOWNLOAD_URL" -o "$TMP_PATH"
chmod +x "$TMP_PATH"
"$TMP_PATH" --version
mv "$TMP_PATH" "$CLOUDFLARED"
chmod +x "$CLOUDFLARED"

echo "Installed cloudflared at $CLOUDFLARED"
