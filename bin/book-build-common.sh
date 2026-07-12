#!/usr/bin/env bash
# Shared setup for the PDF, DOCX, and EPUB builders.

book_build_init() {
  local book="${1:-}"
  [[ -n "$book" ]] || { echo "Usage: $0 <book-dir>" >&2; return 2; }

  ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
  BOOK_NAME="${book#./}"
  BOOK_DIR="$ROOT/$BOOK_NAME"
  BIN_DIR="$ROOT/tools/bin"
  DIST_DIR="$ROOT/dist"
  BOOK_ENV="$BOOK_DIR/book.env"

  [[ -d "$BOOK_DIR" ]] || { echo "ERROR: Missing book dir: $BOOK_DIR" >&2; return 1; }
  [[ -f "$BOOK_ENV" ]] || { echo "ERROR: Missing $BOOK_ENV." >&2; return 1; }

  # shellcheck disable=SC1090
  source "$BOOK_ENV"

  local var
  for var in BOOK_TITLE BOOK_SUBTITLE BOOK_OUTPUT_BASENAME BOOK_AUTHOR BOOK_COPYRIGHT_YEAR; do
    [[ -n "${!var:-}" ]] || { echo "ERROR: $BOOK_ENV must define $var." >&2; return 1; }
  done

  : "${BOOK_HARDCOVER_ISBN:=}"
  : "${BOOK_PAPERBACK_ISBN:=}"
  : "${BOOK_SCRIPTURE_NOTICE:=}"
  : "${BOOKLET_SOURCE_TITLE:=}"
  mkdir -p "$DIST_DIR"
  cd "$ROOT"
}

require_files() {
  local path
  for path in "$@"; do
    [[ -f "$path" ]] || { echo "ERROR: Missing required file: $path" >&2; return 1; }
  done
}

collect_markdown_inputs() {
  local front_matter="$1"
  local -n result="$2"
  local chapter

  result=("$front_matter")
  while IFS= read -r chapter; do
    result+=("$BOOK_DIR/$chapter")
  done < <(find "$BOOK_DIR" -maxdepth 1 -type f -name '[0-9][0-9]-*.md' -printf '%f\n' | sort)

  [[ ${#result[@]} -gt 1 ]] || {
    echo "ERROR: No chapter files found in $BOOK_DIR (expected NN-*.md)." >&2
    return 1
  }
}

render_front_matter() {
  local src="$1"
  local dst="$2"

  FRONT_MATTER="$src" RENDERED_FRONT_MATTER="$dst" \
  BOOK_TITLE="$BOOK_TITLE" BOOK_SUBTITLE="$BOOK_SUBTITLE" \
  BOOK_OUTPUT_BASENAME="$BOOK_OUTPUT_BASENAME" BOOK_AUTHOR="$BOOK_AUTHOR" \
  BOOK_COPYRIGHT_YEAR="$BOOK_COPYRIGHT_YEAR" \
  BOOK_HARDCOVER_ISBN="$BOOK_HARDCOVER_ISBN" \
  BOOK_PAPERBACK_ISBN="$BOOK_PAPERBACK_ISBN" \
  python3 - <<'PY'
from pathlib import Path
import os

text = Path(os.environ["FRONT_MATTER"]).read_text(encoding="utf-8")
for name in (
    "BOOK_TITLE", "BOOK_SUBTITLE", "BOOK_OUTPUT_BASENAME", "BOOK_AUTHOR",
    "BOOK_COPYRIGHT_YEAR", "BOOK_HARDCOVER_ISBN", "BOOK_PAPERBACK_ISBN",
):
    text = text.replace(f"{{{{{name}}}}}", os.environ[name])
Path(os.environ["RENDERED_FRONT_MATTER"]).write_text(text, encoding="utf-8")
PY
}
