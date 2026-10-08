#!/usr/bin/env bash
# Rebuild src/whoami/backend/static/app.css with the Tailwind v4 standalone CLI (ADR 0002).
# The binary is downloaded once into .cache/tw/ (gitignored); override with TAILWIND_BIN.
set -euo pipefail
root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
bin="${TAILWIND_BIN:-$root/.cache/tw/tailwindcss}"
if [ ! -x "$bin" ]; then
  mkdir -p "$(dirname "$bin")"
  curl -sSfL -o "$bin" https://github.com/tailwindlabs/tailwindcss/releases/latest/download/tailwindcss-linux-x64
  chmod +x "$bin"
fi
static="$root/src/whoami/backend/static"
"$bin" -i "$static/src/app.css" -o "$static/app.css" --minify "$@"
