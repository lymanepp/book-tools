#!/usr/bin/env python3
"""
build-book.py — Orchestrate print-PDF, cover, DOCX, and EPUB builds.

This is the project-level wrapper. The lower-level scripts keep their narrow
jobs:

  pdf.sh              builds one normal book interior PDF
  booklet.py          assembles/builds one booklet interior PDF
  render-cover.py     builds cover PDFs
  docx.sh             builds one submission DOCX
  epub.sh             builds one EPUB

The target directory must contain book.env. Build decisions are driven by that
file, with command-line flags available for one-off overrides.

Examples:
  python3 tools/bin/build-book.py book1 --renderer weasyprint
  python3 tools/bin/build-book.py book2 --pdf --covers
  python3 tools/bin/build-book.py booklets/marriage-and-family
  python3 tools/bin/build-book.py book1 --covers --bindings "paperback hardcover"
  python3 tools/bin/build-book.py book1 --dry-run

With no positive product-selection flags, the wrapper builds every product
enabled by book.env. --all is an explicit alias for the same configured build.
Positive flags such as --pdf or --covers narrow the build to only those
products unless --all is also given. Negative flags such as --no-covers subtract
from either mode.

book.env fields used by this wrapper:
  BOOK_TITLE                 Human-readable title for logs
  BOOK_OUTPUT_BASENAME       Output filename base, e.g. what-scripture-says-vol1

  BOOK_BUILD_PDF             true/false; default true
  BOOK_BUILD_DOCX            true/false; default auto
  BOOK_BUILD_EPUB            true/false; default auto
  BOOK_BUILD_COVERS          true/false; default true when cover template exists

  BOOK_COVER_TEMPLATE        defaults to cover.html
  BOOK_COVER_BINDINGS        defaults to "paperback hardcover"
  BOOK_COVER_PAPER           consumed by render-cover.py unless --paper overrides

Booklet targets use the same BOOK_* identity/output fields and add:
  BOOKLET_CHAPTERS           when present, PDF builds go through booklet.py
"""

from __future__ import annotations

import argparse
import os
import shlex
import subprocess
import sys
from pathlib import Path

from book_tools_common import load_env, repo_root, resolve_under


TRUE_VALUES = {"1", "true", "yes", "y", "on"}
FALSE_VALUES = {"0", "false", "no", "n", "off"}
VALID_BINDINGS = {"paperback", "hardcover"}





def rel(root: Path, path: Path) -> str:
    try:
        return str(path.resolve().relative_to(root))
    except ValueError:
        return str(path)


def parse_bool(value: str | None, default: bool, var_name: str) -> bool:
    if value is None or value == "":
        return default
    normalized = value.strip().lower()
    if normalized in TRUE_VALUES:
        return True
    if normalized in FALSE_VALUES:
        return False
    raise SystemExit(
        f"ERROR: {var_name} must be true/false, yes/no, on/off, or 1/0; got {value!r}."
    )


def auto_docx_enabled(book_dir: Path, is_booklet: bool) -> bool:
    return (
        not is_booklet
        and (book_dir / "front-matter-submission.md").is_file()
        and (book_dir / "metadata-submission.yaml").is_file()
    )


def auto_epub_enabled(book_dir: Path, is_booklet: bool) -> bool:
    return auto_docx_enabled(book_dir, is_booklet)


def cover_template_exists(book_dir: Path, env: dict[str, str]) -> bool:
    template = env.get("BOOK_COVER_TEMPLATE", "cover.html") or "cover.html"
    path = Path(template).expanduser()
    if not path.is_absolute():
        path = book_dir / path
    return path.is_file()


def parse_bindings(value: str) -> list[str]:
    try:
        parts = shlex.split(value, comments=False, posix=True)
    except ValueError as e:
        raise SystemExit(f"ERROR: Could not parse cover bindings {value!r}: {e}") from e
    if not parts:
        raise SystemExit("ERROR: Cover binding list is empty.")
    bad = [b for b in parts if b not in VALID_BINDINGS]
    if bad:
        raise SystemExit(
            "ERROR: Unsupported cover binding(s): "
            + ", ".join(bad)
            + ". Use paperback and/or hardcover."
        )
    # Preserve order while de-duplicating.
    result: list[str] = []
    for part in parts:
        if part not in result:
            result.append(part)
    return result


