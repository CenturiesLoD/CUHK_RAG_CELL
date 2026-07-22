#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
HOST_ID="$(hostname -s)"
PIDFILE="${PUBLIC_DEMO_TUNNEL_PIDFILE:-$ROOT/logs/public_demo_tunnel.$HOST_ID.pid}"
URLFILE="${PUBLIC_DEMO_TUNNEL_URLFILE:-$ROOT/logs/public_demo_tunnel.$HOST_ID.url}"

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

if [[ -s "$URLFILE" ]]; then
    URL="$(cat "$URLFILE")"
    echo "URL: $URL"
    if curl -fsS "$URL/health"; then
        echo
        echo "Health: ok"
    else
        echo "Health: unavailable"
    fi
else
    echo "URL: unavailable"
fi
