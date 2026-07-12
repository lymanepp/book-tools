#!/usr/bin/env bash
# =============================================================================
# docx.sh — Build a DOCX for publisher submission.
#
# Run from the workspace root:
#   bash tools/bin/docx.sh book1
#   bash tools/bin/docx.sh book2
#
# Output: dist/<BOOK_OUTPUT_BASENAME>-submission.docx
#
# Required files in the book directory:
#   book.env
#   front-matter-submission.md
#   metadata-submission.yaml
#   NN-*.md  (chapter files — no YAML metadata blocks inside them)
#
# Required support files in tools/bin/:
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
#   BOOK_AUTHOR              Author name
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

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=book-build-common.sh
source "$SCRIPT_DIR/book-build-common.sh"
book_build_init "${1:-}"

TEMPLATE_BUILDER="$BIN_DIR/build-template.py"
TEMPLATE="$BIN_DIR/reference-template.docx"
MDFORMAT="$BIN_DIR/mdformat.lua"
FRONT_MATTER="$BOOK_DIR/front-matter-submission.md"
METADATA="$BOOK_DIR/metadata-submission.yaml"
OUTPUT="$DIST_DIR/${BOOK_OUTPUT_BASENAME}-submission.docx"

require_files "$TEMPLATE_BUILDER" "$MDFORMAT" "$FRONT_MATTER" "$METADATA"

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
render_front_matter "$FRONT_MATTER" "$RENDERED_FRONT_MATTER"

# ── Collect chapter inputs ────────────────────────────────────────────────────

collect_markdown_inputs "$RENDERED_FRONT_MATTER" INPUTS

echo "Building: ${BOOK_TITLE}"
echo "Output:   ${OUTPUT}"
echo "Inputs:   ${#INPUTS[@]} files"
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
