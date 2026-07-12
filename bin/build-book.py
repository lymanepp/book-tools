#!/usr/bin/env python3
"""Build a configured book or booklet and its enabled publication products."""

from __future__ import annotations

import argparse
import shlex
import subprocess
from pathlib import Path

from book_tools_common import load_env, repo_root, resolve_under


TRUE_VALUES = {"1", "true", "yes", "y", "on"}
FALSE_VALUES = {"0", "false", "no", "n", "off"}
PRODUCTS = ("pdf", "covers", "docx", "epub")
VALID_BINDINGS = {"paperback", "hardcover"}


def rel(root: Path, path: Path) -> str:
    try:
        return str(path.resolve().relative_to(root))
    except ValueError:
        return str(path)


def parse_bool(value: str | None, default: bool, name: str) -> bool:
    if not value:
        return default
    normalized = value.strip().lower()
    if normalized in TRUE_VALUES:
        return True
    if normalized in FALSE_VALUES:
        return False
    raise SystemExit(f"ERROR: {name} must be true/false; got {value!r}.")


def auto_submission_enabled(book_dir: Path, is_booklet: bool) -> bool:
    return not is_booklet and all(
        (book_dir / name).is_file()
        for name in ("front-matter-submission.md", "metadata-submission.yaml")
    )


def cover_enabled(book_dir: Path, env: dict[str, str]) -> bool:
    template = Path(env.get("BOOK_COVER_TEMPLATE") or "cover.html").expanduser()
    return (template if template.is_absolute() else book_dir / template).is_file()


def parse_bindings(value: str) -> list[str]:
    try:
        bindings = list(dict.fromkeys(shlex.split(value)))
    except ValueError as exc:
        raise SystemExit(f"ERROR: Could not parse cover bindings {value!r}: {exc}") from exc
    if not bindings:
        raise SystemExit("ERROR: Cover binding list is empty.")
    invalid = [binding for binding in bindings if binding not in VALID_BINDINGS]
    if invalid:
        raise SystemExit(
            f"ERROR: Unsupported cover binding(s): {', '.join(invalid)}. "
            "Use paperback and/or hardcover."
        )
    return bindings


def run(cmd: list[str], root: Path, dry_run: bool) -> None:
    print("\n$ " + " ".join(shlex.quote(part) for part in cmd), flush=True)
    if dry_run:
        return
    result = subprocess.run(cmd, cwd=root, check=False)
    if result.returncode:
        raise SystemExit(result.returncode)


def output(root: Path, basename: str, product: str, *, binding: str = "", preview: bool = False) -> Path:
    suffixes = {
        "pdf": "-print.pdf",
        "docx": "-submission.docx",
        "epub": ".epub",
        "cover": f"-{binding}-cover{'-preview' if preview else ''}.pdf",
    }
    return root / "dist" / f"{basename}{suffixes[product]}"


def configured_products(book_dir: Path, env: dict[str, str]) -> dict[str, bool]:
    is_booklet = bool(env.get("BOOKLET_CHAPTERS"))
    submission_default = auto_submission_enabled(book_dir, is_booklet)
    defaults = {
        "pdf": True,
        "covers": cover_enabled(book_dir, env),
        "docx": submission_default,
        "epub": submission_default,
    }
    return {
        name: parse_bool(env.get(f"BOOK_BUILD_{name.upper()}"), default, f"BOOK_BUILD_{name.upper()}")
        for name, default in defaults.items()
    }


