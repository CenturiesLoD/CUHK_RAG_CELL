#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

scripts/write_public_endpoint_manifest.sh

if ! git diff --quiet -- docs/current_endpoint.json; then
    git add docs/current_endpoint.json
    git commit -m "Update hosted API endpoint"
else
    echo "Endpoint manifest already matches the current URL."
fi

if [[ "${PUBLISH_ENDPOINT_PUSH:-0}" == "1" ]]; then
    git push origin HEAD
else
    echo "Not pushed. Set PUBLISH_ENDPOINT_PUSH=1 to push after committing."
fi
