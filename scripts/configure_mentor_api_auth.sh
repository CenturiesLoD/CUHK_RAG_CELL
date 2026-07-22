#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="${MENTOR_ENV_FILE:-$ROOT/.env}"
SECRETS_DIR="${MENTOR_SECRETS_DIR:-$ROOT/secrets}"
KEY_FILE="${MENTOR_API_KEY_FILE:-$SECRETS_DIR/mentor_api_key.txt}"
PYTHON="${PYTHON:-$ROOT/qwen_env/bin/python}"

mkdir -p "$SECRETS_DIR"
chmod 700 "$SECRETS_DIR"

if [[ ! -s "$KEY_FILE" ]]; then
    "$PYTHON" - <<'PY' > "$KEY_FILE"
import secrets
print("cell-rag-" + secrets.token_urlsafe(32))
PY
    chmod 600 "$KEY_FILE"
fi

"$PYTHON" - "$ENV_FILE" "$KEY_FILE" <<'PY'
from pathlib import Path
import sys

env_path = Path(sys.argv[1])
key_path = Path(sys.argv[2])
key = key_path.read_text(encoding="utf-8").strip()

updates = {
    "MENTOR_API_KEY": key,
    "MENTOR_API_HOST": "127.0.0.1",
    "MENTOR_API_PORT": "8020",
    "MENTOR_RAG_BASE_URL": "http://127.0.0.1:8010",
}

lines = []
seen = set()
if env_path.exists():
    lines = env_path.read_text(encoding="utf-8").splitlines()

output = []
for line in lines:
    stripped = line.strip()
    if not stripped or stripped.startswith("#") or "=" not in line:
        output.append(line)
        continue
    key_name = line.split("=", 1)[0].strip()
    if key_name in updates:
        output.append(f"{key_name}={updates[key_name]}")
        seen.add(key_name)
    else:
        output.append(line)

for key_name, value in updates.items():
    if key_name not in seen:
        output.append(f"{key_name}={value}")

env_path.write_text("\n".join(output).rstrip() + "\n", encoding="utf-8")
PY

echo "Mentor API auth configured."
echo "API key file: $KEY_FILE"
echo "Restart mentor API after changing auth config."