def choose_products(args: argparse.Namespace, book_dir: Path, env: dict[str, str]) -> dict[str, bool]:
    selected = {name: bool(getattr(args, name)) for name in PRODUCTS}
    products = configured_products(book_dir, env) if args.all or not any(selected.values()) else selected
    for name in PRODUCTS:
        if getattr(args, f"no_{name}"):
            products[name] = False
    return products


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("book_dir", help="Book/booklet directory containing book.env")

    products = p.add_argument_group("products")
    products.add_argument("--all", action="store_true", help="Build all products enabled by book.env (the default).")
    for name, help_text in {
        "pdf": "interior print PDF",
        "covers": "cover PDFs",
        "docx": "submission DOCX",
        "epub": "EPUB",
    }.items():
        products.add_argument(f"--{name}", action="store_true", help=f"Build only the {help_text}.")
        products.add_argument(f"--no-{name}", action="store_true", help=f"Skip the {help_text}.")

    covers = p.add_argument_group("cover options")
    covers.add_argument("--bindings", help="Space-separated bindings; overrides BOOK_COVER_BINDINGS.")
    covers.add_argument("--paper", choices=["cream", "white"])
    covers.add_argument("--renderer", choices=["auto", "weasyprint", "wkhtmltopdf", "chrome", "chromium"], default="auto")
    covers.add_argument("--preview", action="store_true")

    release = p.add_argument_group("publication metadata")
    release.add_argument("--release", action="store_true", help="Require a clean tagged release build.")
    release.add_argument("--release-tag", help="Release tag, normally inferred from HEAD.")
    release.add_argument("--release-date", help="ISO publication date; defaults to tagged commit date.")
    release.add_argument("--no-finalize", action="store_true")
    p.add_argument("--dry-run", action="store_true")
    return p


def main() -> None:
    args = parser().parse_args()
    root = repo_root()
    book_dir = resolve_under(root, args.book_dir)
    env_path = book_dir / "book.env"

    if not book_dir.is_dir():
        raise SystemExit(f"ERROR: Missing book directory: {book_dir}")
    if not env_path.is_file():
        raise SystemExit(f"ERROR: Missing {env_path}")

    env = load_env(env_path)
    for name in ("BOOK_TITLE", "BOOK_OUTPUT_BASENAME"):
        if not env.get(name):
            raise SystemExit(f"ERROR: {env_path} must define {name}.")

    target = rel(root, book_dir)
    basename = env["BOOK_OUTPUT_BASENAME"]
    is_booklet = bool(env.get("BOOKLET_CHAPTERS"))
    products = choose_products(args, book_dir, env)
    bindings = parse_bindings(args.bindings or env.get("BOOK_COVER_BINDINGS", "paperback hardcover"))

    prepare = ["python3", "tools/bin/publication.py", "prepare", target]
    if args.release:
        prepare.append("--release")
    if args.release_tag:
        prepare += ["--tag", args.release_tag]
    if args.release_date:
        prepare += ["--date", args.release_date]
    run(prepare, root, args.dry_run)

    enabled = [name for name in PRODUCTS if products[name]]
    print(f"Building target: {env['BOOK_TITLE']}")
    print(f"Directory:       {target}")
    print(f"Kind:            {'booklet' if is_booklet else 'book'}")
    print(f"Products:        {', '.join(enabled) if enabled else 'none'}")

    interior = output(root, basename, "pdf")
    if products["pdf"]:
        command = ["python3", "tools/bin/booklet.py", target] if is_booklet else ["bash", "tools/bin/pdf.sh", target]
        run(command, root, args.dry_run)

    if products["covers"]:
        base = ["python3", "tools/bin/render-cover.py", target, "--renderer", args.renderer]
        if args.preview:
            base.append("--preview")
        if args.paper:
            base += ["--paper", args.paper]
        if args.dry_run or interior.is_file():
            base += ["--pdf", rel(root, interior)]
        for binding in bindings:
            run(base + ["--binding", binding], root, args.dry_run)

    for name, script in (("docx", "docx.sh"), ("epub", "epub.sh")):
        if products[name]:
            run(["bash", f"tools/bin/{script}", target], root, args.dry_run)

    if enabled and not args.no_finalize:
        run(["python3", "tools/bin/publication.py", "finalize", target], root, args.dry_run)

    print("\nExpected artifacts:")
    artifact_paths: list[Path] = []
    if products["pdf"]:
        artifact_paths.append(interior)
    if products["covers"]:
        artifact_paths += [output(root, basename, "cover", binding=b, preview=args.preview) for b in bindings]
    if products["docx"]:
        artifact_paths.append(output(root, basename, "docx"))
    if products["epub"]:
        artifact_paths.append(output(root, basename, "epub"))
    for path in artifact_paths:
        print(f"  - {rel(root, path)}")

    print("\nDry run complete." if args.dry_run else "\nDone.")


if __name__ == "__main__":
    main()
