#!/usr/bin/env python3
"""
Verify the active book build environment.

Required for the current pipeline:
  - Typst interior PDFs
  - WeasyPrint cover PDFs
  - Pandoc DOCX
  - Pandoc EPUB
  - pypdf page-count extraction
  - python-docx helper/template generation
  - EB Garamond and TeX Gyre fonts

Intentionally does NOT require:
  - qpdf
  - poppler-utils: pdfinfo, pdffonts, pdftoppm
  - TeX Live / XeLaTeX
  - jq
"""

from __future__ import annotations

import importlib.util
import shutil
import subprocess
import sys
from pathlib import Path


REQUIRED_COMMANDS = [
    "typst",
    "pandoc",
    "python3",
    "weasyprint",
]

REQUIRED_PYTHON_MODULES = [
    "docx",       # python-docx
    "pypdf",
    "weasyprint",
]

# Do not hard-code EB Garamond font file paths here.
#
# Debian and Ubuntu package the same font family under different directories,
# extensions, and optical-size filenames. Validate installed face metadata via
# fontconfig rather than hard-coding paths or trusting fc-match fallbacks.
REQUIRED_FILES: list[Path] = []


def command_exists(name: str) -> bool:
    return shutil.which(name) is not None


def module_exists(name: str) -> bool:
    return importlib.util.find_spec(name) is not None


def command_output(args: list[str]) -> str:
    try:
        result = subprocess.run(
            args,
            check=True,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )
        return result.stdout.strip()
    except Exception as exc:
        return f"ERROR: {exc}"


def normalize_font_name(value: str) -> str:
    # Fontconfig may report the same family as either "TeX Gyre Pagella" or
    # "TeXGyrePagella" depending on the installed face/package.
    return "".join(ch for ch in value.casefold() if ch.isalnum())


def installed_font_faces() -> list[tuple[str, str, str]]:
    """Return installed font faces as (file, family, style) tuples."""
    if not command_exists("fc-list"):
        return []

    result = subprocess.run(
        ["fc-list", "--format", "%{file}\t%{family}\t%{style}\n"],
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
    )
    if result.returncode != 0:
        return []

    faces: list[tuple[str, str, str]] = []
    for line in result.stdout.splitlines():
        parts = line.split("\t", 2)
        if len(parts) == 3:
            faces.append((parts[0], parts[1], parts[2]))
    return faces


def find_font_face(
    faces: list[tuple[str, str, str]],
    family: str,
    required_style: str,
) -> str | None:
    """Find an actually installed face matching family and style metadata."""
    wanted_family = normalize_font_name(family)
    wanted_style = normalize_font_name(required_style)

    for file_name, families, styles in faces:
        family_names = {
            normalize_font_name(item)
            for item in families.split(",")
            if item.strip()
        }
        style_names = [
            normalize_font_name(item)
            for item in styles.split(",")
            if item.strip()
        ]

        if wanted_family not in family_names:
            continue
        if not any(wanted_style in style for style in style_names):
            continue

        primary_family = families.split(",", 1)[0].strip()
        primary_style = styles.split(",", 1)[0].strip()
        return f'{Path(file_name).name}: "{primary_family}" "{primary_style}"'

    return None


def main() -> int:
    errors: list[str] = []

    for command in REQUIRED_COMMANDS:
        if not command_exists(command):
            errors.append(f"missing command: {command}")

    for module in REQUIRED_PYTHON_MODULES:
        if not module_exists(module):
            errors.append(f"missing Python module: {module}")

    for path in REQUIRED_FILES:
        if not path.exists():
            errors.append(f"missing file: {path}")

    font_faces = installed_font_faces()
    if not font_faces:
        errors.append("missing command or usable output: fc-list")

    tex_gyre_match = find_font_face(font_faces, "TeX Gyre Pagella", "Regular")
    if not tex_gyre_match:
        errors.append("missing installed font face: TeX Gyre Pagella Regular")

    eb_match = find_font_face(font_faces, "EB Garamond", "Regular")
    if not eb_match:
        errors.append("missing installed font face: EB Garamond Regular")

    eb_italic_match = find_font_face(font_faces, "EB Garamond", "Italic")
    if not eb_italic_match:
        errors.append("missing installed font face: EB Garamond Italic")

    eb_bold_match = find_font_face(font_faces, "EB Garamond", "Bold")
    if not eb_bold_match:
        errors.append("missing installed font face: EB Garamond Bold")

    typst_version = command_output(["typst", "--version"]) if command_exists("typst") else "missing"
    pandoc_version = (
        command_output(["pandoc", "--version"]).splitlines()[0]
        if command_exists("pandoc")
        else "missing"
    )
    weasyprint_version = (
        command_output(["weasyprint", "--version"])
        if command_exists("weasyprint")
        else "missing"
    )

    if errors:
        print("Build environment check FAILED:", file=sys.stderr)
        for error in errors:
            print(f"  - {error}", file=sys.stderr)
        print("", file=sys.stderr)
        print("Detected versions:", file=sys.stderr)
        print(f"  typst:       {typst_version}", file=sys.stderr)
        print(f"  pandoc:      {pandoc_version}", file=sys.stderr)
        print(f"  weasyprint:  {weasyprint_version}", file=sys.stderr)
        if tex_gyre_match:
            print(f"  TeX Gyre:    {tex_gyre_match}", file=sys.stderr)
        if eb_match:
            print(f"  EB Garamond: {eb_match}", file=sys.stderr)
        if eb_italic_match:
            print(f"  EB Italic:   {eb_italic_match}", file=sys.stderr)
        if eb_bold_match:
            print(f"  EB Bold:     {eb_bold_match}", file=sys.stderr)
        return 1

    print("Build environment check OK")
    print(f"  typst:       {typst_version}")
    print(f"  pandoc:      {pandoc_version}")
    print(f"  weasyprint:  {weasyprint_version}")
    print(f"  TeX Gyre:    {tex_gyre_match}")
    print(f"  EB Garamond: {eb_match}")
    print(f"  EB Italic:   {eb_italic_match}")
    print(f"  EB Bold:     {eb_bold_match}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