def run(cmd: list[str], root: Path, dry_run: bool, env: dict[str, str] | None = None) -> None:
    printable = " ".join(shlex.quote(c) for c in cmd)
    print(f"\n$ {printable}", flush=True)
    if dry_run:
        return
    result = subprocess.run(cmd, cwd=str(root), check=False, env=env)
    if result.returncode != 0:
        raise SystemExit(result.returncode)


def output_pdf(root: Path, env: dict[str, str]) -> Path:
    return root / "dist" / f"{env['BOOK_OUTPUT_BASENAME']}-print.pdf"


def output_docx(root: Path, env: dict[str, str]) -> Path:
    return root / "dist" / f"{env['BOOK_OUTPUT_BASENAME']}-submission.docx"


def output_epub(root: Path, env: dict[str, str]) -> Path:
    return root / "dist" / f"{env['BOOK_OUTPUT_BASENAME']}.epub"


def output_cover(root: Path, env: dict[str, str], binding: str, preview: bool) -> Path:
    suffix = "-preview" if preview else ""
    return root / "dist" / f"{env['BOOK_OUTPUT_BASENAME']}-{binding}-cover{suffix}.pdf"


def configured_products(book_dir: Path, env: dict[str, str]) -> dict[str, bool]:
    is_booklet = bool(env.get("BOOKLET_CHAPTERS"))
    return {
        "pdf": parse_bool(env.get("BOOK_BUILD_PDF"), True, "BOOK_BUILD_PDF"),
        "covers": parse_bool(
            env.get("BOOK_BUILD_COVERS"),
            cover_template_exists(book_dir, env),
            "BOOK_BUILD_COVERS",
        ),
        "docx": parse_bool(
            env.get("BOOK_BUILD_DOCX"),
            auto_docx_enabled(book_dir, is_booklet),
            "BOOK_BUILD_DOCX",
        ),
        "epub": parse_bool(
            env.get("BOOK_BUILD_EPUB"),
            auto_epub_enabled(book_dir, is_booklet),
            "BOOK_BUILD_EPUB",
        ),
    }


