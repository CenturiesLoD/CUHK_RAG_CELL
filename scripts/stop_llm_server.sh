#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
HOST_ID="$(hostname -s)"
PIDFILE="${LLM_PIDFILE:-$ROOT/logs/llm_server.$HOST_ID.pid}"

if [[ ! -f "$PIDFILE" ]]; then
  echo "No LLM PID file found."
  exit 0
fi

PID="$(cat "$PIDFILE" || true)"
if [[ -z "$PID" ]] || ! kill -0 "$PID" 2>/dev/null; then
  rm -f "$PIDFILE"
  echo "Removed stale LLM PID file."
  exit 0
fi

kill "$PID"
for _ in $(seq 1 60); do
  if ! kill -0 "$PID" 2>/dev/null; then
    rm -f "$PIDFILE"
    echo "Stopped LLM server: pid=$PID"
    exit 0
  fi
  sleep 1
done

echo "LLM server did not stop within 60 seconds: pid=$PID"
exit 1
