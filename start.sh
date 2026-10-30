#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
export OPENMOLSPEC_ROOT="${OPENMOLSPEC_ROOT:-$ROOT}"
exec "$ROOT/.venv/bin/streamlit" run "$ROOT/app.py" "$@"