def choose_products(args: argparse.Namespace, book_dir: Path, env: dict[str, str]) -> dict[str, bool]:
    positive_selection = args.pdf or args.covers or args.docx or args.epub

    if args.all or not positive_selection:
        # No positive product-selection flags means: build what book.env enables.
        # --all is retained as a readable explicit alias for this default behavior.
        products = configured_products(book_dir, env)
    else:
        # Explicit positive product flags narrow the build to only those products.
        products = {
            "pdf": bool(args.pdf),
            "covers": bool(args.covers),
            "docx": bool(args.docx),
            "epub": bool(args.epub),
        }

    if args.no_pdf:
        products["pdf"] = False
    if args.no_covers:
        products["covers"] = False
    if args.no_docx:
        products["docx"] = False
    if args.no_epub:
        products["epub"] = False

    return products


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("book_dir", help="Book/booklet directory containing book.env")

    product = parser.add_argument_group("products")
    product.add_argument("--all", action="store_true", help="Build all products enabled by book.env. This is also the default when no positive product flags are given.")
    product.add_argument("--pdf", action="store_true", help="Build the interior print PDF.")
    product.add_argument("--covers", action="store_true", help="Build cover PDFs.")
    product.add_argument("--docx", action="store_true", help="Build the submission DOCX.")
    product.add_argument("--epub", action="store_true", help="Build the EPUB.")
    product.add_argument("--no-pdf", action="store_true", help="Skip the interior print PDF.")
    product.add_argument("--no-covers", action="store_true", help="Skip cover PDFs.")
    product.add_argument("--no-docx", action="store_true", help="Skip the submission DOCX.")
    product.add_argument("--no-epub", action="store_true", help="Skip the EPUB.")

    covers = parser.add_argument_group("cover options")
    covers.add_argument(
        "--bindings",
        default=None,
        help="Space-separated cover bindings. Overrides BOOK_COVER_BINDINGS. Default: 'paperback hardcover'.",
    )
    covers.add_argument("--paper", choices=["cream", "white"], default=None, help="Override BOOK_COVER_PAPER.")
    covers.add_argument("--renderer", choices=["auto", "weasyprint", "wkhtmltopdf", "chrome", "chromium"], default="auto")
    covers.add_argument("--preview", action="store_true", help="Ask render-cover.py for preview PDFs.")

    release = parser.add_argument_group("publication metadata")
    release.add_argument("--release", action="store_true", help="Require a clean, tagged release build.")
    release.add_argument("--release-tag", default=None, help="Release tag, e.g. book1-v1.0.0. Normally inferred from HEAD.")
    release.add_argument("--release-date", default=None, help="ISO publication date. Defaults to tagged commit date.")
    release.add_argument("--no-finalize", action="store_true", help="Do not write manifest and checksums after the build.")
    parser.add_argument("--dry-run", action="store_true", help="Print commands without running them.")
    args = parser.parse_args()

    root = repo_root()
    book_dir = resolve_under(root, args.book_dir)
    env_path = book_dir / "book.env"

    if not book_dir.is_dir():
        raise SystemExit(f"ERROR: Missing book directory: {book_dir}")
    if not env_path.is_file():
        raise SystemExit(f"ERROR: Missing {env_path}")

    env = load_env(env_path)
    for required in ("BOOK_TITLE", "BOOK_OUTPUT_BASENAME"):
        if not env.get(required):
            raise SystemExit(f"ERROR: {env_path} must define {required}.")

    is_booklet = bool(env.get("BOOKLET_CHAPTERS"))
    products = choose_products(args, book_dir, env)
    bindings = parse_bindings(args.bindings or env.get("BOOK_COVER_BINDINGS", "paperback hardcover"))

    publication_cmd = ["python3", "tools/bin/publication.py", "prepare", rel(root, book_dir)]
    if args.release:
        publication_cmd.append("--release")
    if args.release_tag:
        publication_cmd.extend(["--tag", args.release_tag])
    if args.release_date:
        publication_cmd.extend(["--date", args.release_date])
    run(publication_cmd, root, args.dry_run)

    print(f"Building target: {env['BOOK_TITLE']}", flush=True)
    print(f"Directory:       {rel(root, book_dir)}", flush=True)
    print(f"Kind:            {'booklet' if is_booklet else 'book'}", flush=True)
    print(
        "Products:        "
        + ", ".join(name for name, enabled in products.items() if enabled)
        if any(products.values())
        else "Products:        none",
        flush=True,
    )

    interior_pdf = output_pdf(root, env)

    if products["pdf"]:
        if is_booklet:
            run(["python3", "tools/bin/booklet.py", rel(root, book_dir)], root, args.dry_run)
        else:
            run(["bash", "tools/bin/pdf.sh", rel(root, book_dir)], root, args.dry_run)

    if products["covers"]:
        cover_cmd_base = [
            "python3",
            "tools/bin/render-cover.py",
            rel(root, book_dir),
            "--renderer",
            args.renderer,
        ]
        if args.preview:
            cover_cmd_base.append("--preview")
        if args.paper:
            cover_cmd_base.extend(["--paper", args.paper])

        # Prefer the freshly built or pre-existing interior PDF so spine width is exact.
        # In dry-run mode, show the intended final command even if the PDF does not exist yet.
        if args.dry_run or interior_pdf.is_file():
            cover_cmd_base.extend(["--pdf", rel(root, interior_pdf)])

        for binding in bindings:
            run(cover_cmd_base + ["--binding", binding], root, args.dry_run)

    if products["docx"]:
        run(["bash", "tools/bin/docx.sh", rel(root, book_dir)], root, args.dry_run)

    if products["epub"]:
        run(["bash", "tools/bin/epub.sh", rel(root, book_dir)], root, args.dry_run)

    if not args.no_finalize and any(products.values()):
        run(["python3", "tools/bin/publication.py", "finalize", rel(root, book_dir)], root, args.dry_run)

    print("\nExpected artifacts:")
    if products["pdf"]:
        print(f"  - {rel(root, interior_pdf)}")
    if products["covers"]:
        for binding in bindings:
            print(f"  - {rel(root, output_cover(root, env, binding, args.preview))}")
    if products["docx"]:
        print(f"  - {rel(root, output_docx(root, env))}")
    if products["epub"]:
        print(f"  - {rel(root, output_epub(root, env))}")

    print("\nDone." if not args.dry_run else "\nDry run complete.")


if __name__ == "__main__":
    main()
