#!/usr/bin/env bash
set -euo pipefail

# Stops the full local RAG stack in reverse dependency order.
# 1) Public demo tunnel first, so no public requests reach the mentor API.
# 2) Mentor API second, so no demonstration requests reach the RAG server.
# 3) RAG server third, so no new answer requests reach the LLM.
# 4) LLM server fourth, freeing the large Qwen3-32B GPU allocation.

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo "Stopping public demo tunnel..."
if [[ -x "$ROOT/scripts/stop_public_demo_tunnel.sh" ]]; then
  "$ROOT/scripts/stop_public_demo_tunnel.sh" || PUBLIC_DEMO_TUNNEL_STOP_FAILED=1
else
  echo "stop_public_demo_tunnel.sh not installed."
fi

echo
echo "Stopping Mentor API server..."
"$ROOT/scripts/stop_mentor_api.sh" || MENTOR_API_STOP_FAILED=1

echo
echo "Stopping RAG server..."
"$ROOT/scripts/stop_rag_server.sh" || RAG_STOP_FAILED=1

echo
echo "Stopping local LLM server..."
"$ROOT/scripts/stop_llm_server.sh" || LLM_STOP_FAILED=1

echo
if [[ "${PUBLIC_DEMO_TUNNEL_STOP_FAILED:-0}" == "1" || "${MENTOR_API_STOP_FAILED:-0}" == "1" || "${RAG_STOP_FAILED:-0}" == "1" || "${LLM_STOP_FAILED:-0}" == "1" ]]; then
  echo "One or more services did not stop cleanly. Current status:"
  "$ROOT/scripts/status_all.sh" || true
  exit 1
fi

echo "Full stack stopped."
