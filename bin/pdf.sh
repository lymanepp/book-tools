#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=book-build-common.sh
source "$SCRIPT_DIR/book-build-common.sh"
book_build_init "${1:-}"

MODE="print"
BUILD_DIR="$ROOT/build/$BOOK_NAME"
LUA_FILTER="$BIN_DIR/typst-markup.lua"
BOOK_TYP_SRC="$BIN_DIR/book.typ"
FONT_SETUP="$BIN_DIR/ensure-print-fonts.sh"
COMBINED_MD="$BUILD_DIR/$BOOK_NAME.combined.md"
BODY_TYP="$BUILD_DIR/$BOOK_NAME.body.typ"
GENERATED_TYP="$BUILD_DIR/$BOOK_NAME.typ"
OUTPUT_PDF="$DIST_DIR/${BOOK_OUTPUT_BASENAME}-$MODE.pdf"
BOOK_INFO_TYP="$BUILD_DIR/book-info.typ"

require_files "$LUA_FILTER" "$BOOK_TYP_SRC" "$FONT_SETUP"
mkdir -p "$BUILD_DIR"
FONT_DIR="$("$FONT_SETUP" "$ROOT")"

# Optional per-book print geometry. These defaults are the historical book-tools
# 6×9 layout, so existing books remain byte-for-layout compatible unless a book
# explicitly opts into different trim or margins in book.env.
: "${BOOK_PAGE_WIDTH:=6}"
: "${BOOK_PAGE_HEIGHT:=9}"
: "${BOOK_MARGIN_TOP:=0.70}"
: "${BOOK_MARGIN_BOTTOM:=0.62}"
: "${BOOK_MARGIN_INNER:=0.95}"
: "${BOOK_MARGIN_OUTER:=0.575}"
: "${BOOK_HYPHENATE:=false}"
: "${BOOK_CHAPTER_OPEN:=recto}"
: "${BOOK_MIN_PRINT_PAGES:=}"

require_positive_number() {
  local name="$1" value="$2"
  if [[ ! "$value" =~ ^([0-9]+([.][0-9]*)?|[.][0-9]+)$ ]] \
      || ! awk -v n="$value" 'BEGIN { exit !(n > 0) }'; then
    echo "ERROR: $BOOK_ENV must define $name as a positive number of inches, got: $value" >&2
    exit 1
  fi
}

for geometry_var in \
  BOOK_PAGE_WIDTH BOOK_PAGE_HEIGHT BOOK_MARGIN_TOP BOOK_MARGIN_BOTTOM \
  BOOK_MARGIN_INNER BOOK_MARGIN_OUTER; do
  require_positive_number "$geometry_var" "${!geometry_var}"
done

case "$BOOK_HYPHENATE" in
  true|false) ;;
  *)
    echo "ERROR: $BOOK_ENV must define BOOK_HYPHENATE as true or false, got: $BOOK_HYPHENATE" >&2
    exit 1
    ;;
esac

case "$BOOK_CHAPTER_OPEN" in
  recto|next) ;;
  *)
    echo "ERROR: $BOOK_ENV must define BOOK_CHAPTER_OPEN as recto or next, got: $BOOK_CHAPTER_OPEN" >&2
    exit 1
    ;;
esac

if [[ -n "$BOOK_MIN_PRINT_PAGES" && ! "$BOOK_MIN_PRINT_PAGES" =~ ^[1-9][0-9]*$ ]]; then
  echo "ERROR: $BOOK_ENV must define BOOK_MIN_PRINT_PAGES as a positive integer, got: $BOOK_MIN_PRINT_PAGES" >&2
  exit 1
fi

