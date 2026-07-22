#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

LLM_HOST="${LLM_HOST:-127.0.0.1}"
LLM_PORT="${LLM_PORT:-8000}"
RAG_HOST="${RAG_HOST:-127.0.0.1}"
RAG_PORT="${RAG_PORT:-8010}"
PUBLIC_API_HOST="${PUBLIC_API_HOST:-127.0.0.1}"
PUBLIC_API_PORT="${PUBLIC_API_PORT:-8020}"

LLM_WAIT_SECONDS="${ENSURE_LLM_WAIT_SECONDS:-1500}"
RAG_WAIT_SECONDS="${ENSURE_RAG_WAIT_SECONDS:-300}"
PUBLIC_API_WAIT_SECONDS="${ENSURE_PUBLIC_API_WAIT_SECONDS:-120}"
POLL_SECONDS="${ENSURE_POLL_SECONDS:-5}"

LLM_HEALTH_URL="http://$LLM_HOST:$LLM_PORT/v1/models"
RAG_HEALTH_URL="http://$RAG_HOST:$RAG_PORT/health"
PUBLIC_API_HEALTH_URL="http://$PUBLIC_API_HOST:$PUBLIC_API_PORT/health"

health_ok() {
    curl -fsS "$1" >/dev/null 2>&1
}

wait_for_url() {
    local name="$1"
    local url="$2"
    local wait_seconds="$3"
    local elapsed=0

    while (( elapsed <= wait_seconds )); do
        if health_ok "$url"; then
            echo "$name is healthy."
            return 0
        fi
        if (( elapsed > 0 && elapsed % 60 == 0 )); then
            echo "Still waiting for $name... elapsed=${elapsed}s url=$url"
        fi
        sleep "$POLL_SECONDS"
        elapsed=$((elapsed + POLL_SECONDS))
    done

    echo "$name did not become healthy within ${wait_seconds}s: $url"
    return 1
}

ensure_service() {
    local name="$1"
    local health_url="$2"
    local start_script="$3"
    local stop_script="$4"
    local wait_seconds="$5"
    local restart_unhealthy="${6:-true}"

    echo
    echo "== Ensure $name =="

    if health_ok "$health_url"; then
        echo "$name already healthy: $health_url"
        return 0
    fi

    echo "$name is not healthy yet. Checking whether it is already starting..."
    if "$start_script"; then
        if wait_for_url "$name" "$health_url" "$wait_seconds"; then
            return 0
        fi
    fi

    if [[ "$restart_unhealthy" != "true" ]]; then
        echo "$name is still unavailable and restart_unhealthy=false."
        return 1
    fi

    echo "$name is still unavailable. Restarting this service once..."
    "$stop_script" || true
    "$start_script"
    wait_for_url "$name" "$health_url" "$wait_seconds"
}

echo "Cell RAG universal stack ensure"
echo "project_root: $ROOT"
echo "started_utc: $(date -u +%Y-%m-%dT%H:%M:%SZ)"

ensure_service "LLM server" "$LLM_HEALTH_URL" "$ROOT/scripts/start_llm_server.sh" "$ROOT/scripts/stop_llm_server.sh" "$LLM_WAIT_SECONDS" true
ensure_service "RAG server" "$RAG_HEALTH_URL" "$ROOT/scripts/start_rag_server.sh" "$ROOT/scripts/stop_rag_server.sh" "$RAG_WAIT_SECONDS" true
ensure_service "Public API server" "$PUBLIC_API_HEALTH_URL" "$ROOT/scripts/start_public_api.sh" "$ROOT/scripts/stop_public_api.sh" "$PUBLIC_API_WAIT_SECONDS" true

echo
echo "== Final status =="
"$ROOT/scripts/status_all.sh"

echo
echo "Stack ready."
echo "Public API URL on server: http://$PUBLIC_API_HOST:$PUBLIC_API_PORT/docs"
