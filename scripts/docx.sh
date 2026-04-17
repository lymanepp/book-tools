#!/bin/bash
# =============================================================================
# docx.sh — Build a DOCX for either print production or publisher submission.
#
# Run from a book directory that contains book.env:
#   cd book1/  && bash ../scripts/docx.sh
#   cd book1/  && bash ../scripts/docx.sh submission
#   cd counseling/ && bash ../../scripts/docx.sh
#
# Required files in the current book directory:
#   book.env
#   front-matter-print.md
#   front-matter-submission.md
#   metadata-print.yaml
#   metadata-submission.yaml
#   NN-*.md  (chapter files, no YAML metadata blocks inside them)
#
# Required support files relative to this script:
#   reference-template.docx
#   mdformat.lua
#   postprocess-pandoc.py
#
# book.env must define:
#   BOOK_TITLE
#   BOOK_SUBTITLE
#   BOOK_OUTPUT_BASENAME
#   BOOK_HARDCOVER_ISBN   (optional — substituted in front matter)
#   BOOK_PAPERBACK_ISBN   (optional — substituted in front matter)
# =============================================================================

set -euo pipefail

MODE="${1:-print}"

SCRIPTS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TEMPLATE="${SCRIPTS_DIR}/reference-template.docx"
MDFORMAT="${SCRIPTS_DIR}/mdformat.lua"
POSTPROC="${SCRIPTS_DIR}/postprocess-pandoc.py"
BOOK_ENV="book.env"

# ── Validate environment ─────────────────────────────────────────────────────

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

for required in "$TEMPLATE" "$MDFORMAT" "$POSTPROC"; do
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

# ── Template ──────────────────────────────────────────────────────────────────
# Regenerate the reference template before every print build so style changes
# are always in sync.  Skip for submission builds (not needed, saves time).

if $APPLY_POSTPROCESS; then
    echo "Regenerating reference template..."
    python3 "${SCRIPTS_DIR}/build-template.py" "$TEMPLATE"
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

# ── Collect inputs ────────────────────────────────────────────────────────────

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