# Escape strings for Typst string literals.
typst_escape() {
  local s="${1-}"
  s=${s//\\/\\\\}
  s=${s//\"/\\\"}
  printf '%s' "$s"
}


# Generate one canonical Typst record from book.env. Front-matter templates
# consume this instead of repeating book-specific identity data.
{
  printf '// Generated from %s. Do not edit.\n' "${BOOK_ENV#$ROOT/}"
  printf '#let book_info = (\n'
  printf '  title: "%s",\n' "$(typst_escape "$BOOK_TITLE")"
  printf '  subtitle: "%s",\n' "$(typst_escape "$BOOK_SUBTITLE")"
  printf '  author: "%s",\n' "$(typst_escape "$BOOK_AUTHOR")"
  printf '  copyright_year: "%s",\n' "$(typst_escape "$BOOK_COPYRIGHT_YEAR")"
  printf '  hardcover_isbn: "%s",\n' "$(typst_escape "$BOOK_HARDCOVER_ISBN")"
  printf '  paperback_isbn: "%s",\n' "$(typst_escape "$BOOK_PAPERBACK_ISBN")"
  printf '  scripture_notice: "%s",\n' "$(typst_escape "$BOOK_SCRIPTURE_NOTICE")"
  printf '  source_title: "%s",\n' "$(typst_escape "$BOOKLET_SOURCE_TITLE")"
  printf ')\n'
} > "$BOOK_INFO_TYP"


collect_chapters() {
  # Numbered chapters are NN-*.md. Interstitial structural files such as
  # Parts and the Conclusion may use a sortable letter suffix (NNa-*.md).
  find "$BOOK_DIR" -maxdepth 1 -type f \
    \( -name '[0-9][0-9]-*.md' -o -name '[0-9][0-9][a-z]-*.md' \) \
    -printf '%f\n' | sort
}

: > "$COMBINED_MD"

mapfile -t CHAPTERS < <(collect_chapters)
if [[ "${#CHAPTERS[@]}" -eq 0 ]]; then
  echo "No manuscript files found. Add files like 00-introduction.md (and optional interstitial NNa-*.md files)." >&2
  exit 1
fi

for chapter in "${CHAPTERS[@]}"; do
  file="$BOOK_DIR/$chapter"
  [[ -f "$file" ]] || { echo "Missing chapter: $file" >&2; exit 1; }
  cat "$file" >> "$COMBINED_MD"
  printf '\n\n' >> "$COMBINED_MD"
done
# Remove invisible Unicode format/control characters that can surface as
# visible PDF text-extraction or print artifacts after line breaking.
perl -CSD -0pi -e 's/[\x{FEFF}\x{00AD}\x{FFFE}\x{FFFF}]//g' "$COMBINED_MD"


cp "$BOOK_TYP_SRC" "$BUILD_DIR/book.typ"

# Convert chapter/body Markdown only. Front matter is generated in Typst below.
SUPPRESS_TYPST_PREAMBLE=1 pandoc \
  -f markdown+smart+footnotes+pipe_tables+raw_tex \
  -t typst \
  --wrap=none \
  --lua-filter "$LUA_FILTER" \
  -o "$BODY_TYP" \
  "$COMBINED_MD"


FRONT_MATTER_SRC="$BOOK_DIR/front-matter-$MODE.typ"
FRONT_MATTER_BUILD="$BUILD_DIR/front-matter-$MODE.typ"
BACK_MATTER_SRC="$BOOK_DIR/back-matter-$MODE.typ"
BACK_MATTER_BUILD="$BUILD_DIR/back-matter-$MODE.typ"

{
  printf '#import "book.typ" as book\n'
  printf '#show: book.setup.with(\n'
  printf '  title: "%s",\n' "$(typst_escape "$BOOK_TITLE")"
  printf '  page_width: %sin,\n' "$BOOK_PAGE_WIDTH"
  printf '  page_height: %sin,\n' "$BOOK_PAGE_HEIGHT"
  printf '  margin_top: %sin,\n' "$BOOK_MARGIN_TOP"
  printf '  margin_bottom: %sin,\n' "$BOOK_MARGIN_BOTTOM"
  printf '  margin_inside: %sin,\n' "$BOOK_MARGIN_INNER"
  printf '  margin_outside: %sin,\n' "$BOOK_MARGIN_OUTER"
  printf ')\n\n'

  if [[ -f "$FRONT_MATTER_SRC" ]]; then
    cp "$FRONT_MATTER_SRC" "$FRONT_MATTER_BUILD"
    [[ -f "$BUILD_DIR/publication-info.typ" ]] || { echo "Missing publication metadata: $BUILD_DIR/publication-info.typ" >&2; exit 1; }
    printf "#include \"front-matter-$MODE.typ\"\n\n"
    TOC_SRC="$BIN_DIR/toc-$MODE.typ"
    cp "$TOC_SRC" "$BUILD_DIR/toc-$MODE.typ"
    printf "#include \"toc-$MODE.typ\"\n\n"
  else
    # Fallback: use the built-in front_matter() function for books
    # that do not yet have a front-matter-$MODE.typ.
    printf '#book.front_matter(\n'
    printf '  title: "%s",\n' "$(typst_escape "$BOOK_TITLE")"
    printf '  subtitle: "%s",\n' "$(typst_escape "$BOOK_SUBTITLE")"
    printf '  author: "%s",\n' "$(typst_escape "$BOOK_AUTHOR")"
    printf '  copyright_year: "%s",\n' "$(typst_escape "$BOOK_COPYRIGHT_YEAR")"
    printf '  hardcover_isbn: "%s",\n' "$(typst_escape "$BOOK_HARDCOVER_ISBN")"
    printf '  paperback_isbn: "%s",\n' "$(typst_escape "$BOOK_PAPERBACK_ISBN")"
    printf ')\n\n'
  fi

  cat "$BODY_TYP"

  if [[ -f "$BACK_MATTER_SRC" ]]; then
    cp "$BACK_MATTER_SRC" "$BACK_MATTER_BUILD"
    # Back matter is intentionally concatenated instead of included.
    # Typst includes do not inherit this file's local `book` import, while
    # the curated back-matter file is allowed to call book.* helpers directly.
    printf '\n\n'
    cat "$BACK_MATTER_BUILD"
    printf '\n'
  fi
} > "$GENERATED_TYP"

typst compile \
  --root "$ROOT" \
  --font-path "$FONT_DIR" \
  --input "book-hyphenate=$BOOK_HYPHENATE" \
  --input "book-chapter-open=$BOOK_CHAPTER_OPEN" \
  "$GENERATED_TYP" \
  "$OUTPUT_PDF"

if [[ -n "$BOOK_MIN_PRINT_PAGES" ]]; then
  if command -v pdfinfo >/dev/null 2>&1; then
    ACTUAL_PRINT_PAGES="$(pdfinfo "$OUTPUT_PDF" | awk '/^Pages:/ { print $2; exit }')"
    if [[ ! "$ACTUAL_PRINT_PAGES" =~ ^[0-9]+$ ]]; then
      echo "ERROR: Could not determine page count for $OUTPUT_PDF" >&2
      exit 1
    fi
    if (( ACTUAL_PRINT_PAGES < BOOK_MIN_PRINT_PAGES )); then
      echo "ERROR: $OUTPUT_PDF has $ACTUAL_PRINT_PAGES pages; minimum configured print page count is $BOOK_MIN_PRINT_PAGES" >&2
      exit 1
    fi
    echo "Print page count: $ACTUAL_PRINT_PAGES (minimum $BOOK_MIN_PRINT_PAGES)"
  else
    echo "WARNING: pdfinfo unavailable; cannot verify BOOK_MIN_PRINT_PAGES=$BOOK_MIN_PRINT_PAGES" >&2
  fi
fi

# Guard against a regression to the legacy 12pt files or silent Libertinus
# substitution. `pdffonts` is supplied by poppler-utils when available.
if command -v pdffonts >/dev/null 2>&1; then
  FONT_REPORT="$(pdffonts "$OUTPUT_PDF")"
  if ! grep -q 'EBGaramond' <<<"$FONT_REPORT"; then
    echo "ERROR: EB Garamond was not embedded in $OUTPUT_PDF" >&2
    printf '%s\n' "$FONT_REPORT" >&2
    exit 1
  fi
  if grep -Eq 'EBGaramond12|LibertinusSerif' <<<"$FONT_REPORT"; then
    echo "ERROR: Legacy/fallback serif detected in $OUTPUT_PDF" >&2
    printf '%s\n' "$FONT_REPORT" >&2
    exit 1
  fi
fi

echo "Built: $OUTPUT_PDF"
