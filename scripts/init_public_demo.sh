#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

RESTART_TUNNEL=0
PUBLISH_ENDPOINT=0
PRINT_API_KEY=0

usage() {
    cat <<'EOF'
Usage: scripts/init_public_demo.sh [options]

Start or repair the CCI-hosted public demo backend.

Options:
  --restart-tunnel    Stop the current quick tunnel first, forcing a fresh URL.
  --publish-endpoint  Commit and push docs/current_endpoint.json after URL update.
  --print-api-key     Print the public API key to stdout. Use only for private handoff.
  -h, --help          Show this help.

Default behavior reuses the existing tunnel if it is still running.
EOF
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --restart-tunnel)
            RESTART_TUNNEL=1
            shift
            ;;
        --publish-endpoint)
            PUBLISH_ENDPOINT=1
            shift
            ;;
        --print-api-key)
            PRINT_API_KEY=1
            shift
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            echo "Unknown option: $1" >&2
            usage >&2
            exit 2
            ;;
    esac
done

if [[ "$RESTART_TUNNEL" == "1" ]]; then
    echo "== Restart public tunnel =="
    scripts/stop_public_demo_tunnel.sh || true
    echo
fi

echo "== Initialize hosted demo =="
scripts/ensure_hosted_demo.sh

echo
echo "== Update endpoint manifest =="
scripts/write_public_endpoint_manifest.sh

if [[ "$PUBLISH_ENDPOINT" == "1" ]]; then
    echo
    echo "== Publish endpoint manifest =="
    PUBLISH_ENDPOINT_PUSH=1 scripts/publish_public_endpoint.sh
fi

HOST_ID="$(hostname -s)"
URLFILE="${PUBLIC_DEMO_TUNNEL_URLFILE:-$ROOT/logs/public_demo_tunnel.$HOST_ID.url}"
KEYFILE="${PUBLIC_API_KEY_FILE:-$ROOT/secrets/public_api_key.txt}"
URL="$(cat "$URLFILE" | tr -d '[:space:]')"

echo
echo "== Ready =="
echo "Public API URL: $URL"
echo "Endpoint manifest: docs/current_endpoint.json"
echo "API key file: $KEYFILE"
echo
echo "Client smoke test:"
echo "  export CELL_RAG_DEMO_API_KEY=\"<api-key>\""
echo "  python examples/smoke_hosted_demo.py"

if [[ "$PRINT_API_KEY" == "1" ]]; then
    echo
    echo "Public API key:"
    cat "$KEYFILE"
    echo
fi
