#!/usr/bin/env python3
"""
booklet.py — Compile a WSS booklet PDF via the same Typst pipeline as books.

Each booklet lives in booklets/<name>/book.env. Identity and output metadata
use the same BOOK_* variables consumed by pdf.sh and render-cover.py. The only
booklet-specific fields are the source-selection fields used to assemble the
temporary book directory before handing off to pdf.sh.

Usage:
    python3 tools/bin/booklet.py marriage-and-family
    python3 tools/bin/booklet.py booklets/marriage-and-family

book.env fields:
    BOOK_TITLE                Displayed title
    BOOK_SUBTITLE             Displayed subtitle
    BOOK_OUTPUT_BASENAME      Output filename base (no extension)
    BOOK_AUTHOR               Author name
    BOOK_COPYRIGHT_YEAR       Four-digit year
    BOOK_HARDCOVER_ISBN       ISBN-13, or empty string (optional)
    BOOK_PAPERBACK_ISBN       ISBN-13, or empty string (optional)
    BOOKLET_SOURCE_TITLE      Parent/source work title used in generated front matter
    BOOKLET_SOURCE_BOOKS      Source map, e.g. '1:book1 2:book2'
    BOOKLET_CHAPTERS          Space-separated chapter specs, e.g. '1:7 2:4-7'
    BOOKLET_INTRO             Intro Markdown file relative to booklet dir (optional)

Chapter spec syntax:
    1:7        Book 1, chapter 7
    2:4-7      Book 2, chapters 4 through 7
    2:4,6,7    Book 2, chapters 4, 6, and 7
"""

import argparse
import glob
import os
import re
import shlex
import shutil
import subprocess
import sys
from pathlib import Path


# ── paths ────────────────────────────────────────────────────────────────────

def _find_repo_root() -> Path:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            check=True,
        )
        return Path(result.stdout.strip()).resolve()
    except (subprocess.CalledProcessError, FileNotFoundError):
        # python3 tools/bin/booklet.py -> repo root is two parents up.
        return Path(__file__).resolve().parents[2]


ROOT = _find_repo_root()
BOOKLETS_DIR = ROOT / "booklets"
BIN_DIR = Path(__file__).resolve().parent
PDF_SH = BIN_DIR / "pdf.sh"


# ── config ───────────────────────────────────────────────────────────────────

REQUIRED_FIELDS = [
    "BOOK_TITLE",
    "BOOK_SUBTITLE",
    "BOOK_OUTPUT_BASENAME",
    "BOOK_AUTHOR",
    "BOOK_COPYRIGHT_YEAR",
    "BOOKLET_CHAPTERS",
    "BOOKLET_SOURCE_TITLE",
    "BOOKLET_SOURCE_BOOKS",
]

DEFAULT_FIELDS = {
    "BOOK_HARDCOVER_ISBN": "",
    "BOOK_PAPERBACK_ISBN": "",
    "BOOKLET_INTRO": "",
}


def load_env(path: Path) -> dict[str, str]:
    """Parse a shell-style key=value env file. Returns a dict of strings."""
    env: dict[str, str] = {}
    for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped.startswith("export "):
            stripped = stripped[len("export "):].lstrip()
        if "=" not in stripped:
            continue
        key, _, raw = stripped.partition("=")
        key = key.strip()
        raw = raw.strip()
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", key):
            print(f"ERROR: Invalid env key in {path}:{lineno}: {key}", file=sys.stderr)
            sys.exit(1)
        try:
            value = shlex.split(raw, comments=False, posix=True)[0] if raw else ""
        except ValueError as e:
            print(f"ERROR: Could not parse {path}:{lineno}: {e}", file=sys.stderr)
            sys.exit(1)
        env[key] = value
    return env


def validate_config(cfg: dict[str, str], env_path: Path) -> None:
    missing = [f for f in REQUIRED_FIELDS if not cfg.get(f)]
    if missing:
        print(f"ERROR: {env_path} is missing required fields: {', '.join(missing)}", file=sys.stderr)
        sys.exit(1)


def resolve_under_root(value: str) -> Path:
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = ROOT / path
    return path.resolve()


