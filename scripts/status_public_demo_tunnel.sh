#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
HOST_ID="$(hostname -s)"
PIDFILE="${PUBLIC_DEMO_TUNNEL_PIDFILE:-$ROOT/logs/public_demo_tunnel.$HOST_ID.pid}"
URLFILE="${PUBLIC_DEMO_TUNNEL_URLFILE:-$ROOT/logs/public_demo_tunnel.$HOST_ID.url}"
SKIP_HEALTH="${PUBLIC_DEMO_SKIP_HEALTH:-0}"
STATUS=0

if [[ -f "$PIDFILE" ]]; then
    PID="$(cat "$PIDFILE" || true)"
    if [[ -n "$PID" ]] && kill -0 "$PID" 2>/dev/null; then
        echo "Process: running pid=$PID"
    else
        echo "Process: stale PID file"
        STATUS=1
    fi
else
    echo "Process: no PID file"
    STATUS=1
fi

if [[ -s "$URLFILE" ]]; then
    URL="$(cat "$URLFILE")"
    echo "URL: $URL"
    if [[ "$SKIP_HEALTH" == "1" ]]; then
        echo "Health: external check skipped"
    elif curl -fsS "$URL/health"; then
        echo
        echo "Health: ok"
    else
        echo "Health: unavailable"
        STATUS=1
    fi
else
    echo "URL: unavailable"
    STATUS=1
fi

exit "$STATUS"
