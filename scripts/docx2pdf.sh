#!/usr/bin/env bash
set -euo pipefail

# Usage:
#   ./docx-to-pdf.sh input.docx [output.pdf]
#
# Example:
#   ./docx-to-pdf.sh book1/what-scripture-says-vol1.docx
#   ./docx-to-pdf.sh book*/what-scripture-says-*.docx

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PY_SCRIPT="$SCRIPT_DIR/docx2pdf.py"

if [[ ! -f "$PY_SCRIPT" ]]; then
  echo "Error: Python script not found: $PY_SCRIPT" >&2
  exit 1
fi

if ! command -v py >/dev/null 2>&1; then
  echo "Error: 'py' launcher not found in PATH." >&2
  echo "Install Python for Windows and ensure the Python launcher is installed." >&2
  exit 1
fi

if [[ $# -lt 1 || $# -gt 2 ]]; then
  echo "Usage: $(basename "$0") input.docx [output.pdf]" >&2
  exit 1
fi

INPUT_DOCX="$1"
OUTPUT_PDF="${2:-}"

if [[ ! -f "$INPUT_DOCX" ]]; then
  echo "Error: Input file not found: $INPUT_DOCX" >&2
  exit 1
fi

echo "Checking for pywin32..."

if ! py -c "import pythoncom" >/dev/null 2>&1; then
  echo "pywin32 not found. Installing..."
  py -m pip install --upgrade pip
  py -m pip install pywin32
else
  echo "pywin32 already installed."
fi

# Some systems need COM registration after pywin32 install.
# This is harmless to attempt and non-fatal if unavailable.
echo "Running pywin32 post-install registration if available..."
py -c "import runpy; runpy.run_module('pywin32_postinstall', run_name='__main__')" -install >/dev/null 2>&1 || true

echo "Converting DOCX to PDF with Microsoft Word..."
if [[ -n "$OUTPUT_PDF" ]]; then
  py "$PY_SCRIPT" "$INPUT_DOCX" "$OUTPUT_PDF"
else
  py "$PY_SCRIPT" "$INPUT_DOCX"
fi
