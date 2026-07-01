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
# extensions, and optical-size filenames. The build cares that the font family
# resolves through fontconfig, because WeasyPrint resolves fonts that way when
# cover templates use font-family names.
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


def fc_match(font_name: str) -> str | None:
    if not command_exists("fc-match"):
        return None

    result = subprocess.run(
        ["fc-match", font_name],
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
    )
    if result.returncode != 0:
        return None

    output = result.stdout.strip()
    if not output:
        return None

    # Avoid false positives where fontconfig silently falls back to DejaVu,
    # Liberation, or another generic serif font.
    if font_name.lower() not in output.lower():
        return None

    return output


def fc_match_style(font_name: str, style: str) -> str | None:
    if not command_exists("fc-match"):
        return None

    pattern = f"{font_name}:style={style}"
    result = subprocess.run(
        ["fc-match", pattern],
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
    )
    if result.returncode != 0:
        return None

    output = result.stdout.strip()
    if not output:
        return None

    # Same fallback guard as fc_match.
    if font_name.lower() not in output.lower():
        return None

    return output


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

    tex_gyre_match = fc_match("TeX Gyre Pagella")
    if not tex_gyre_match:
        errors.append("missing fontconfig match: TeX Gyre Pagella")

    eb_match = fc_match("EB Garamond")
    if not eb_match:
        errors.append("missing fontconfig match: EB Garamond")

    eb_italic_match = fc_match_style("EB Garamond", "Italic")
    if not eb_italic_match:
        errors.append("missing fontconfig match: EB Garamond Italic")

    eb_bold_match = fc_match_style("EB Garamond", "Bold")
    if not eb_bold_match:
        errors.append("missing fontconfig match: EB Garamond Bold")

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
