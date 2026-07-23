#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUNTIME_MANIFEST="${PUBLIC_ENDPOINT_RUNTIME_MANIFEST:-$ROOT/docs/current_endpoint.json}"
REPO_URL="${PUBLIC_ENDPOINT_REPO_URL:-ssh://git@ssh.github.com:443/CenturiesLoD/CUHK_RAG_CELL.git}"
REPO_BRANCH="${PUBLIC_ENDPOINT_REPO_BRANCH:-main}"
REPO_DIR="${PUBLIC_ENDPOINT_REPO_DIR:-$ROOT/.endpoint_repo}"
DEPLOY_KEY="${PUBLIC_ENDPOINT_DEPLOY_KEY:-$ROOT/secrets/github_deploy_key}"
GIT_USER_NAME="${PUBLIC_ENDPOINT_GIT_USER_NAME:-Cell RAG CCI}"
GIT_USER_EMAIL="${PUBLIC_ENDPOINT_GIT_USER_EMAIL:-cell-rag-cci@users.noreply.github.com}"

require_command() {
    if ! command -v "$1" >/dev/null 2>&1; then
        echo "Required command is missing: $1" >&2
        exit 1
    fi
}

require_command git
require_command cp

if [[ -z "${GIT_SSH_COMMAND:-}" && -f "$DEPLOY_KEY" ]]; then
    export GIT_SSH_COMMAND="ssh -i $DEPLOY_KEY -o IdentitiesOnly=yes -o StrictHostKeyChecking=accept-new"
fi

cd "$ROOT"
scripts/write_public_endpoint_manifest.sh

if [[ -e "$REPO_DIR" && ! -d "$REPO_DIR/.git" ]]; then
    echo "Endpoint repo path exists but is not a Git checkout: $REPO_DIR" >&2
    exit 1
fi

git config --global --add safe.directory "$REPO_DIR" >/dev/null 2>&1 || true

if [[ ! -d "$REPO_DIR/.git" ]]; then
    mkdir -p "$(dirname "$REPO_DIR")"
    git clone --depth=1 --branch "$REPO_BRANCH" "$REPO_URL" "$REPO_DIR"
    git config --global --add safe.directory "$REPO_DIR" >/dev/null 2>&1 || true
else
    git -C "$REPO_DIR" remote set-url origin "$REPO_URL"
    git -C "$REPO_DIR" fetch origin "$REPO_BRANCH"
    git -C "$REPO_DIR" checkout "$REPO_BRANCH"
    git -C "$REPO_DIR" pull --ff-only origin "$REPO_BRANCH"
fi

git -C "$REPO_DIR" config user.name "$GIT_USER_NAME"
git -C "$REPO_DIR" config user.email "$GIT_USER_EMAIL"

mkdir -p "$REPO_DIR/docs"
cp "$RUNTIME_MANIFEST" "$REPO_DIR/docs/current_endpoint.json"

if ! git -C "$REPO_DIR" diff --quiet -- docs/current_endpoint.json; then
    git -C "$REPO_DIR" add docs/current_endpoint.json
    git -C "$REPO_DIR" commit -m "Update hosted API endpoint"
else
    echo "Endpoint manifest already matches the current URL."
fi

if [[ "${PUBLISH_ENDPOINT_PUSH:-0}" == "1" ]]; then
    git -C "$REPO_DIR" push origin "$REPO_BRANCH"
else
    echo "Not pushed. Set PUBLISH_ENDPOINT_PUSH=1 to push after committing."
fi
