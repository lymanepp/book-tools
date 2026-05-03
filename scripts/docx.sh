#!/usr/bin/env bash
# =============================================================================
# docx.sh — Build a DOCX for publisher submission.
#
# Run from the workspace root:
#   bash tools/scripts/docx.sh book1
#   bash tools/scripts/docx.sh book2
#
# Output: dist/<BOOK_OUTPUT_BASENAME>-submission.docx
#
# Required files in the book directory:
#   book.env
#   front-matter-submission.md
#   metadata-submission.yaml
#   NN-*.md  (chapter files — no YAML metadata blocks inside them)
#
# Required support files in tools/scripts/:
#   build-template.py
#   mdformat.lua
#
# =============================================================================
# book.env reference
# =============================================================================
#
# Required:
#   BOOK_TITLE               Display title
#   BOOK_SUBTITLE            Display subtitle
#   BOOK_OUTPUT_BASENAME     Stem for output filename
#
# Optional identity (substituted into front matter if present):
#   BOOK_AUTHOR              Default: Lyman Epp
#   BOOK_HARDCOVER_ISBN
#   BOOK_PAPERBACK_ISBN
#
# Typography — all optional; defaults shown:
#   BOOK_BODY_FONT           Body text font.           [Palatino Linotype]
#   BOOK_BODY_SIZE           Body text size in pt.     [11]
#   BOOK_BODY_ALIGN          justify | left            [justify]
#   BOOK_FIRST_LINE_INDENT   First-line indent inches. [0.25]
#   BOOK_LINE_SPACING        Line spacing multiplier.  [1.0]
#   BOOK_H1_SIZE             H1 size in pt.            [16]
#   BOOK_H2_SIZE             H2 size in pt.            [13]
#   BOOK_H3_SIZE             H3 size in pt.            [12]
#   BOOK_FOOTNOTE_SIZE       Footnote size in pt.      [9]
#   BOOK_TABLE_BODY_FONT     Table body cell font.     [Georgia]
#   BOOK_TABLE_BODY_SIZE     Table body cell size pt.  [9.9]
#   BOOK_TABLE_HEADER_FONT   Table header font.        [Arial]
#   BOOK_TABLE_HEADER_SIZE   Table header size pt.     [10]
#   BOOK_QUOTE_PRESET        scripture | clinical      [scripture]
#
# =============================================================================

set -euo pipefail

ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
cd "$ROOT"

BOOK="${1:-}"

if [[ -z "$BOOK" ]]; then
    echo "Usage: $0 book1|book2" >&2
    exit 1
fi

BOOK_NAME="${BOOK#./}"
BOOK_DIR="$ROOT/$BOOK_NAME"
SCRIPTS_DIR="$ROOT/tools/scripts"
DIST_DIR="$ROOT/dist"

TEMPLATE_BUILDER="$SCRIPTS_DIR/build-template.py"
TEMPLATE="$SCRIPTS_DIR/reference-template.docx"
MDFORMAT="$SCRIPTS_DIR/mdformat.lua"
BOOK_ENV="$BOOK_DIR/book.env"

# ── Validate inputs ───────────────────────────────────────────────────────────

[[ -d "$BOOK_DIR" ]] || { echo "ERROR: Missing book dir: $BOOK_DIR" >&2; exit 1; }

if [[ ! -f "$BOOK_ENV" ]]; then
    echo "ERROR: Missing $BOOK_ENV." >&2
    exit 1
fi

# shellcheck disable=SC1090
source "$BOOK_ENV"

for var in BOOK_TITLE BOOK_SUBTITLE BOOK_OUTPUT_BASENAME; do
    if [[ -z "${!var:-}" ]]; then
        echo "ERROR: $BOOK_ENV must define $var." >&2
        exit 1
    fi
done

for required in "$TEMPLATE_BUILDER" "$MDFORMAT"; do
    if [[ ! -f "$required" ]]; then
        echo "ERROR: Missing required file: $required" >&2
        exit 1
    fi
done

FRONT_MATTER="$BOOK_DIR/front-matter-submission.md"
METADATA="$BOOK_DIR/metadata-submission.yaml"

for required in "$FRONT_MATTER" "$METADATA"; do
    if [[ ! -f "$required" ]]; then
        echo "ERROR: Missing required file: $required" >&2
        exit 1
    fi
done

mkdir -p "$DIST_DIR"
OUTPUT="$DIST_DIR/${BOOK_OUTPUT_BASENAME}-submission.docx"

# ── Build reference template ──────────────────────────────────────────────────
# Rebuilt on every run so book.env typography changes are always reflected.
# Page geometry is not passed — submission uses build-template.py defaults.

echo "Building reference template..."

TEMPLATE_ARGS=()

