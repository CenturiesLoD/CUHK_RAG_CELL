#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

OUT_DIR="${1:-reports/startup_ab/$(date -u +%Y%m%dT%H%M%SZ)}"
PYTHON="${PYTHON:-$ROOT/qwen_env/bin/python}"
HOST="${LLM_HOST:-127.0.0.1}"
PORT="${LLM_PORT:-8000}"
MODEL="${LLM_SERVED_MODEL_NAME:-qwen3-32b}"
HEALTH_URL="http://$HOST:$PORT/v1/models"
CHAT_URL="http://$HOST:$PORT/v1/chat/completions"

mkdir -p "$OUT_DIR"

RESULTS="$OUT_DIR/llm_startup_ab.tsv"
printf "case\tenforce_eager\tstartup_seconds\tfirst_completion_seconds\thealth_ok\tcompletion_ok\tlog\n" > "$RESULTS"

run_case() {
  local name="$1"
  local enforce_eager="$2"
  local log="$OUT_DIR/llm_${name}.log"
  local start_ms
  local end_ms
  local startup_seconds
  local completion_seconds
  local completion_ok="false"

  echo "== $name =="
  echo "Stopping existing LLM server..."
  scripts/stop_llm_server.sh || true
  sleep 8

  echo "Starting LLM server with LLM_ENFORCE_EAGER=$enforce_eager..."
  start_ms="$(date +%s%3N)"
  LLM_ENFORCE_EAGER="$enforce_eager" LLM_LOGFILE="$log" scripts/start_llm_server.sh
  end_ms="$(date +%s%3N)"
  startup_seconds="$("$PYTHON" -c 'import sys; print(round((int(sys.argv[2])-int(sys.argv[1]))/1000, 3))' "$start_ms" "$end_ms")"

  echo "Running first chat completion timing..."
  set +e
  completion_seconds="$(
    "$PYTHON" - "$CHAT_URL" "$MODEL" <<'PY'
import json
import sys
import time

import requests

url = sys.argv[1]
model = sys.argv[2]
payload = {
    "model": model,
    "messages": [{"role": "user", "content": "Answer in one sentence: what is a T cell?"}],
    "max_tokens": 48,
    "temperature": 0,
}
started = time.perf_counter()
response = requests.post(url, json=payload, timeout=300)
elapsed = time.perf_counter() - started
response.raise_for_status()
body = response.json()
content = body["choices"][0]["message"]["content"]
if not content.strip():
    raise SystemExit("empty completion")
print(round(elapsed, 3))
PY
  )"
  local completion_status=$?
  set -e

  if [[ "$completion_status" -eq 0 ]]; then
    completion_ok="true"
  else
    completion_seconds="NA"
  fi

  if curl -fsS "$HEALTH_URL" >/dev/null 2>&1; then
    printf "%s\t%s\t%s\t%s\ttrue\t%s\t%s\n" "$name" "$enforce_eager" "$startup_seconds" "$completion_seconds" "$completion_ok" "$log" >> "$RESULTS"
  else
    printf "%s\t%s\t%s\t%s\tfalse\t%s\t%s\n" "$name" "$enforce_eager" "$startup_seconds" "$completion_seconds" "$completion_ok" "$log" >> "$RESULTS"
  fi
}

run_case "cuda_graph_default_first" "false"
run_case "enforce_eager" "true"
run_case "cuda_graph_default_restored" "false"

echo
echo "Benchmark results:"
cat "$RESULTS"
echo
echo "Logs and results written to: $OUT_DIR"
echo "Default CUDA graph mode is running after benchmark."
