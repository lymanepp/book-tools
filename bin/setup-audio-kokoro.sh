#!/usr/bin/env bash
# Install the optional local Kokoro proof-audio toolchain.
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
TOOLS_ROOT="$(cd -- "$SCRIPT_DIR/.." && pwd)"

# The released Kokoro 0.9.4 wheel on PyPI declares Python >=3.10,<3.13.
# Keep the proof-audio environment on Python 3.12 until a compatible release
# is published. The project devcontainer is pinned accordingly.
if ! python3 - <<'PYVER'
import sys
raise SystemExit(0 if (3, 10) <= sys.version_info[:2] < (3, 13) else 1)
PYVER
then
  echo "ERROR: Kokoro 0.9.4 requires Python 3.10-3.12; found $(python3 --version 2>&1)." >&2
  echo "       Use the project devcontainer pinned to Python 3.12-trixie." >&2
  exit 1
fi

as_root() {
  if [[ "${EUID:-$(id -u)}" -eq 0 ]]; then
    "$@"
  elif command -v sudo >/dev/null 2>&1; then
    sudo "$@"
  else
    echo "ERROR: Need root privileges to install OS packages: $*" >&2
    exit 1
  fi
}

if command -v apt-get >/dev/null 2>&1; then
  missing=()
  command -v espeak-ng >/dev/null 2>&1 || missing+=(espeak-ng)
  command -v ffmpeg >/dev/null 2>&1 || missing+=(ffmpeg)
  if ((${#missing[@]})); then
    as_root apt-get update -qq
    as_root apt-get install -y --no-install-recommends "${missing[@]}"
  fi
else
  command -v espeak-ng >/dev/null 2>&1 \
    || { echo "ERROR: espeak-ng is required and apt-get is unavailable." >&2; exit 1; }
  command -v ffmpeg >/dev/null 2>&1 \
    || { echo "ERROR: ffmpeg is required for M4A/MP3 output." >&2; exit 1; }
fi

pip_cmd=(python3 -m pip install --upgrade -r "$TOOLS_ROOT/requirements-audio-kokoro.txt")
if [[ -n "${VIRTUAL_ENV:-}" ]]; then
  "${pip_cmd[@]}"
elif python3 -m pip help install 2>/dev/null | grep -q -- '--break-system-packages'; then
  "${pip_cmd[@]}" --break-system-packages
else
  "${pip_cmd[@]}"
fi

python3 - <<'PY'
from kokoro import KPipeline
import soundfile
print("Kokoro proof-audio dependencies installed successfully.")
PY
