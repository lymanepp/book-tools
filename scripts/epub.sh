#!/usr/bin/env bash
# =============================================================================
# epub.sh — Build an EPUB from the manuscript source.
#
# Run from the workspace root:
#   bash tools/scripts/epub.sh book1
#   bash tools/scripts/epub.sh book2
#
# Output: dist/<BOOK_OUTPUT_BASENAME>.epub
#
# Required files in the book directory:
#   book.env
#   front-matter-submission.md
#   metadata-submission.yaml
#   NN-*.md  (chapter files — no YAML metadata blocks inside them)
#
# Notes:
# - Footnotes are stripped: some TTS / Virtual Voice readers treat them as body text.
# - Images are not stripped; handle per-book in metadata or chapter source if needed.
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
DIST_DIR="$ROOT/dist"

BOOK_ENV="$BOOK_DIR/book.env"
METADATA="$BOOK_DIR/metadata-submission.yaml"
FRONT_MATTER="$BOOK_DIR/front-matter-submission.md"

# ── Validate inputs ───────────────────────────────────────────────────────────

[[ -d "$BOOK_DIR" ]] || { echo "ERROR: Missing book dir: $BOOK_DIR" >&2; exit 1; }

if [[ ! -f "$BOOK_ENV" ]]; then
    echo "ERROR: Missing $BOOK_ENV." >&2
    exit 1
fi

# shellcheck disable=SC1090
source "$BOOK_ENV"

if [[ -z "${BOOK_TITLE:-}" || -z "${BOOK_SUBTITLE:-}" || -z "${BOOK_OUTPUT_BASENAME:-}" ]]; then
    echo "ERROR: $BOOK_ENV must define BOOK_TITLE, BOOK_SUBTITLE, and BOOK_OUTPUT_BASENAME." >&2
    exit 1
fi

for required in "$METADATA" "$FRONT_MATTER"; do
    if [[ ! -f "$required" ]]; then
        echo "ERROR: Missing required file: $required" >&2
        exit 1
    fi
done

mkdir -p "$DIST_DIR"
OUTPUT="$DIST_DIR/${BOOK_OUTPUT_BASENAME}.epub"
AUTHOR="${BOOK_AUTHOR:-Lyman Epp}"

# ── Collect chapter inputs ────────────────────────────────────────────────────

INPUTS=("$FRONT_MATTER")
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

# ── Clean inputs into workdir ─────────────────────────────────────────────────

WORKDIR="$(mktemp -d)"
trap 'rm -rf "$WORKDIR"' EXIT

CLEAN_FILES=()

for src in "${INPUTS[@]}"; do
    out="$WORKDIR/$(basename "$src")"

    cp "$src" "$out"

    # Strip footnote definitions and inline references for EPUB/TTS friendliness.
    sed -i '/^\[\^[^]]*\]:/d' "$out"
    sed -i 's/\[\^[^]]*\]//g' "$out"

    # Collapse repeated blank lines.
    awk 'BEGIN{blank=0} /^$/{if(blank) next; blank=1} !/^$/{blank=0} {print}' \
        "$out" > "${out}.tmp"
    mv "${out}.tmp" "$out"

    CLEAN_FILES+=("$out")
done

# ── Pandoc ────────────────────────────────────────────────────────────────────

echo
echo "Running pandoc..."

pandoc \
    "${CLEAN_FILES[@]}" \
    --output="${OUTPUT}" \
    --from=markdown \
    --to=epub3 \
    --toc \
    --toc-depth=1 \
    --split-level=1 \
    --metadata-file="${METADATA}" \
    --metadata title="${BOOK_TITLE}" \
    --metadata subtitle="${BOOK_SUBTITLE}" \
    --metadata author="${AUTHOR}" \
    --metadata lang="en-US" \
    --wrap=none \
    --standalone

echo
echo "✓ Built: ${OUTPUT}"
echo

if command -v epubcheck &>/dev/null; then
    echo "Running epubcheck..."
    java -jar "$(command -v epubcheck)" "${OUTPUT}"
else
    echo "epubcheck not found, skipping validation."
fi

echo
