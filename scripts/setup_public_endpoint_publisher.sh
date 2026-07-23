#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
KEYFILE="${PUBLIC_ENDPOINT_DEPLOY_KEY:-$ROOT/secrets/github_deploy_key}"
REPO_URL="${PUBLIC_ENDPOINT_REPO_URL:-ssh://git@ssh.github.com:443/CenturiesLoD/CUHK_RAG_CELL.git}"
REPO_BRANCH="${PUBLIC_ENDPOINT_REPO_BRANCH:-main}"
REPO_DIR="${PUBLIC_ENDPOINT_REPO_DIR:-$ROOT/.endpoint_repo}"

if ! command -v ssh-keygen >/dev/null 2>&1; then
    echo "ssh-keygen is required to create a deploy key." >&2
    exit 1
fi

mkdir -p "$(dirname "$KEYFILE")"

if [[ ! -f "$KEYFILE" ]]; then
    ssh-keygen -t ed25519 -N "" -C "cell-rag-cci-endpoint-publisher" -f "$KEYFILE" >/dev/null
    chmod 600 "$KEYFILE"
fi

cat <<EOF
GitHub endpoint publisher key is ready.

Public key to add to GitHub as a repo deploy key with write access:

$(cat "$KEYFILE.pub")

GitHub location:
  CenturiesLoD/CUHK_RAG_CELL -> Settings -> Deploy keys -> Add deploy key

Required checkbox:
  Allow write access

After the deploy key is added, test publishing with:
  PUBLIC_ENDPOINT_REPO_URL="$REPO_URL" \\
  PUBLIC_ENDPOINT_REPO_BRANCH="$REPO_BRANCH" \\
  PUBLIC_ENDPOINT_REPO_DIR="$REPO_DIR" \\
  PUBLIC_ENDPOINT_DEPLOY_KEY="$KEYFILE" \\
  PUBLISH_ENDPOINT_PUSH=1 scripts/publish_public_endpoint.sh

After that, restarting the hosted demo can publish automatically with:
  scripts/init_public_demo.sh --restart-tunnel --publish-endpoint
EOF
