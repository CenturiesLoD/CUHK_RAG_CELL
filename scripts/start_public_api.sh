#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
HOST_ID="$(hostname -s)"
PYTHON="${PYTHON:-$ROOT/qwen_env/bin/python}"
HOST="${PUBLIC_API_HOST:-127.0.0.1}"
PORT="${PUBLIC_API_PORT:-8020}"
PIDFILE="${PUBLIC_API_PIDFILE:-$ROOT/logs/public_api_server.$HOST_ID.pid}"
LOGFILE="${PUBLIC_API_LOGFILE:-$ROOT/logs/public_api_server.$HOST_ID.log}"

mkdir -p "$ROOT/logs"

if [[ -f "$PIDFILE" ]]; then
  PID="$(cat "$PIDFILE" || true)"
  if [[ -n "$PID" ]] && kill -0 "$PID" 2>/dev/null; then
    echo "Public API server already running: pid=$PID url=http://$HOST:$PORT"
    exit 0
  fi
  rm -f "$PIDFILE"
fi

cd "$ROOT"
export PYTHONPATH="$ROOT/src${PYTHONPATH:+:$PYTHONPATH}"

nohup setsid "$PYTHON" -m uvicorn public_api_server:app --host "$HOST" --port "$PORT" >> "$LOGFILE" 2>&1 < /dev/null &
PID=$!
echo "$PID" > "$PIDFILE"

echo "Started public API server: pid=$PID url=http://$HOST:$PORT"
echo "Log: $LOGFILE"

for _ in $(seq 1 90); do
  if ! kill -0 "$PID" 2>/dev/null; then
    echo "Public API server exited before becoming healthy. Recent log:"
    tail -80 "$LOGFILE" || true
    exit 1
  fi

  if curl -fsS "http://$HOST:$PORT/health" >/dev/null 2>&1; then
    echo "Public API server is healthy."
    exit 0
  fi

  sleep 1
done

echo "Public API server is still starting. Check $LOGFILE for progress."