[[ -n "${BOOK_BODY_FONT:-}"         ]] && TEMPLATE_ARGS+=(--body-font         "$BOOK_BODY_FONT")
[[ -n "${BOOK_BODY_SIZE:-}"         ]] && TEMPLATE_ARGS+=(--body-size         "$BOOK_BODY_SIZE")
[[ -n "${BOOK_BODY_ALIGN:-}"        ]] && TEMPLATE_ARGS+=(--body-align        "$BOOK_BODY_ALIGN")
[[ -n "${BOOK_FIRST_LINE_INDENT:-}" ]] && TEMPLATE_ARGS+=(--first-line-indent "$BOOK_FIRST_LINE_INDENT")
[[ -n "${BOOK_LINE_SPACING:-}"      ]] && TEMPLATE_ARGS+=(--line-spacing      "$BOOK_LINE_SPACING")
[[ -n "${BOOK_H1_SIZE:-}"           ]] && TEMPLATE_ARGS+=(--h1-size           "$BOOK_H1_SIZE")
[[ -n "${BOOK_H2_SIZE:-}"           ]] && TEMPLATE_ARGS+=(--h2-size           "$BOOK_H2_SIZE")
[[ -n "${BOOK_H3_SIZE:-}"           ]] && TEMPLATE_ARGS+=(--h3-size           "$BOOK_H3_SIZE")
[[ -n "${BOOK_FOOTNOTE_SIZE:-}"     ]] && TEMPLATE_ARGS+=(--footnote-size     "$BOOK_FOOTNOTE_SIZE")
[[ -n "${BOOK_TABLE_BODY_FONT:-}"   ]] && TEMPLATE_ARGS+=(--table-body-font   "$BOOK_TABLE_BODY_FONT")
[[ -n "${BOOK_TABLE_BODY_SIZE:-}"   ]] && TEMPLATE_ARGS+=(--table-body-size   "$BOOK_TABLE_BODY_SIZE")
[[ -n "${BOOK_TABLE_HEADER_FONT:-}" ]] && TEMPLATE_ARGS+=(--table-header-font "$BOOK_TABLE_HEADER_FONT")
[[ -n "${BOOK_TABLE_HEADER_SIZE:-}" ]] && TEMPLATE_ARGS+=(--table-header-size "$BOOK_TABLE_HEADER_SIZE")
[[ -n "${BOOK_QUOTE_PRESET:-}"      ]] && TEMPLATE_ARGS+=(--quote-preset      "$BOOK_QUOTE_PRESET")

python3 "$TEMPLATE_BUILDER" "$TEMPLATE" "${TEMPLATE_ARGS[@]}"

# ── Render front matter ───────────────────────────────────────────────────────

RENDERED_FRONT_MATTER="$(mktemp --suffix=.md)"
trap 'rm -f "$RENDERED_FRONT_MATTER"' EXIT

export FRONT_MATTER RENDERED_FRONT_MATTER
export BOOK_TITLE BOOK_SUBTITLE BOOK_OUTPUT_BASENAME
export BOOK_AUTHOR="${BOOK_AUTHOR:-Lyman Epp}"
export BOOK_HARDCOVER_ISBN="${BOOK_HARDCOVER_ISBN:-}"
export BOOK_PAPERBACK_ISBN="${BOOK_PAPERBACK_ISBN:-}"
export BOOK_COPYRIGHT_YEAR="${BOOK_COPYRIGHT_YEAR:-}"

python3 - <<'PY'
from pathlib import Path
import os

src = Path(os.environ["FRONT_MATTER"])
dst = Path(os.environ["RENDERED_FRONT_MATTER"])

replacements = {
    "{{BOOK_TITLE}}": os.environ["BOOK_TITLE"],
    "{{BOOK_SUBTITLE}}": os.environ["BOOK_SUBTITLE"],
    "{{BOOK_OUTPUT_BASENAME}}": os.environ["BOOK_OUTPUT_BASENAME"],
    "{{BOOK_AUTHOR}}": os.environ["BOOK_AUTHOR"],
    "{{BOOK_COPYRIGHT_YEAR}}": os.environ["BOOK_COPYRIGHT_YEAR"],
    "{{BOOK_HARDCOVER_ISBN}}": os.environ["BOOK_HARDCOVER_ISBN"],
    "{{BOOK_PAPERBACK_ISBN}}": os.environ["BOOK_PAPERBACK_ISBN"],
}

text = src.read_text(encoding="utf-8")
for marker, value in replacements.items():
    text = text.replace(marker, value)
dst.write_text(text, encoding="utf-8")
PY

# ── Collect chapter inputs ────────────────────────────────────────────────────

INPUTS=("$RENDERED_FRONT_MATTER")
while IFS= read -r md; do
    INPUTS+=("$BOOK_DIR/$md")
done < <(find "$BOOK_DIR" -maxdepth 1 -type f -name '[0-9][0-9]-*.md' -printf '%f\n' | sort)

if [[ ${#INPUTS[@]} -le 1 ]]; then
    echo "ERROR: No chapter files found in $BOOK_DIR (expected NN-*.md)." >&2
    exit 1
fi

echo "Building: ${BOOK_TITLE}"
echo "Output:   ${OUTPUT}"
echo "Inputs:   $((${#INPUTS[@]})) files"
printf '  - %s\n' "${INPUTS[@]}"

# ── Pandoc ────────────────────────────────────────────────────────────────────

echo
echo "Running pandoc..."

pandoc \
    --metadata-file="${METADATA}" \
    "${INPUTS[@]}" \
    --output="${OUTPUT}" \
    --reference-doc="${TEMPLATE}" \
    --lua-filter="${MDFORMAT}"

echo
echo "✓ Built: ${OUTPUT}"
