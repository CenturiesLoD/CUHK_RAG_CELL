#!/usr/bin/env bash
set -euo pipefail

DEFAULT_PACKAGES=(
  ca-certificates
  curl
  git
  openssh-client
  procps
  rsync
)

PACKAGES=("$@")
if [[ "${#PACKAGES[@]}" -eq 0 ]]; then
  PACKAGES=("${DEFAULT_PACKAGES[@]}")
fi

AUTO_INSTALL="${CELL_RAG_AUTO_INSTALL_SYSTEM_PACKAGES:-1}"

missing=()
for package in "${PACKAGES[@]}"; do
  if ! dpkg-query -W -f='${Status}' "$package" 2>/dev/null | grep -q "install ok installed"; then
    missing+=("$package")
  fi
done

if [[ "${#missing[@]}" -eq 0 ]]; then
  echo "System package check: ok (${PACKAGES[*]})"
  exit 0
fi

echo "Missing system packages: ${missing[*]}"

case "$AUTO_INSTALL" in
  1|true|TRUE|yes|YES|on|ON)
    ;;
  *)
    cat >&2 <<EOF
Automatic system package installation is disabled.
Install manually, or rerun with:

  CELL_RAG_AUTO_INSTALL_SYSTEM_PACKAGES=1 scripts/init_public_demo.sh --publish-endpoint

Required packages:
  ${missing[*]}
EOF
    exit 1
    ;;
esac

if ! command -v apt-get >/dev/null 2>&1; then
  echo "apt-get is not available; cannot install: ${missing[*]}" >&2
  exit 1
fi

if [[ "$(id -u)" -ne 0 ]]; then
  echo "Root is required to install system packages with apt-get." >&2
  echo "Missing packages: ${missing[*]}" >&2
  exit 1
fi

export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y --no-install-recommends "${missing[@]}"

echo "Installed missing system packages: ${missing[*]}"
