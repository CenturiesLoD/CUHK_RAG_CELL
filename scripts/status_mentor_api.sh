#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
HOST_ID="$(hostname -s)"
HOST="${MENTOR_API_HOST:-127.0.0.1}"
PORT="${MENTOR_API_PORT:-8020}"
PIDFILE="${MENTOR_API_PIDFILE:-$ROOT/logs/mentor_api_server.$HOST_ID.pid}"

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
fi
