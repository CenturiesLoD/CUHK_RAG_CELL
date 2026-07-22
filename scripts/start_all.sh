#!/usr/bin/env bash
set -euo pipefail

# Starts or verifies the full local RAG stack.
# Delegates to ensure_stack.sh so healthy services are not restarted and stale
# PID files or half-started services are handled consistently.

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

exec "$ROOT/scripts/ensure_stack.sh"
