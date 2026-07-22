#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
HOST_ID="$(hostname -s)"
HOST="${RAG_HOST:-127.0.0.1}"
PORT="${RAG_PORT:-8010}"
PIDFILE="${RAG_PIDFILE:-$ROOT/logs/rag_search_server.$HOST_ID.pid}"

if [[ -f "$PIDFILE" ]]; then
  PID="$(cat "$PIDFILE" || true)"
  if [[ -n "$PID" ]] && kill -0 "$PID" 2>/dev/null; then
    echo "Process: running pid=$PID"
  else
    echo "Process: stale PID file"
  fi
else
  echo "Process: no PID file"
fi

if curl -fsS "http://$HOST:$PORT/health"; then
  echo
  echo "Health: ok"
else
  echo "Health: unavailable"
  exit 1
fi
