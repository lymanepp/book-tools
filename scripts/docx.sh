#!/bin/bash
# =============================================================================
# docx.sh — Build a DOCX for either print production or publisher submission.
#
# Run from a book directory that contains book.env:
#   cd book1/    && bash ../scripts/docx.sh
#   cd book1/    && bash ../scripts/docx.sh submission
#   cd counseling/ && bash ../../scripts/docx.sh
#
# Required files in the current book directory:
#   book.env
#   front-matter-print.md
#   front-matter-submission.md
#   metadata-print.yaml
#   metadata-submission.yaml
#   NN-*.md  (chapter files — no YAML metadata blocks inside them)
#
# Required support files relative to this script:
#   build-template.py
#   postprocess-pandoc.py
#   mdformat.lua
#
# =============================================================================
# book.env reference
# =============================================================================
#
# Required:
#   BOOK_TITLE               Display title (substituted into front matter)
#   BOOK_SUBTITLE            Display subtitle
#   BOOK_OUTPUT_BASENAME     Stem for output filename, e.g. "my-book"
#
# Optional identity (substituted into front matter if present):
#   BOOK_HARDCOVER_ISBN
#   BOOK_PAPERBACK_ISBN
#   BOOK_AUTHOR              Default: Lyman Epp (hardcoded in epub.sh; update there)
#   BOOK_ID                  Informational only
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
# Page geometry — all optional; defaults shown:
#   BOOK_PAGE_WIDTH          Page width in inches.     [6]
#   BOOK_PAGE_HEIGHT         Page height in inches.    [9]
#   BOOK_MARGIN_INNER        Inner (spine) margin in.  [0.75]
#   BOOK_MARGIN_OUTER        Outer margin in inches.   [0.5]
#   BOOK_MARGIN_TOP          Top margin in inches.     [0.75]
#   BOOK_MARGIN_BOTTOM       Bottom margin in inches.  [0.75]
#
# =============================================================================

set -euo pipefail

MODE="${1:-print}"

SCRIPTS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TEMPLATE_BUILDER="${SCRIPTS_DIR}/build-template.py"
TEMPLATE="${SCRIPTS_DIR}/reference-template.docx"
MDFORMAT="${SCRIPTS_DIR}/mdformat.lua"
POSTPROC="${SCRIPTS_DIR}/postprocess-pandoc.py"
BOOK_ENV="book.env"

# ── Validate environment ──────────────────────────────────────────────────────

if [[ ! -f "$BOOK_ENV" ]]; then
    echo "ERROR: Missing $BOOK_ENV. Run from a book directory." >&2
    exit 1
fi

# shellcheck disable=SC1091
source "$BOOK_ENV"

for var in BOOK_TITLE BOOK_SUBTITLE BOOK_OUTPUT_BASENAME; do
    if [[ -z "${!var:-}" ]]; then
        echo "ERROR: $BOOK_ENV must define $var." >&2
        exit 1
    fi
done

for required in "$TEMPLATE_BUILDER" "$MDFORMAT" "$POSTPROC"; do
    if [[ ! -f "$required" ]]; then
        echo "ERROR: Missing required file: $required" >&2
        exit 1
    fi
done

# ── Mode selection ────────────────────────────────────────────────────────────

case "$MODE" in
    print)
        FRONT_MATTER="front-matter-print.md"
        METADATA="metadata-print.yaml"
        OUTPUT="${BOOK_OUTPUT_BASENAME}.docx"
        APPLY_POSTPROCESS=true
        ;;
    submission)
        FRONT_MATTER="front-matter-submission.md"
        METADATA="metadata-submission.yaml"
        OUTPUT="${BOOK_OUTPUT_BASENAME}-submission.docx"
        APPLY_POSTPROCESS=false
        ;;
    *)
        echo "ERROR: Unknown mode '$MODE'. Use 'print' or 'submission'." >&2
        exit 1
        ;;
esac

for required in "$FRONT_MATTER" "$METADATA"; do
    if [[ ! -f "$required" ]]; then
        echo "ERROR: Missing required file: $required" >&2
        exit 1
    fi
done

# ── Build reference template ──────────────────────────────────────────────────
# Only for print builds (submission doesn't use the template for styling).
# Rebuild on every print build so book.env changes are always reflected.

