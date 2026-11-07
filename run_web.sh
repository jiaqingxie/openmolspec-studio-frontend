#!/usr/bin/env bash
set -euo pipefail
GALLERY="$(cd "$(dirname "$0")" && pwd)"
export OPENMOLSPEC_ROOT="${OPENMOLSPEC_ROOT:-/mnt/shared-storage-user/xiejiaqing/openmolspec-studio-portable}"
PYTHON="${PYTHON:-/mnt/shared-storage-user/luxinyu/openmolspec-studio-portable/.venv/bin/python}"
VENDOR="$GALLERY/vendor"
if [ ! -f "$VENDOR/fastapi/__init__.py" ] || [ ! -f "$VENDOR/uvicorn/__init__.py" ]; then
  "$PYTHON" -m pip install --quiet --target "$VENDOR" fastapi uvicorn
fi
export PYTHONPATH="$VENDOR${PYTHONPATH:+:$PYTHONPATH}"
export HOME="$GALLERY/.home"
mkdir -p "$HOME"
cd "$GALLERY"
exec "$PYTHON" -m uvicorn server:app --host 127.0.0.1 --port "${PORT:-8501}"
