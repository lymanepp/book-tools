#!/bin/bash
# =============================================================================
# build-epub.sh
#
# Build an EPUB from the manuscript source using the submission-oriented
# front matter and metadata.
#
# Run from either book directory:
#   cd book1/ && bash ../scripts/build-epub.sh
#   cd book2/ && bash ../scripts/build-epub.sh
#
# Expected files in the current book directory:
#   book.env
#   front-matter-submission.md
#   metadata-submission.yaml
#   NN-*.md chapter files
#
# Expected support files alongside this script:
#   mdformat.lua   (optional for future use; not required here)
#
# Notes:
# - Chapter files should not contain YAML metadata blocks.
# - EPUB uses the submission front matter, not the print front matter.
# - Footnotes are stripped because some TTS / Virtual Voice readers treat
#   them as body text.
# =============================================================================

set -euo pipefail

SCRIPTS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
METADATA="metadata-submission.yaml"
FRONT_MATTER="front-matter-submission.md"
BOOK_ENV="book.env"

if [[ ! -f "$METADATA" ]]; then
    echo "ERROR: Missing metadata file: $METADATA" >&2
    exit 1
fi

if [[ ! -f "$FRONT_MATTER" ]]; then
    echo "ERROR: Missing front matter file: $FRONT_MATTER" >&2
    exit 1
fi

if [[ ! -f "$BOOK_ENV" ]]; then
    echo "ERROR: Missing $BOOK_ENV. Run from a book directory." >&2
    exit 1
fi

# shellcheck disable=SC1091
source "$BOOK_ENV"

if [[ -z "${BOOK_TITLE:-}" || -z "${BOOK_SUBTITLE:-}" || -z "${BOOK_OUTPUT_BASENAME:-}" ]]; then
    echo "ERROR: $BOOK_ENV must define BOOK_TITLE, BOOK_SUBTITLE, and BOOK_OUTPUT_BASENAME." >&2
    exit 1
fi

TITLE="$BOOK_TITLE"
SUBTITLE="$BOOK_SUBTITLE"
OUTPUT="${BOOK_OUTPUT_BASENAME}.epub"

WORKDIR="$(mktemp -d)"
trap 'rm -rf "$WORKDIR"' EXIT

echo "Building: ${TITLE}"
echo "Output:   ${OUTPUT}"

INPUTS=("$FRONT_MATTER")
while IFS= read -r md; do
    INPUTS+=("$md")
done < <(find . -maxdepth 1 -type f -name '[0-9][0-9]-*.md' -printf '%f\n' | sort)

if [[ ${#INPUTS[@]} -le 1 ]]; then
    echo "ERROR: No chapter files found." >&2
    exit 1
fi

echo "Inputs:   $((${#INPUTS[@]})) files"
printf '  - %s\n' "${INPUTS[@]}"

CLEAN_FILES=()

for md in "${INPUTS[@]}"; do
    out="${WORKDIR}/${md}"

    cp "$md" "$out"

    # Strip raw print/layout commands if any remain.
    sed -i \
        -e '/^\\newpage/d' \
        -e '/^\\vspace/d' \
        -e '/^\\toc/d' \
        -e '/^\\raggedright/d' \
        -e 's/\\newpage//g' \
        -e 's/\\vspace{[^}]*}//g' \
        "$out"

    # Strip Pandoc fenced div markers if any remain.
    sed -i '/^:::/d' "$out"

    # Strip footnote definitions and inline references for EPUB/TTS friendliness.
    sed -i '/^\[\^[^]]*\]:/d' "$out"
    sed -i 's/\[\^[^]]*\]//g' "$out"

    # Strip print-only image references if desired for EPUB simplicity.
    sed -i '/!\[.*\](.*\.png)/d' "$out"

    # Collapse repeated blank lines.
    awk 'BEGIN{blank=0} /^$/{if(blank) next; blank=1} !/^$/{blank=0} {print}' "$out" > "${out}.tmp"
    mv "${out}.tmp" "$out"

    CLEAN_FILES+=("$out")
done

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
    --metadata title="${TITLE}" \
    --metadata subtitle="${SUBTITLE}" \
    --metadata author="Lyman Epp" \
    --metadata lang="en-US" \
    --metadata description="A Reformed Baptist layman's examination of what Scripture says on the questions the world and the church are pressing hardest." \
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
