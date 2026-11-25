#!/bin/sh
# First-run setup for NixNet Job Command. Never overwrites an existing
# config, profile, or data directory.
set -eu
ROOT="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
cd "$ROOT"

PY="${PYTHON:-python3}"
if ! "$PY" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 9) else 1)'; then
  echo "NixNet Job Command needs Python 3.9 or newer. Found: $($PY --version 2>&1)" >&2
  exit 1
fi
echo "Python: $($PY --version)"

if [ ! -f config.toml ] && [ ! -f config.json ]; then
  cp config.example.toml config.toml
  echo "Wrote config.toml from the example. Edit it before you go further if you want."
else
  echo "Keeping existing config."
fi

if [ ! -f profile.json ]; then
  cp profile.example.json profile.json
  echo "Wrote profile.json from the example. Replace it with your own facts before you apply anywhere."
else
  echo "Keeping existing profile.json."
fi

mkdir -p data/screenshots logs
if [ ! -f .env ] && [ -f .env.example ]; then
  # Do not copy secrets; just remind the user.
  echo "Optional integrations: copy .env.example to .env and fill only what you use."
fi

echo
echo "Next:"
echo "  make run          # serves http://127.0.0.1:8742"
echo "  make test         # boots a temp database and hits the API"
echo
echo "The first boot loads seed/example_seed.json (Acme Cloud and friends)"
echo "so you can click around immediately. Your real jobs stay in data/."
