#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

MODEL_PATH="${LLM_MODEL_PATH:-$ROOT/models/Qwen3-32B}"
READ_MIB="${READ_MIB:-1024}"
PYTHON="${PYTHON:-$ROOT/qwen_env/bin/python}"

echo "== Model Path =="
echo "model_path: $MODEL_PATH"
if [[ -e "$MODEL_PATH" ]]; then
  echo "resolved: $(readlink -f "$MODEL_PATH")"
  du -sh "$MODEL_PATH" || true
  find "$MODEL_PATH" -maxdepth 1 -type f | wc -l | awk '{print "files: " $1}'
else
  echo "missing: $MODEL_PATH"
  exit 1
fi

echo
echo "== Filesystems =="
for path in "$MODEL_PATH" "$ROOT" /data /tmp /dev/shm /scratch /local_scratch /mnt/localssd; do
  if [[ -e "$path" ]]; then
    echo "-- $path --"
    df -hT "$path" || true
    findmnt -T "$path" -o TARGET,SOURCE,FSTYPE,OPTIONS 2>/dev/null || true
  fi
done

echo
echo "== Block Devices =="
lsblk -o NAME,TYPE,SIZE,MODEL,ROTA,FSTYPE,MOUNTPOINTS 2>/dev/null || true

echo
echo "== Sample Read Benchmark =="
SHARD="$(find "$MODEL_PATH" -maxdepth 1 -type f -name '*.safetensors' | sort | head -n 1 || true)"
if [[ -z "$SHARD" ]]; then
  echo "No safetensors shard found under $MODEL_PATH."
  exit 0
fi

echo "sample_file: $SHARD"
echo "requested_read_mib: $READ_MIB"
"$PYTHON" - "$SHARD" "$READ_MIB" <<'PY'
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

path = Path(sys.argv[1])
target_mib = int(sys.argv[2])
target_bytes = target_mib * 1024 * 1024
block_size = 64 * 1024 * 1024

read_bytes = 0
started = time.perf_counter()
with path.open("rb", buffering=0) as handle:
    while read_bytes < target_bytes:
        chunk = handle.read(min(block_size, target_bytes - read_bytes))
        if not chunk:
            break
        read_bytes += len(chunk)
elapsed = time.perf_counter() - started
mib = read_bytes / 1024 / 1024
rate = mib / elapsed if elapsed > 0 else 0.0
print(f"read_mib: {mib:.1f}")
print(f"elapsed_seconds: {elapsed:.3f}")
print(f"throughput_mib_per_sec: {rate:.1f}")
print("note: this is cache-sensitive; repeat readings can be faster due to OS page cache.")
PY