def parse_source_books(value: str, env_path: Path) -> dict[int, Path]:
    """Parse BOOKLET_SOURCE_BOOKS='1:book1 2:book2'."""
    source_books: dict[int, Path] = {}
    for token in value.split():
        if ":" not in token:
            print(
                f"ERROR: Invalid BOOKLET_SOURCE_BOOKS token in {env_path}: {token!r}. "
                "Use NUMBER:directory, e.g. 1:book1.",
                file=sys.stderr,
            )
            sys.exit(1)
        number_raw, dir_raw = token.split(":", 1)
        try:
            number = int(number_raw)
        except ValueError:
            print(f"ERROR: Invalid source-book number in {env_path}: {number_raw!r}", file=sys.stderr)
            sys.exit(1)
        if number < 1:
            print(f"ERROR: Source-book numbers must be positive in {env_path}: {number}", file=sys.stderr)
            sys.exit(1)
        source_dir = resolve_under_root(dir_raw)
        if not source_dir.is_dir():
            print(f"ERROR: Source-book directory not found for {number}: {source_dir}", file=sys.stderr)
            sys.exit(1)
        source_books[number] = source_dir

    if not source_books:
        print(f"ERROR: BOOKLET_SOURCE_BOOKS in {env_path} produced no source books.", file=sys.stderr)
        sys.exit(1)
    return source_books


def shell_quote(value: str) -> str:
    """Single-quote for a POSIX shell env file."""
    return "'" + value.replace("'", "'\\''") + "'"