if $APPLY_POSTPROCESS; then
    echo "Building reference template..."

    # Map book.env variables to build-template.py CLI arguments.
    # Each argument is only passed when the book.env variable is set,
    # so unset variables fall through to the script's own defaults.

    TEMPLATE_ARGS=()

    [[ -n "${BOOK_BODY_FONT:-}"          ]] && TEMPLATE_ARGS+=(--body-font         "$BOOK_BODY_FONT")
    [[ -n "${BOOK_BODY_SIZE:-}"          ]] && TEMPLATE_ARGS+=(--body-size         "$BOOK_BODY_SIZE")
    [[ -n "${BOOK_BODY_ALIGN:-}"         ]] && TEMPLATE_ARGS+=(--body-align        "$BOOK_BODY_ALIGN")
    [[ -n "${BOOK_FIRST_LINE_INDENT:-}"  ]] && TEMPLATE_ARGS+=(--first-line-indent "$BOOK_FIRST_LINE_INDENT")
    [[ -n "${BOOK_LINE_SPACING:-}"       ]] && TEMPLATE_ARGS+=(--line-spacing      "$BOOK_LINE_SPACING")
    [[ -n "${BOOK_H1_SIZE:-}"            ]] && TEMPLATE_ARGS+=(--h1-size           "$BOOK_H1_SIZE")
    [[ -n "${BOOK_H2_SIZE:-}"            ]] && TEMPLATE_ARGS+=(--h2-size           "$BOOK_H2_SIZE")
    [[ -n "${BOOK_H3_SIZE:-}"            ]] && TEMPLATE_ARGS+=(--h3-size           "$BOOK_H3_SIZE")
    [[ -n "${BOOK_FOOTNOTE_SIZE:-}"      ]] && TEMPLATE_ARGS+=(--footnote-size     "$BOOK_FOOTNOTE_SIZE")
    [[ -n "${BOOK_TABLE_BODY_FONT:-}"    ]] && TEMPLATE_ARGS+=(--table-body-font   "$BOOK_TABLE_BODY_FONT")
    [[ -n "${BOOK_TABLE_BODY_SIZE:-}"    ]] && TEMPLATE_ARGS+=(--table-body-size   "$BOOK_TABLE_BODY_SIZE")
    [[ -n "${BOOK_TABLE_HEADER_FONT:-}"  ]] && TEMPLATE_ARGS+=(--table-header-font "$BOOK_TABLE_HEADER_FONT")
    [[ -n "${BOOK_TABLE_HEADER_SIZE:-}"  ]] && TEMPLATE_ARGS+=(--table-header-size "$BOOK_TABLE_HEADER_SIZE")
    [[ -n "${BOOK_QUOTE_PRESET:-}"       ]] && TEMPLATE_ARGS+=(--quote-preset      "$BOOK_QUOTE_PRESET")
    [[ -n "${BOOK_PAGE_WIDTH:-}"         ]] && TEMPLATE_ARGS+=(--page-width        "$BOOK_PAGE_WIDTH")
    [[ -n "${BOOK_PAGE_HEIGHT:-}"        ]] && TEMPLATE_ARGS+=(--page-height       "$BOOK_PAGE_HEIGHT")
    [[ -n "${BOOK_MARGIN_INNER:-}"       ]] && TEMPLATE_ARGS+=(--margin-inner      "$BOOK_MARGIN_INNER")
    [[ -n "${BOOK_MARGIN_OUTER:-}"       ]] && TEMPLATE_ARGS+=(--margin-outer      "$BOOK_MARGIN_OUTER")
    [[ -n "${BOOK_MARGIN_TOP:-}"         ]] && TEMPLATE_ARGS+=(--margin-top        "$BOOK_MARGIN_TOP")
    [[ -n "${BOOK_MARGIN_BOTTOM:-}"      ]] && TEMPLATE_ARGS+=(--margin-bottom     "$BOOK_MARGIN_BOTTOM")

    python3 "$TEMPLATE_BUILDER" "$TEMPLATE" "${TEMPLATE_ARGS[@]}"
fi

# ── Render front matter ───────────────────────────────────────────────────────

RENDERED_FRONT_MATTER="$(mktemp --suffix=.md)"
trap 'rm -f "$RENDERED_FRONT_MATTER"' EXIT

sed \
    -e "s|{{BOOK_TITLE}}|${BOOK_TITLE}|g" \
    -e "s|{{BOOK_SUBTITLE}}|${BOOK_SUBTITLE}|g" \
    -e "s|{{BOOK_HARDCOVER_ISBN}}|${BOOK_HARDCOVER_ISBN:-}|g" \
    -e "s|{{BOOK_PAPERBACK_ISBN}}|${BOOK_PAPERBACK_ISBN:-}|g" \
    "$FRONT_MATTER" > "$RENDERED_FRONT_MATTER"

# ── Collect chapter inputs ────────────────────────────────────────────────────

INPUTS=("$RENDERED_FRONT_MATTER")
while IFS= read -r md; do
    INPUTS+=("$md")
done < <(find . -maxdepth 1 -type f -name '[0-9][0-9]-*.md' -printf '%f\n' | sort)

if [[ ${#INPUTS[@]} -le 1 ]]; then
    echo "ERROR: No chapter files found (expected NN-*.md)." >&2
    exit 1
fi

echo "Building: ${BOOK_TITLE}"
echo "Mode:     ${MODE}"
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

# ── Post-process (print only) ─────────────────────────────────────────────────

if $APPLY_POSTPROCESS; then
    echo
    echo "Running postprocess-pandoc.py..."
    python3 "${POSTPROC}" "${OUTPUT}" --title "${BOOK_TITLE}"
else
    echo
    echo "Skipping print-only post-processing for submission build."
fi

echo
echo "✓ Built: ${OUTPUT}"
