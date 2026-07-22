#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
HOST_ID="$(hostname -s)"
GPU_COUNT="$(nvidia-smi -L 2>/dev/null | wc -l | tr -d ' ')"
if [[ "${GPU_COUNT:-0}" -ge 2 ]]; then
  DEFAULT_CUDA_VISIBLE_DEVICES="1"
else
  DEFAULT_CUDA_VISIBLE_DEVICES="0"
fi
PYTHON="${PYTHON:-$ROOT/qwen_env/bin/python}"
HOST="${RAG_HOST:-127.0.0.1}"
PORT="${RAG_PORT:-8010}"
CUDA_DEVICES="${RAG_CUDA_VISIBLE_DEVICES:-${CUDA_VISIBLE_DEVICES:-$DEFAULT_CUDA_VISIBLE_DEVICES}}"
PIDFILE="${RAG_PIDFILE:-$ROOT/logs/rag_search_server.$HOST_ID.pid}"
LOGFILE="${RAG_LOGFILE:-$ROOT/logs/rag_search_server.$HOST_ID.log}"

mkdir -p "$ROOT/logs"

if [[ -f "$PIDFILE" ]]; then
  PID="$(cat "$PIDFILE" || true)"
  if [[ -n "$PID" ]] && kill -0 "$PID" 2>/dev/null; then
    echo "Cell RAG server already running: pid=$PID url=http://$HOST:$PORT"
    exit 0
  fi
  rm -f "$PIDFILE"
fi

cd "$ROOT"
export PYTHONPATH="$ROOT/src${PYTHONPATH:+:$PYTHONPATH}"
export CUDA_VISIBLE_DEVICES="$CUDA_DEVICES"

# Run in a new session so the server is not tied to the SSH session that starts it.
nohup setsid "$PYTHON" -m uvicorn rag_search_server:app --host "$HOST" --port "$PORT" >> "$LOGFILE" 2>&1 < /dev/null &
PID=$!
echo "$PID" > "$PIDFILE"

echo "Started Cell RAG server: pid=$PID url=http://$HOST:$PORT cuda_visible_devices=$CUDA_VISIBLE_DEVICES"
echo "Log: $LOGFILE"

for _ in $(seq 1 180); do
  if ! kill -0 "$PID" 2>/dev/null; then
    echo "Cell RAG server exited before becoming healthy. Recent log:"
    tail -80 "$LOGFILE" || true
    exit 1
  fi

  if curl -fsS "http://$HOST:$PORT/health" >/dev/null 2>&1; then
    echo "Cell RAG server is healthy."
    exit 0
  fi

  sleep 1
done

echo "Cell RAG server is still starting. Check $LOGFILE for progress."
