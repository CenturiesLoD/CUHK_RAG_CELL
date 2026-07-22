#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
HOST_ID="$(hostname -s)"

if [[ -f "$ROOT/.env" ]]; then
  set -a
  # shellcheck source=/dev/null
  source "$ROOT/.env"
  set +a
fi

GPU_COUNT="$(nvidia-smi -L 2>/dev/null | wc -l | tr -d ' ')"
DEFAULT_CUDA_VISIBLE_DEVICES="0"
if [[ "${GPU_COUNT:-0}" -ge 2 ]]; then
  DEFAULT_MAX_MODEL_LEN="4096"
  DEFAULT_GPU_MEMORY_UTILIZATION="0.90"
else
  DEFAULT_MAX_MODEL_LEN="2048"
  DEFAULT_GPU_MEMORY_UTILIZATION="0.80"
fi
PYTHON="${PYTHON:-$ROOT/vllm_env/bin/python}"
MODEL_SOURCE_PATH="${LLM_MODEL_SOURCE_PATH:-$ROOT/models/Qwen3-32B}"
MODEL_PATH="${LLM_MODEL_PATH:-$MODEL_SOURCE_PATH}"
FAST_MODEL_CACHE_ENABLED="${LLM_FAST_MODEL_CACHE_ENABLED:-false}"
FAST_MODEL_CACHE_PATH="${LLM_FAST_MODEL_CACHE_PATH:-}"
SERVED_MODEL_NAME="${LLM_SERVED_MODEL_NAME:-qwen3-32b}"
HOST="${LLM_HOST:-127.0.0.1}"
PORT="${LLM_PORT:-8000}"
CUDA_DEVICES="${LLM_CUDA_VISIBLE_DEVICES:-${CUDA_VISIBLE_DEVICES:-$DEFAULT_CUDA_VISIBLE_DEVICES}}"
PIDFILE="${LLM_PIDFILE:-$ROOT/logs/llm_server.$HOST_ID.pid}"
LOGFILE="${LLM_LOGFILE:-$ROOT/logs/llm_server.$HOST_ID.log}"
MAX_MODEL_LEN="${LLM_MAX_MODEL_LEN:-$DEFAULT_MAX_MODEL_LEN}"
GPU_MEMORY_UTILIZATION="${LLM_GPU_MEMORY_UTILIZATION:-$DEFAULT_GPU_MEMORY_UTILIZATION}"
MAX_NUM_SEQS="${LLM_MAX_NUM_SEQS:-1}"
CPU_OFFLOAD_GB="${LLM_CPU_OFFLOAD_GB:-0}"
SAFETENSORS_LOAD_STRATEGY="${LLM_SAFETENSORS_LOAD_STRATEGY:-prefetch}"
SAFETENSORS_PREFETCH_NUM_THREADS="${LLM_SAFETENSORS_PREFETCH_NUM_THREADS:-4}"
ENFORCE_EAGER="${LLM_ENFORCE_EAGER:-false}"

mkdir -p "$ROOT/logs"

case "${FAST_MODEL_CACHE_ENABLED,,}" in
  1|true|yes|on)
    if [[ -z "$FAST_MODEL_CACHE_PATH" ]]; then
      echo "LLM_FAST_MODEL_CACHE_ENABLED=true requires LLM_FAST_MODEL_CACHE_PATH."
      exit 1
    fi
    if [[ ! -f "$FAST_MODEL_CACHE_PATH/config.json" ]] || ! find "$FAST_MODEL_CACHE_PATH" -maxdepth 1 -type f -name '*.safetensors' | grep -q .; then
      echo "Fast model cache is missing or incomplete. Preparing: $FAST_MODEL_CACHE_PATH"
      LLM_MODEL_SOURCE_PATH="$MODEL_SOURCE_PATH" "$ROOT/scripts/prepare_fast_model_cache.sh" "$FAST_MODEL_CACHE_PATH"
    fi
    MODEL_PATH="$FAST_MODEL_CACHE_PATH"
    ;;
esac

if [[ -f "$PIDFILE" ]]; then
  PID="$(cat "$PIDFILE" || true)"
  if [[ -n "$PID" ]] && kill -0 "$PID" 2>/dev/null; then
    echo "LLM server already running: pid=$PID url=http://$HOST:$PORT/v1"
    exit 0
  fi
  rm -f "$PIDFILE"
fi

cd "$ROOT"
export CUDA_VISIBLE_DEVICES="$CUDA_DEVICES"

ARGS=(
  -m vllm.entrypoints.openai.api_server
  --model "$MODEL_PATH"
  --served-model-name "$SERVED_MODEL_NAME"
  --host "$HOST"
  --port "$PORT"
  --trust-remote-code
  --dtype bfloat16
  --max-model-len "$MAX_MODEL_LEN"
  --max-num-seqs "$MAX_NUM_SEQS"
  --gpu-memory-utilization "$GPU_MEMORY_UTILIZATION"
  --safetensors-load-strategy "$SAFETENSORS_LOAD_STRATEGY"
)

if [[ "$CPU_OFFLOAD_GB" != "0" ]]; then
  ARGS+=(--cpu-offload-gb "$CPU_OFFLOAD_GB")
fi

if [[ "$SAFETENSORS_LOAD_STRATEGY" == "prefetch" ]]; then
  ARGS+=(--safetensors-prefetch-num-threads "$SAFETENSORS_PREFETCH_NUM_THREADS")
fi

case "${ENFORCE_EAGER,,}" in
  1|true|yes|on)
    ARGS+=(--enforce-eager)
    ;;
esac

nohup setsid "$PYTHON" "${ARGS[@]}" >> "$LOGFILE" 2>&1 < /dev/null &
PID=$!
echo "$PID" > "$PIDFILE"

echo "Started LLM server: pid=$PID url=http://$HOST:$PORT/v1 model=$SERVED_MODEL_NAME cuda_visible_devices=$CUDA_VISIBLE_DEVICES max_model_len=$MAX_MODEL_LEN safetensors_load_strategy=$SAFETENSORS_LOAD_STRATEGY enforce_eager=$ENFORCE_EAGER"
echo "Log: $LOGFILE"

for _ in $(seq 1 900); do
  if ! kill -0 "$PID" 2>/dev/null; then
    echo "LLM server exited before becoming healthy. Recent log:"
    tail -120 "$LOGFILE" || true
    exit 1
  fi

  if curl -fsS "http://$HOST:$PORT/v1/models" >/dev/null 2>&1; then
    echo "LLM server is healthy."
    exit 0
  fi

  sleep 2
done

echo "LLM server is still starting. Check $LOGFILE for progress."
