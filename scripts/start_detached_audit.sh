#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
HOST_ID="$(hostname -s)"
STAMP="${AUDIT_STAMP:-$(date -u +%Y%m%dT%H%M%SZ)}"
OUT_DIR="${1:-$ROOT/reports/audits/$STAMP}"
PIDFILE="${DETACHED_AUDIT_PIDFILE:-$ROOT/logs/detached_audit.$HOST_ID.pid}"
LOGFILE="${DETACHED_AUDIT_LOGFILE:-$ROOT/logs/detached_audit.$HOST_ID.log}"
OUTFILE="${DETACHED_AUDIT_OUTFILE:-$ROOT/logs/detached_audit.$HOST_ID.outdir}"

mkdir -p "$ROOT/logs" "$OUT_DIR"

if [[ -s "$PIDFILE" ]]; then
    PID="$(cat "$PIDFILE")"
    if kill -0 "$PID" 2>/dev/null; then
        echo "Detached audit already running: pid=$PID"
        echo "Run scripts/status_detached_audit.sh for progress."
        exit 1
    fi
fi

: > "$LOGFILE"
nohup setsid "$ROOT/scripts/audit_all.sh" "$OUT_DIR" > "$LOGFILE" 2>&1 < /dev/null &
PID=$!
echo "$PID" > "$PIDFILE"
echo "$OUT_DIR" > "$OUTFILE"

echo "Started detached audit: pid=$PID"
echo "Output: $OUT_DIR"
echo "Live log: $LOGFILE"
echo "Progress: scripts/status_detached_audit.sh"
