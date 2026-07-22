#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

echo "== Ensure local RAG stack =="
scripts/ensure_stack.sh

echo
echo "== Configure mentor API auth =="
scripts/configure_mentor_api_auth.sh

echo
echo "== Restart mentor API to load auth config =="
scripts/stop_mentor_api.sh || true
scripts/start_mentor_api.sh

echo
echo "== Install public tunnel binary =="
scripts/install_cloudflared.sh

echo
echo "== Start public demo tunnel =="
scripts/start_public_demo_tunnel.sh

echo
echo "== Smoke-test public demo URL =="
mkdir -p reports/public_demo
if scripts/smoke_public_demo.sh > reports/public_demo/smoke_public_demo_latest.log; then
    echo "Public smoke test passed from this host."
else
    echo "Public smoke test did not pass from this host."
    echo "This can happen when the CCI host cannot resolve its own quick-tunnel URL."
    echo "Run examples/smoke_hosted_demo.py from an external client to verify public access."
fi
cat reports/public_demo/smoke_public_demo_latest.log

echo
echo "== Public demo status =="
scripts/status_public_demo_tunnel.sh

echo
echo "Hosted demo backend is ready."
