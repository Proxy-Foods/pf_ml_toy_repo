#!/usr/bin/env bash
# One-shot environment setup: creates a .venv, installs dependencies,
# and creates a local .env from .env.example if one doesn't exist yet.
#
# Usage:
#   ./setup.sh
#   source .venv/bin/activate   # then activate it in your current shell

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$REPO_ROOT"

if [ ! -d ".venv" ]; then
    echo "Creating virtual environment in .venv/ ..."
    python3 -m venv .venv
else
    echo ".venv already exists, skipping creation."
fi

echo "Installing dependencies..."
"./.venv/bin/pip" install --upgrade pip -q
"./.venv/bin/pip" install -r requirements.txt -q

if [ ! -f ".env" ]; then
    echo "Creating .env from .env.example (fill in your real Azure values)..."
    cp .env.example .env
else
    echo ".env already exists, leaving it alone."
fi

echo ""
echo "Done. Next steps:"
echo "  source .venv/bin/activate"
echo "  \$EDITOR .env               # fill in AZURE_OPENAI_* values"
echo "  pytest                    # run unit tests (no Azure creds needed)"
echo "  jupyter notebook notebooks/recipe_generator.ipynb"
