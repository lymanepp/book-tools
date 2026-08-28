#!/usr/bin/env bash
# Fetch the exact modern EB Garamond family used by the print build.
#
# The legacy georgd "EB Garamond 12" files have incomplete/rough bold coverage.
# Pinning a complete Octavio Pardo build here makes the PDF independent of
# whatever EB Garamond happens to be installed on the host.
set -euo pipefail

ROOT="${1:-}"
if [[ -z "$ROOT" ]]; then
  SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
  ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
fi

FONT_REV="106a4a6d377987459ae5e68673a4570f13b957fb"
FONT_DIR="$ROOT/build/.fonts/eb-garamond-$FONT_REV"
FONT_BASE="https://raw.githubusercontent.com/octaviopardo/EBGaramond12/$FONT_REV/fonts/otf"
LICENSE_URL="https://raw.githubusercontent.com/octaviopardo/EBGaramond12/$FONT_REV/OFL.txt"

mkdir -p "$FONT_DIR"

fetch() {
  local url="$1"
  local dest="$2"
  local tmp

  [[ -s "$dest" ]] && return 0
  command -v curl >/dev/null 2>&1 || {
    echo "ERROR: curl is required to fetch the pinned EB Garamond print fonts." >&2
    exit 1
  }

  tmp="${dest}.tmp.$$"
  echo "Fetching $(basename "$dest") ..." >&2
  if ! curl --fail --location --silent --show-error \
      --retry 3 --retry-delay 1 \
      "$url" -o "$tmp"; then
    rm -f "$tmp"
    echo "ERROR: Could not fetch $url" >&2
    exit 1
  fi
  mv "$tmp" "$dest"
}

fetch "$FONT_BASE/EBGaramond-Regular.otf"    "$FONT_DIR/EBGaramond-Regular.otf"
fetch "$FONT_BASE/EBGaramond-Italic.otf"     "$FONT_DIR/EBGaramond-Italic.otf"
fetch "$FONT_BASE/EBGaramond-Bold.otf"       "$FONT_DIR/EBGaramond-Bold.otf"
fetch "$FONT_BASE/EBGaramond-BoldItalic.otf" "$FONT_DIR/EBGaramond-BoldItalic.otf"
fetch "$LICENSE_URL"                          "$FONT_DIR/OFL.txt"

printf '%s\n' "$FONT_DIR"
