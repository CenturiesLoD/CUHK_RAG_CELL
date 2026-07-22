#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
HOST_ID="$(hostname -s)"
PIDFILE="${RAG_PIDFILE:-$ROOT/logs/rag_search_server.$HOST_ID.pid}"

if [[ ! -f "$PIDFILE" ]]; then
  echo "No Cell RAG PID file found."
  exit 0
fi

PID="$(cat "$PIDFILE" || true)"
if [[ -z "$PID" ]] || ! kill -0 "$PID" 2>/dev/null; then
  rm -f "$PIDFILE"
  echo "Removed stale Cell RAG PID file."
  exit 0
fi

kill "$PID"
for _ in $(seq 1 30); do
  if ! kill -0 "$PID" 2>/dev/null; then
    rm -f "$PIDFILE"
    echo "Stopped Cell RAG server: pid=$PID"
    exit 0
  fi
  sleep 1
done

echo "Cell RAG server did not stop within 30 seconds: pid=$PID"
exit 1
