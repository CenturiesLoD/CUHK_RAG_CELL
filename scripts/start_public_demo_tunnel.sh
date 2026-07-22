#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
HOST_ID="$(hostname -s)"
CLOUDFLARED="${CLOUDFLARED:-$ROOT/tools/cloudflared}"
MENTOR_API_BASE_URL="${MENTOR_API_BASE_URL:-http://127.0.0.1:8020}"
PIDFILE="${PUBLIC_DEMO_TUNNEL_PIDFILE:-$ROOT/logs/public_demo_tunnel.$HOST_ID.pid}"
LOGFILE="${PUBLIC_DEMO_TUNNEL_LOGFILE:-$ROOT/logs/public_demo_tunnel.$HOST_ID.log}"
URLFILE="${PUBLIC_DEMO_TUNNEL_URLFILE:-$ROOT/logs/public_demo_tunnel.$HOST_ID.url}"

mkdir -p "$ROOT/logs"

if [[ ! -x "$CLOUDFLARED" ]]; then
    echo "cloudflared not found at $CLOUDFLARED. Run scripts/install_cloudflared.sh first."
    exit 1
fi

if ! curl -fsS "$MENTOR_API_BASE_URL/health" >/dev/null 2>&1; then
    echo "Mentor API is not healthy at $MENTOR_API_BASE_URL/health. Run scripts/ensure_stack.sh first."
    exit 1
fi

if [[ -f "$PIDFILE" ]]; then
    PID="$(cat "$PIDFILE" || true)"
    if [[ -n "$PID" ]] && kill -0 "$PID" 2>/dev/null; then
        echo "Public demo tunnel already running: pid=$PID"
        if [[ -s "$URLFILE" ]]; then
            echo "URL: $(cat "$URLFILE")"
        fi
        exit 0
    fi
    rm -f "$PIDFILE"
fi

: > "$LOGFILE"
nohup setsid "$CLOUDFLARED" tunnel --url "$MENTOR_API_BASE_URL" --no-autoupdate >> "$LOGFILE" 2>&1 < /dev/null &
PID=$!
echo "$PID" > "$PIDFILE"

echo "Started public demo tunnel: pid=$PID"
echo "Log: $LOGFILE"

for _ in $(seq 1 90); do
    if ! kill -0 "$PID" 2>/dev/null; then
        echo "Public demo tunnel exited before URL became available. Recent log:"
        tail -80 "$LOGFILE" || true
        exit 1
    fi

    URL="$(grep -Eo 'https://[-a-zA-Z0-9.]+trycloudflare.com' "$LOGFILE" | tail -n 1 || true)"
    if [[ -n "$URL" ]]; then
        echo "$URL" > "$URLFILE"
        echo "Public demo URL: $URL"
        exit 0
    fi

    sleep 1
done

echo "Public demo tunnel is still starting. Check $LOGFILE for progress."
exit 1
