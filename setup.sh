#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
python3 -m venv --system-site-packages "$ROOT/.venv"
"$ROOT/.venv/bin/python" -m pip install --no-build-isolation -e "$ROOT" -r "$ROOT/requirements.txt"
