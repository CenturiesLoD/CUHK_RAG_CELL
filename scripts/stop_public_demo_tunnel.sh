#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
HOST_ID="$(hostname -s)"
PIDFILE="${PUBLIC_DEMO_TUNNEL_PIDFILE:-$ROOT/logs/public_demo_tunnel.$HOST_ID.pid}"
URLFILE="${PUBLIC_DEMO_TUNNEL_URLFILE:-$ROOT/logs/public_demo_tunnel.$HOST_ID.url}"

if [[ ! -f "$PIDFILE" ]]; then
    echo "No public demo tunnel PID file found."
    exit 0
fi

PID="$(cat "$PIDFILE" || true)"
if [[ -z "$PID" ]] || ! kill -0 "$PID" 2>/dev/null; then
    rm -f "$PIDFILE"
    echo "Removed stale public demo tunnel PID file."
    exit 0
fi

kill "$PID"
for _ in $(seq 1 30); do
    if ! kill -0 "$PID" 2>/dev/null; then
        rm -f "$PIDFILE"
        rm -f "$URLFILE"
        echo "Stopped public demo tunnel: pid=$PID"
        exit 0
    fi
    sleep 1
done

echo "Public demo tunnel did not stop within 30 seconds: pid=$PID"
exit 1