def write_book_env(path: Path, cfg: dict[str, str]) -> None:
    """Write only BOOK_* fields to the temporary book.env consumed by pdf.sh."""
    lines = []
    for key in sorted(k for k in cfg if k.startswith("BOOK_")):
        lines.append(f"{key}={shell_quote(str(cfg[key]))}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


# ── chapter discovery ────────────────────────────────────────────────────────

def find_chapter_file(source_books: dict[int, Path], book: int, chapter: int) -> Path:
    book_dir = source_books.get(book)
    if not book_dir:
        available = ", ".join(str(n) for n in sorted(source_books))
        raise FileNotFoundError(
            f"Book {book} is not mapped in BOOKLET_SOURCE_BOOKS. Available: {available}"
        )
    pattern = str(book_dir / f"{chapter:02d}-*.md")
    matches = sorted(glob.glob(pattern))
    if not matches:
        raise FileNotFoundError(
            f"No file for book {book}, chapter {chapter} (pattern: {pattern})"
        )
    return Path(matches[0])


def parse_spec(spec: str) -> list[tuple[int, int]]:
    m = re.fullmatch(r"(\d+):(.+)", spec)
    if not m:
        raise ValueError(f"Invalid spec '{spec}'. Use BOOK:CHAPTER(S), e.g. 1:7 or 2:4-7")
    book = int(m.group(1))
    chapters = []
    for token in m.group(2).split(","):
        token = token.strip()
        if "-" in token:
            start, end = token.split("-", 1)
            chapters.extend(range(int(start), int(end) + 1))
        else:
            chapters.append(int(token))
    return [(book, ch) for ch in chapters]


def resolve_chapters(chapters_str: str) -> list[tuple[int, int]]:
    pairs = []
    for spec in chapters_str.split():
        pairs.extend(parse_spec(spec))
    return pairs


# ── chapter heading rewrite ──────────────────────────────────────────────────

def rewrite_chapter_number(text: str, new_number: int) -> str:
    """Rewrite '# N. Title ...' to '# NEW_N. Title ...' on the first H1."""
    return re.sub(
        r"^# \d+\.\s+(.+)$",
        lambda m: f"# {new_number}. {m.group(1)}",
        text,
        count=1,
        flags=re.MULTILINE,
    )


# ── strict sed edit validation/application ───────────────────────────────────

def active_sed_rules(sed_path: Path) -> list[tuple[int, str]]:
    """Return active, single-line sed rules from edits.sed.

    Blank lines and comment lines are ignored. The booklet build intentionally
    supports only one surgical edit per active line so stale edits can be caught
    precisely.
    """
    rules: list[tuple[int, str]] = []
    for lineno, line in enumerate(sed_path.read_text(encoding="utf-8").splitlines(), start=1):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        rules.append((lineno, stripped))
    return rules


def find_unescaped_delimiter(text: str, delimiter: str, start: int) -> int:
    """Find delimiter not escaped by a backslash in a sed command string."""
    escaped = False
    for index in range(start, len(text)):
        char = text[index]
        if escaped:
            escaped = False
            continue
        if char == "\\":
            escaped = True
            continue
        if char == delimiter:
            return index
    return -1


def sed_count_command(rule: str, sed_path: Path, lineno: int) -> str:
    """Convert a supported sed edit rule into a sed -n command that prints affected lines."""
    if rule.startswith("s"):
        if len(rule) < 4:
            raise ValueError(f"{sed_path}:{lineno}: malformed substitution rule: {rule}")
        delimiter = rule[1]
        if delimiter.isspace():
            raise ValueError(f"{sed_path}:{lineno}: malformed substitution delimiter: {rule}")
        first = find_unescaped_delimiter(rule, delimiter, 2)
        if first == -1:
            raise ValueError(f"{sed_path}:{lineno}: substitution is missing pattern delimiter: {rule}")
        second = find_unescaped_delimiter(rule, delimiter, first + 1)
        if second == -1:
            raise ValueError(f"{sed_path}:{lineno}: substitution is missing replacement delimiter: {rule}")
        flags = rule[second + 1:]
        if not re.fullmatch(r"[0-9gIpM]*", flags):
            raise ValueError(
                f"{sed_path}:{lineno}: unsupported substitution flags {flags!r}; "
                "supported flags are digits, g, I, p, and M."
            )
        if "p" not in flags:
            flags += "p"
        return rule[:second + 1] + flags

    if rule.startswith("/"):
        end = find_unescaped_delimiter(rule, "/", 1)
        if end == -1:
            raise ValueError(f"{sed_path}:{lineno}: deletion rule is missing closing delimiter: {rule}")
        suffix = rule[end + 1:]
        if suffix != "d":
            raise ValueError(
                f"{sed_path}:{lineno}: unsupported sed address command {suffix!r}; "
                "only /PATTERN/d is supported."
            )
        return rule[:end + 1] + "p"

    raise ValueError(
        f"{sed_path}:{lineno}: unsupported sed rule: {rule!r}. "
        "Use one s/PATTERN/REPLACEMENT/FLAGS rule or one /PATTERN/d rule per line."
    )


def count_sed_rule_matches(rule: str, sed_path: Path, lineno: int, md_files: list[str]) -> tuple[int, list[str]]:
    """Count how many current Markdown lines would be affected by one sed rule."""
    count_command = sed_count_command(rule, sed_path, lineno)
    result = subprocess.run(
        ["sed", "-n", "-E", count_command] + md_files,
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        message = result.stderr.strip() or result.stdout.strip() or f"sed exited with code {result.returncode}"
        raise RuntimeError(f"{sed_path}:{lineno}: could not validate sed rule: {message}")
    matched_lines = result.stdout.splitlines()
    return len(matched_lines), matched_lines


def apply_sed_edits_strict(sed_path: Path, md_files: list[str]) -> None:
    """Apply edits.sed, failing if any active edit does not affect exactly one line.

    This catches stale booklet edits as soon as the source chapters drift. Each
    active edits.sed line is validated against the current temporary Markdown
    files, then applied before the next rule is checked, matching the intended
    surgical/sequential nature of these booklet edits.
    """
    rules = active_sed_rules(sed_path)
    if not rules:
        print("  No active edits.sed rules.")
        return

    for lineno, rule in rules:
        try:
            match_count, matched_lines = count_sed_rule_matches(rule, sed_path, lineno, md_files)
        except (ValueError, RuntimeError) as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            sys.exit(1)

        if match_count != 1:
            print(
                f"ERROR: {sed_path}:{lineno} matched {match_count} lines; expected exactly 1.",
                file=sys.stderr,
            )
            print(f"Rule: {rule}", file=sys.stderr)
            if matched_lines:
                print("Matched lines:", file=sys.stderr)
                for matched in matched_lines[:10]:
                    short = matched if len(matched) <= 180 else matched[:177] + "..."
                    print(f"  {short}", file=sys.stderr)
                if len(matched_lines) > 10:
                    print(f"  ... {len(matched_lines) - 10} more", file=sys.stderr)
            sys.exit(1)

        result = subprocess.run(
            ["sed", "-E", "-i", rule] + md_files,
            check=False,
        )
        if result.returncode != 0:
            print(f"ERROR: sed exited with code {result.returncode} at {sed_path}:{lineno}", file=sys.stderr)
            sys.exit(result.returncode)


# ── front-matter-print.typ ───────────────────────────────────────────────────

def make_front_matter(title: str, subtitle: str, author: str, year: str,
                      hardcover_isbn: str, paperback_isbn: str, source_title: str) -> str:
    def esc(s: str) -> str:
        return s.replace("\\", "\\\\").replace('"', '\\"')

    isbn_block = ""
    if hardcover_isbn or paperback_isbn:
        lines = []
        if hardcover_isbn:
            lines.append(f"  [ISBN: {esc(hardcover_isbn)} (hardcover)]")
            if paperback_isbn:
                lines.append("  linebreak()")
        if paperback_isbn:
            lines.append(f"  [ISBN: {esc(paperback_isbn)} (paperback)]")
        isbn_block = "\n  v(41.7pt)\n" + "\n".join(lines)

    return f"""\
// front-matter-print.typ — Booklet front matter (generated by booklet.py)
// Mirrors the 4-page structure of the real WSS book front-matter files.
// pdf.sh appends toc-print.typ (p5/recto + p6/verso) automatically.
#import "book.typ" as book

// ── Page 1: Title page (recto/odd) ───────────────────────────────────────────
#book._suppress.update(true)
#book._chapter_open_page.update(0)
#set align(center)
#v(42.6pt)
#{{
  set text(font: book._body-font, size: 20pt, weight: "bold")
  set par(justify: false, leading: book._leading, spacing: 0pt,
          first-line-indent: (amount: 0pt, all: true))
  [{esc(title)}]
}}
#v(32.5pt)
#{{
  set text(font: book._body-font, size: 12pt, weight: "bold", style: "italic")
  set par(justify: false, leading: book._leading, spacing: 0pt,
          first-line-indent: (amount: 0pt, all: true))
  [{esc(subtitle)}]
}}
#v(30.3pt)
#{{
  set text(font: book._body-font, size: 12pt, weight: "bold")
  set par(justify: false, leading: book._leading, spacing: 0pt,
          first-line-indent: (amount: 0pt, all: true))
  [{esc(author)}]
}}
#set align(left)

// ── Page 2: Blank verso ──────────────────────────────────────────────────────
#pagebreak(to: "even")
#book._suppress.update(true)
#book._chapter_open_page.update(0)

// ── Page 3: Copyright page (recto/odd) ───────────────────────────────────────
#pagebreak(to: "odd")
#book._suppress.update(true)
#book._chapter_open_page.update(0)
#v(15.1pt)
#{{
  set text(font: book._body-font, size: 11pt)
  set par(justify: false, leading: book._leading, spacing: 0pt,
          first-line-indent: (amount: 0pt, all: true))
  strong[{esc(title)}]
  v(30.8pt)
  emph[{esc(subtitle)}]
  v(41.7pt)
  [\\u{{00A9}} {esc(year)} {esc(author)}]
  v(41.8pt)
  [All rights reserved.]
  v(41.6pt)
  [This booklet is excerpted from ]
  emph[{esc(source_title)}]
  [ by {esc(author)}. No part of this publication may be reproduced, stored in a retrieval system, or transmitted in any form or by any means without the prior written permission of the author, except for brief quotations used in reviews or scholarly works.]
  v(41.7pt)
  [Scripture quotations are from the ESV\\u{{00AE}} Bible (The Holy Bible, English Standard Version\\u{{00AE}}), copyright \\u{{00A9}} 2001 by Crossway, a publishing ministry of Good News Publishers. Used by permission. All rights reserved.]{isbn_block}
  v(41.7pt)
  [Printed in the United States of America.]
}}

// ── Page 4: Blank verso ──────────────────────────────────────────────────────
#pagebreak(to: "even")
#book._suppress.update(true)
#book._chapter_open_page.update(0)

// pdf.sh emits TOC (p5/recto), blank (p6/verso), then pagebreak-to-odd before body.
"""


# ── main ─────────────────────────────────────────────────────────────────────

def resolve_booklet_dir(arg: str) -> Path:
    supplied = Path(arg)
    candidates = []
    if supplied.is_absolute():
        candidates.append(supplied)
    else:
        candidates.append((ROOT / supplied).resolve())
        candidates.append((BOOKLETS_DIR / supplied).resolve())

    for candidate in candidates:
        if candidate.is_dir():
            return candidate
    # Return the most likely path so the error is useful.
    return candidates[-1]


def rel(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(ROOT))
    except ValueError:
        return str(path)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build a WSS booklet PDF from booklets/<name>/book.env.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("booklet", help="Booklet name under booklets/, or path to a booklet directory")
    args = parser.parse_args()

    booklet_dir = resolve_booklet_dir(args.booklet)
    env_path = booklet_dir / "book.env"
    if not env_path.exists():
        print(f"ERROR: No book.env found at {env_path}", file=sys.stderr)
        available = sorted(p.name for p in BOOKLETS_DIR.iterdir() if p.is_dir()) if BOOKLETS_DIR.exists() else []
        if available:
            print(f"Available booklets: {', '.join(available)}", file=sys.stderr)
        sys.exit(1)

    cfg = {**DEFAULT_FIELDS, **load_env(env_path)}
    validate_config(cfg, env_path)

    title = cfg["BOOK_TITLE"]
    subtitle = cfg["BOOK_SUBTITLE"]
    basename = cfg["BOOK_OUTPUT_BASENAME"]
    author = cfg["BOOK_AUTHOR"]
    year = cfg["BOOK_COPYRIGHT_YEAR"]
    hardcover_isbn = cfg["BOOK_HARDCOVER_ISBN"]
    paperback_isbn = cfg["BOOK_PAPERBACK_ISBN"]
    chapters_str = cfg["BOOKLET_CHAPTERS"]
    intro_file = cfg["BOOKLET_INTRO"]
    source_title = cfg["BOOKLET_SOURCE_TITLE"]
    source_books = parse_source_books(cfg["BOOKLET_SOURCE_BOOKS"], env_path)

    try:
        pairs = resolve_chapters(chapters_str)
    except ValueError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)

    if not pairs:
        print("ERROR: BOOKLET_CHAPTERS produced no chapters.", file=sys.stderr)
        sys.exit(1)

    # Build fake book dir directly under ROOT (same level as book1, book2)
    # so pdf.sh BOOK_DIR="$ROOT/$BOOK_NAME" resolves without a symlink.
    fake_book = ROOT / "_booklet_tmp"
    if fake_book.exists():
        shutil.rmtree(fake_book)
    fake_book.mkdir()

    result = subprocess.CompletedProcess([], 1)
    try:
        # Copy intro (if any) as 00-intro.md — plain '# Title' heading renders
        # as front_chapter() (unnumbered, recto-opening, appears in TOC).
        if intro_file:
            intro_src = booklet_dir / intro_file
            if not intro_src.exists():
                print(f"ERROR: BOOKLET_INTRO file not found: {intro_src}", file=sys.stderr)
                sys.exit(1)
            dest = fake_book / "00-intro.md"
            dest.write_text(intro_src.read_text(encoding="utf-8"), encoding="utf-8")
            print(f"  00-intro.md ← {rel(intro_src)}")

        # Copy and renumber chapters.
        for booklet_num, (book, ch) in enumerate(pairs, start=1):
            try:
                src = find_chapter_file(source_books, book, ch)
            except FileNotFoundError as e:
                print(f"ERROR: {e}", file=sys.stderr)
                sys.exit(1)
            text = src.read_text(encoding="utf-8")
            text = rewrite_chapter_number(text, booklet_num)
            dest = fake_book / f"{booklet_num:02d}-ch{booklet_num}.md"
            dest.write_text(text, encoding="utf-8")
            print(f"  {dest.name} ← {rel(src)}")

        # Apply surgical edits if edits.sed exists in the booklet directory.
        edits_sed = booklet_dir / "edits.sed"
        if edits_sed.exists():
            print("  Validating/applying edits.sed...")
            md_files = sorted(str(f) for f in fake_book.glob("*.md"))
            apply_sed_edits_strict(edits_sed, md_files)

        write_book_env(fake_book / "book.env", cfg)
        (fake_book / "front-matter-print.typ").write_text(
            make_front_matter(title, subtitle, author, year, hardcover_isbn, paperback_isbn, source_title),
            encoding="utf-8",
        )

        print(f"\nBuilding: {title}")
        result = subprocess.run(
            ["bash", str(PDF_SH), "_booklet_tmp"],
            cwd=str(ROOT),
            check=False,
        )

    finally:
        shutil.rmtree(fake_book, ignore_errors=True)

    if result.returncode != 0:
        print(f"\nERROR: pdf.sh exited with code {result.returncode}", file=sys.stderr)
        sys.exit(result.returncode)

    out = ROOT / "dist" / f"{basename}-print.pdf"
    if out.exists():
        print(f"\n✓ Built: {out}")
    else:
        print(f"\nWARNING: Expected output not found at {out}", file=sys.stderr)


if __name__ == "__main__":
    main()
