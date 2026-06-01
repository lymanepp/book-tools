#!/usr/bin/env python3
"""
build-booklet.py — Compile a WSS booklet PDF via the Typst pipeline.

Each booklet lives in booklets/<name>/booklet.env. The script reads all
configuration from that file and produces output identical in format to
the full books (same Typst template, same running heads, same front matter
structure).

Usage:
    python3 build-booklet.py <booklet-name>
    python3 build-booklet.py marriage-and-manhood

booklet.env fields:
    BOOKLET_TITLE             Displayed title
    BOOKLET_SUBTITLE          Displayed subtitle
    BOOKLET_OUTPUT_BASENAME   Output filename base (no extension)
    BOOKLET_AUTHOR            Author name
    BOOKLET_COPYRIGHT_YEAR    Four-digit year
    BOOKLET_HARDCOVER_ISBN    ISBN-13, or empty string
    BOOKLET_PAPERBACK_ISBN    ISBN-13, or empty string
    BOOKLET_CHAPTERS          Space-separated chapter specs, e.g. '1:7 2:4-7'

Chapter spec syntax:
    1:7        Book 1, chapter 7
    2:4-7      Book 2, chapters 4 through 7
    2:4,6,7    Book 2, chapters 4, 6, and 7
"""

import argparse
import glob
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

# ── paths ────────────────────────────────────────────────────────────────────

def _find_repo_root() -> Path:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True, text=True, check=True,
        )
        return Path(result.stdout.strip())
    except subprocess.CalledProcessError:
        # Fallback: script location (matches pdf.sh fallback behavior)
        return Path(__file__).parent

ROOT = _find_repo_root()
BOOK_DIRS = {1: ROOT / "book1", 2: ROOT / "book2"}
BOOKLETS_DIR = ROOT / "booklets"
SCRIPTS_DIR = ROOT / "tools" / "scripts"
PDF_SH = SCRIPTS_DIR / "pdf.sh"

# ── config ───────────────────────────────────────────────────────────────────

REQUIRED_FIELDS = [
    "BOOKLET_TITLE",
    "BOOKLET_SUBTITLE",
    "BOOKLET_OUTPUT_BASENAME",
    "BOOKLET_AUTHOR",
    "BOOKLET_COPYRIGHT_YEAR",
    "BOOKLET_CHAPTERS",
]

OPTIONAL_FIELDS = {
    "BOOKLET_HARDCOVER_ISBN": "",
    "BOOKLET_PAPERBACK_ISBN": "",
    "BOOKLET_INTRO": "",
}


def load_env(path: Path) -> dict[str, str]:
    """Parse a shell-style key='value' env file. Returns a dict of strings."""
    env = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, _, raw = line.partition("=")
        key = key.strip()
        # Strip surrounding quotes (single or double)
        value = raw.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
            value = value[1:-1]
        env[key] = value
    return env


def validate_config(cfg: dict[str, str], env_path: Path) -> None:
    missing = [f for f in REQUIRED_FIELDS if not cfg.get(f)]
    if missing:
        print(f"ERROR: {env_path} is missing required fields: {', '.join(missing)}", file=sys.stderr)
        sys.exit(1)


# ── chapter discovery ────────────────────────────────────────────────────────

def find_chapter_file(book: int, chapter: int) -> Path:
    book_dir = BOOK_DIRS.get(book)
    if not book_dir or not book_dir.is_dir():
        raise FileNotFoundError(f"Book {book} directory not found: {book_dir}")
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
        text, count=1, flags=re.MULTILINE
    )


# ── front-matter-print.typ ───────────────────────────────────────────────────

def make_front_matter(title: str, subtitle: str, author: str, year: str,
                      hardcover_isbn: str, paperback_isbn: str) -> str:
    def esc(s):
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
// front-matter-print.typ — Booklet front matter (generated by build-booklet.py)
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
  [This booklet is excerpted from _What Scripture Says_ by {esc(author)}. No part of this publication may be reproduced, stored in a retrieval system, or transmitted in any form or by any means without the prior written permission of the author, except for brief quotations used in reviews or scholarly works.]
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

def main():
    parser = argparse.ArgumentParser(
        description="Build a WSS booklet PDF from booklets/<name>/booklet.env.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("booklet", help="Booklet name (subdirectory under booklets/)")
    args = parser.parse_args()

    # Load config
    booklet_dir = BOOKLETS_DIR / args.booklet
    env_path = booklet_dir / "booklet.env"
    if not env_path.exists():
        print(f"ERROR: No booklet.env found at {env_path}", file=sys.stderr)
        available = sorted(p.name for p in BOOKLETS_DIR.iterdir() if p.is_dir()) if BOOKLETS_DIR.exists() else []
        if available:
            print(f"Available booklets: {', '.join(available)}", file=sys.stderr)
        sys.exit(1)

    cfg = {**OPTIONAL_FIELDS, **load_env(env_path)}
    validate_config(cfg, env_path)

    title          = cfg["BOOKLET_TITLE"]
    subtitle       = cfg["BOOKLET_SUBTITLE"]
    basename       = cfg["BOOKLET_OUTPUT_BASENAME"]
    author         = cfg["BOOKLET_AUTHOR"]
    year           = cfg["BOOKLET_COPYRIGHT_YEAR"]
    hardcover_isbn = cfg["BOOKLET_HARDCOVER_ISBN"]
    paperback_isbn = cfg["BOOKLET_PAPERBACK_ISBN"]
    chapters_str   = cfg["BOOKLET_CHAPTERS"]
    intro_file     = cfg["BOOKLET_INTRO"]

    # Resolve chapter list
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
            print(f"  00-intro.md ← booklets/{args.booklet}/{intro_file}")

        # Copy and renumber chapters
        for booklet_num, (book, ch) in enumerate(pairs, start=1):
            try:
                src = find_chapter_file(book, ch)
            except FileNotFoundError as e:
                print(f"ERROR: {e}", file=sys.stderr)
                sys.exit(1)
            text = src.read_text(encoding="utf-8")
            text = rewrite_chapter_number(text, booklet_num)
            dest = fake_book / f"{booklet_num:02d}-ch{booklet_num}.md"
            dest.write_text(text, encoding="utf-8")
            print(f"  {dest.name} ← book{book}/{src.name}")

        # Apply surgical edits if edits.sed exists in the booklet directory
        edits_sed = booklet_dir / "edits.sed"
        if edits_sed.exists():
            print("  Applying edits.sed...")
            md_files = sorted(str(f) for f in fake_book.glob("*.md"))
            result_sed = subprocess.run(
                ["sed", "-E", "-i", f"--file={edits_sed}"] + md_files,
                check=False,
            )
            if result_sed.returncode != 0:
                print(f"ERROR: sed exited with code {result_sed.returncode}", file=sys.stderr)
                sys.exit(result_sed.returncode)

        # Write book.env (pdf.sh sources this)
        (fake_book / "book.env").write_text(
            f"BOOK_TITLE='{title}'\n"
            f"BOOK_SUBTITLE='{subtitle}'\n"
            f"BOOK_OUTPUT_BASENAME='{basename}'\n"
            f"BOOK_AUTHOR='{author}'\n"
            f"BOOK_COPYRIGHT_YEAR={year}\n"
            f"BOOK_HARDCOVER_ISBN='{hardcover_isbn}'\n"
            f"BOOK_PAPERBACK_ISBN='{paperback_isbn}'\n",
            encoding="utf-8",
        )

        # Write front-matter-print.typ
        (fake_book / "front-matter-print.typ").write_text(
            make_front_matter(title, subtitle, author, year, hardcover_isbn, paperback_isbn),
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
