#!/usr/bin/env bash
# =============================================================================
# epub.sh — Build an EPUB from the manuscript source.
#
# Run from the workspace root:
#   bash tools/bin/epub.sh book1
#   bash tools/bin/epub.sh book2
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
# - Footnotes are preserved by default so the EPUB contains the full manuscript.
# - Set EPUB_STRIP_FOOTNOTES=1 only when building a special TTS copy.
# - Images are not stripped; handle per-book in metadata or chapter source if needed.
# =============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=book-build-common.sh
source "$SCRIPT_DIR/book-build-common.sh"
book_build_init "${1:-}"

METADATA="$BOOK_DIR/metadata-submission.yaml"
FRONT_MATTER="$BOOK_DIR/front-matter-submission.md"
OUTPUT="$DIST_DIR/${BOOK_OUTPUT_BASENAME}.epub"
STRIP_FOOTNOTES="${EPUB_STRIP_FOOTNOTES:-0}"

require_files "$METADATA" "$FRONT_MATTER"

# ── Collect chapter inputs ────────────────────────────────────────────────────

collect_markdown_inputs "$FRONT_MATTER" INPUTS

echo "Building: ${BOOK_TITLE}"
echo "Output:   ${OUTPUT}"
echo "Inputs:   ${#INPUTS[@]} files"
printf '  - %s\n' "${INPUTS[@]}"

# ── Render/copy inputs into workdir ───────────────────────────────────────────

WORKDIR="$(mktemp -d)"
trap 'rm -rf "$WORKDIR"' EXIT

CLEAN_FILES=()


for src in "${INPUTS[@]}"; do
    out="$WORKDIR/$(basename "$src")"

    if [[ "$src" == "$FRONT_MATTER" ]]; then
        render_front_matter "$src" "$out"
    else
        cp "$src" "$out"
    fi

    if [[ "$STRIP_FOOTNOTES" == "1" ]]; then
        # Special-purpose TTS build only. This intentionally removes footnotes.
        # It is not used for the normal EPUB, which preserves the full text.
        sed -i '/^\[\^[^]]*\]:/d' "$out"
        sed -i 's/\[\^[^]]*\]//g' "$out"
    fi

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
    --css="$BIN_DIR/epub.css" \
    --metadata-file="${METADATA}" \
    --metadata title="${BOOK_TITLE}" \
    --metadata subtitle="${BOOK_SUBTITLE}" \
    --metadata author="${BOOK_AUTHOR}" \
    --metadata lang="en-US" \
    --wrap=none \
    --standalone

echo
echo "✓ Built: ${OUTPUT}"
echo

if command -v epubcheck &>/dev/null; then
    echo "Running epubcheck..."
    epubcheck "${OUTPUT}"
else
    echo "epubcheck not found, skipping validation."
fi

echo
