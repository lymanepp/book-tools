#!/usr/bin/env bash
set -euo pipefail

ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
cd "$ROOT"

BOOK="${1:-}"
MODE="${2:-print}"

if [[ -z "$BOOK" ]]; then
  echo "Usage: $0 book1|book2 [print|submission]" >&2
  exit 1
fi

BOOK_NAME="${BOOK#./}"
BOOK_DIR="$ROOT/$BOOK_NAME"
SCRIPTS_DIR="$ROOT/tools/scripts"
BUILD_DIR="$ROOT/build/$BOOK_NAME"
DIST_DIR="$ROOT/dist"

LUA_FILTER="$SCRIPTS_DIR/typst-markup.lua"
BOOK_TYP_SRC="$SCRIPTS_DIR/book.typ"

[[ -d "$BOOK_DIR" ]] || { echo "Missing book dir: $BOOK_DIR" >&2; exit 1; }
[[ -f "$LUA_FILTER" ]] || { echo "Missing Lua filter: $LUA_FILTER" >&2; exit 1; }
[[ -f "$BOOK_TYP_SRC" ]] || { echo "Missing Typst template: $BOOK_TYP_SRC" >&2; exit 1; }

mkdir -p "$BUILD_DIR" "$DIST_DIR"

COMBINED_MD="$BUILD_DIR/$BOOK_NAME.combined.md"
BODY_TYP="$BUILD_DIR/$BOOK_NAME.body.typ"
GENERATED_TYP="$BUILD_DIR/$BOOK_NAME.typ"
OUTPUT_PDF="$DIST_DIR/$BOOK_NAME-$MODE.pdf"

# Optional per-book metadata. Empty/missing values fall through to defaults below.
if [[ -f "$BOOK_DIR/book.env" ]]; then
  set -a
  # shellcheck disable=SC1090
  source "$BOOK_DIR/book.env"
  set +a
fi

case "$BOOK_NAME" in
  book1)
    : "${BOOK_TITLE:=What Scripture Says, Volume 1}"
    : "${BOOK_SUBTITLE:=Confronting the World with Biblical Truth}"
    : "${BOOK_AUTHOR:=Lyman Epp}"
    : "${BOOK_COPYRIGHT_YEAR:=2026}"
    : "${BOOK_HARDCOVER_ISBN:=979-8-251614-81-7}"
    : "${BOOK_PAPERBACK_ISBN:=979-8-251985-46-7}"
    ;;
  book2)
    : "${BOOK_TITLE:=What Scripture Says, Volume 2}"
    : "${BOOK_SUBTITLE:=Submitting the Church to Biblical Authority}"
    : "${BOOK_AUTHOR:=Lyman Epp}"
    : "${BOOK_COPYRIGHT_YEAR:=2026}"
    : "${BOOK_HARDCOVER_ISBN:=979-8-254309-45-1}"
    : "${BOOK_PAPERBACK_ISBN:=979-8-254309-71-0}"
    ;;
  *)
    : "${BOOK_TITLE:=$BOOK_NAME}"
    : "${BOOK_SUBTITLE:=}"
    : "${BOOK_AUTHOR:=Lyman Epp}"
    : "${BOOK_COPYRIGHT_YEAR:=2026}"
    : "${BOOK_HARDCOVER_ISBN:=}"
    : "${BOOK_PAPERBACK_ISBN:=}"
    ;;
esac

# Escape strings for Typst string literals.
typst_escape() {
  local s="${1-}"
  s=${s//\\/\\\\}
  s=${s//\"/\\\"}
  printf '%s' "$s"
}

collect_chapters() {
  if [[ -f "$BOOK_DIR/chapters.txt" ]]; then
    while IFS= read -r chapter || [[ -n "$chapter" ]]; do
      chapter="${chapter%%#*}"
      chapter="$(echo "$chapter" | xargs)"
      [[ -z "$chapter" ]] && continue
      printf '%s\n' "$chapter"
    done < "$BOOK_DIR/chapters.txt"
  else
    # Deterministic fallback for the current repository layout: numbered chapter files.
    find "$BOOK_DIR" -maxdepth 1 -type f -name '[0-9][0-9]-*.md' -printf '%f\n' | sort
  fi
}

: > "$COMBINED_MD"

mapfile -t CHAPTERS < <(collect_chapters)
if [[ "${#CHAPTERS[@]}" -eq 0 ]]; then
  echo "No chapters found. Add $BOOK_DIR/chapters.txt or numbered chapter files like 00-introduction.md." >&2
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
  --lua-filter "$LUA_FILTER" \
  -o "$BODY_TYP" \
  "$COMBINED_MD"

FRONT_MATTER_SRC="$BOOK_DIR/front-matter-print.typ"
FRONT_MATTER_BUILD="$BUILD_DIR/front-matter-print.typ"

{
  printf '#import "book.typ" as book\n'
  printf '#show: book.setup.with(title: "%s")\n\n' "$(typst_escape "$BOOK_TITLE")"

  if [[ "$MODE" == "print" ]]; then
    if [[ -f "$FRONT_MATTER_SRC" ]]; then
      cp "$FRONT_MATTER_SRC" "$FRONT_MATTER_BUILD"
      printf '#include "front-matter-print.typ"\n\n'
      TOC_SRC="$SCRIPTS_DIR/toc-print.typ"
      cp "$TOC_SRC" "$BUILD_DIR/toc-print.typ"
      printf '#include "toc-print.typ"\n\n'
    else
      # Fallback: use the built-in front_matter() function for books
      # that do not yet have a front-matter-print.typ.
      printf '#book.front_matter(\n'
      printf '  title: "%s",\n' "$(typst_escape "$BOOK_TITLE")"
      printf '  subtitle: "%s",\n' "$(typst_escape "$BOOK_SUBTITLE")"
      printf '  author: "%s",\n' "$(typst_escape "$BOOK_AUTHOR")"
      printf '  copyright_year: "%s",\n' "$(typst_escape "$BOOK_COPYRIGHT_YEAR")"
      printf '  hardcover_isbn: "%s",\n' "$(typst_escape "$BOOK_HARDCOVER_ISBN")"
      printf '  paperback_isbn: "%s",\n' "$(typst_escape "$BOOK_PAPERBACK_ISBN")"
      printf ')\n\n'
    fi
  fi

  cat "$BODY_TYP"
} > "$GENERATED_TYP"

typst compile \
  --root "$ROOT" \
  "$GENERATED_TYP" \
  "$OUTPUT_PDF"

echo "Built: $OUTPUT_PDF"
