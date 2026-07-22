#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
HOST_ID="$(hostname -s)"
PIDFILE="${DETACHED_AUDIT_PIDFILE:-$ROOT/logs/detached_audit.$HOST_ID.pid}"
LOGFILE="${DETACHED_AUDIT_LOGFILE:-$ROOT/logs/detached_audit.$HOST_ID.log}"
OUTFILE="${DETACHED_AUDIT_OUTFILE:-$ROOT/logs/detached_audit.$HOST_ID.outdir}"

if [[ ! -s "$OUTFILE" ]]; then
    echo "No detached audit state found for host $HOST_ID."
    exit 1
fi

OUT_DIR="$(cat "$OUTFILE")"
PID="$(cat "$PIDFILE" 2>/dev/null || true)"

echo "Output: $OUT_DIR"
RUNNING=0
if [[ -n "$PID" ]] && kill -0 "$PID" 2>/dev/null; then
    RUNNING=1
    echo "Status: running (pid=$PID)"
else
    echo "Status: finished"
fi

if [[ -s "$OUT_DIR/step_status.tsv" ]]; then
    echo
    echo "Step status:"
    column -t -s $'\t' "$OUT_DIR/step_status.tsv" 2>/dev/null || cat "$OUT_DIR/step_status.tsv"
fi

if [[ "$RUNNING" == "1" ]] && [[ -s "$LOGFILE" ]]; then
    echo
    CURRENT_STEP="$(awk '/ START / { step=$NF } END { print step }' "$OUT_DIR/summary.txt" 2>/dev/null || true)"
    CURRENT_LOG="$OUT_DIR/${CURRENT_STEP}.log"
    if [[ -n "$CURRENT_STEP" ]] && [[ -s "$CURRENT_LOG" ]]; then
        echo "Current step: $CURRENT_STEP"
        tail -30 "$CURRENT_LOG"
    else
        echo "Recent live log:"
        tail -30 "$LOGFILE"
    fi
elif [[ -s "$OUT_DIR/summary.txt" ]]; then
    echo
    echo "Summary:"
    tail -30 "$OUT_DIR/summary.txt"
elif [[ -s "$LOGFILE" ]]; then
    echo
    echo "Recent log:"
    tail -30 "$LOGFILE"
fi

if [[ -z "$PID" ]] || ! kill -0 "$PID" 2>/dev/null; then
    if [[ -s "$OUT_DIR/step_status.tsv" ]] && awk 'NR > 1 && $1 != 0 { failed=1 } END { exit failed ? 0 : 1 }' "$OUT_DIR/step_status.tsv"; then
        exit 1
    fi
fi
