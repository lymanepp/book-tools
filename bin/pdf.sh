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
COMBINED_MD="$BUILD_DIR/$BOOK_NAME.combined.md"
BODY_TYP="$BUILD_DIR/$BOOK_NAME.body.typ"
GENERATED_TYP="$BUILD_DIR/$BOOK_NAME.typ"
OUTPUT_PDF="$DIST_DIR/${BOOK_OUTPUT_BASENAME}-$MODE.pdf"

require_files "$LUA_FILTER" "$BOOK_TYP_SRC"
mkdir -p "$BUILD_DIR"

# Escape strings for Typst string literals.
typst_escape() {
  local s="${1-}"
  s=${s//\\/\\\\}
  s=${s//\"/\\\"}
  printf '%s' "$s"
}


collect_chapters() {
  find "$BOOK_DIR" -maxdepth 1 -type f -name '[0-9][0-9]-*.md' -printf '%f\n' | sort
}

: > "$COMBINED_MD"

mapfile -t CHAPTERS < <(collect_chapters)
if [[ "${#CHAPTERS[@]}" -eq 0 ]]; then
  echo "No chapters found. Add numbered chapter files like 00-introduction.md." >&2
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
WSS_SUPPRESS_TYPST_PREAMBLE=1 pandoc \
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
  printf '#show: book.setup.with(title: "%s")\n\n' "$(typst_escape "$BOOK_TITLE")"

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
  "$GENERATED_TYP" \
  "$OUTPUT_PDF"

echo "Built: $OUTPUT_PDF"
