#!/usr/bin/env bash
set -euo pipefail

# Shows one compact dashboard for the local RAG stack.
# - RAG: FastAPI retrieval/answer API on port 8010.
# - Public API: wrapper on port 8020.
# - Public demo tunnel: optional outbound tunnel for HTTPS access.
# - LLM: vLLM OpenAI-compatible Qwen3-32B server on port 8000.
# - GPU: current memory pressure, important because this stack is VRAM-tight.

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo "== Host =="
hostname
echo

echo "== RAG server =="
"$ROOT/scripts/status_rag_server.sh" || true

echo
echo "== Public API server =="
"$ROOT/scripts/status_public_api.sh" || true

echo
echo "== Public demo tunnel =="
if [[ -x "$ROOT/scripts/status_public_demo_tunnel.sh" ]]; then
  "$ROOT/scripts/status_public_demo_tunnel.sh" || true
else
  echo "status_public_demo_tunnel.sh not installed"
fi

echo
echo "== LLM server =="
"$ROOT/scripts/status_llm_server.sh" || true

echo
echo "== GPU =="
if command -v nvidia-smi >/dev/null 2>&1; then
  nvidia-smi --query-gpu=name,memory.used,memory.total,utilization.gpu,temperature.gpu,power.draw --format=csv,noheader
else
  echo "nvidia-smi not found"
fi

echo
echo "== Stack processes =="
ps -ef | grep -E 'rag_search_server|public_api_server|cloudflared|vllm.entrypoints.openai.api_server|uvicorn rag_search_server|uvicorn public_api_server' | grep -v grep || echo "No stack processes found."
