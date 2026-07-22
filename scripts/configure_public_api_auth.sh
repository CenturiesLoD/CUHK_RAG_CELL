#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="${PUBLIC_ENV_FILE:-$ROOT/.env}"
SECRETS_DIR="${PUBLIC_SECRETS_DIR:-$ROOT/secrets}"
KEY_FILE="${PUBLIC_API_KEY_FILE:-$SECRETS_DIR/public_api_key.txt}"

mkdir -p "$SECRETS_DIR"
chmod 700 "$SECRETS_DIR" 2>/dev/null || true

if [[ ! -s "$KEY_FILE" ]]; then
    "$ROOT/qwen_env/bin/python" - <<'PY' > "$KEY_FILE"
import secrets
print(secrets.token_urlsafe(32))
PY
    chmod 600 "$KEY_FILE" 2>/dev/null || true
fi

KEY="$(cat "$KEY_FILE")"

touch "$ENV_FILE"
"$ROOT/qwen_env/bin/python" - "$ENV_FILE" "$KEY" <<'PY'
from pathlib import Path
import sys

env_path = Path(sys.argv[1])
api_key = sys.argv[2]
updates = {
    "PUBLIC_API_KEY": api_key,
    "PUBLIC_API_HOST": "127.0.0.1",
    "PUBLIC_API_PORT": "8020",
    "PUBLIC_RAG_BASE_URL": "http://127.0.0.1:8010",
}

lines = env_path.read_text(encoding="utf-8").splitlines() if env_path.exists() else []
seen = set()
out = []
for line in lines:
    stripped = line.strip()
    if not stripped or stripped.startswith("#") or "=" not in line:
        out.append(line)
        continue
    key, _ = line.split("=", 1)
    key = key.strip()
    if key in updates:
        out.append(f"{key}={updates[key]}")
        seen.add(key)
    else:
        out.append(line)

for key, value in updates.items():
    if key not in seen:
        out.append(f"{key}={value}")

env_path.write_text("\n".join(out) + "\n", encoding="utf-8")
PY

echo "Public API auth configured."
echo "Key file: $KEY_FILE"
echo "Restart public API after changing auth config."
