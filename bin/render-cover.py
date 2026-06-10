#!/usr/bin/env python3
"""
render-cover.py — KDP full-wrap cover renderer for lymanepp.com.

The renderer is book-directory driven, matching tools/bin/pdf.sh. Give it a
book directory, and it reads that directory's book.env plus cover.html.
There is no embedded registry of known books or booklets.

Usage
─────
  python3 tools/bin/render-cover.py book1 --binding paperback
  python3 tools/bin/render-cover.py book2 --binding hardcover
  python3 tools/bin/render-cover.py book1 --pdf dist/what-scripture-says-vol1-print.pdf
  python3 tools/bin/render-cover.py booklets/marriage-and-family --pdf dist/marriage-and-family-print.pdf
  python3 tools/bin/render-cover.py booklets/marriage-and-family --all-bindings
  python3 tools/bin/render-cover.py --all --all-bindings

Required per-book files
───────────────────────
  <book-dir>/book.env
  <book-dir>/cover.html  (or BOOK_COVER_TEMPLATE='<relative/path.html>')

book.env fields used by this renderer
─────────────────────────────────────
  BOOK_TITLE                  Human-readable label in console output
  BOOK_OUTPUT_BASENAME        Output filename base
  BOOK_COVER_TEMPLATE         Optional; defaults to cover.html
  BOOK_COVER_PAPER            Optional; cream or white; defaults to cream
  BOOK_COVER_SPINE_TEXT       Optional; auto, true, or false; defaults to auto
  BOOK_COVER_SPINE_TEXT_MIN_PAGES
                              Optional; defaults to 79 per KDP spine-text rule
  BOOK_COVER_SPINE_SAFE_MARGIN_IN
                              Optional; defaults to 0.50in; minimum 0.375in
  BOOK_COVER_SPINE_SERIES     Optional; defaults to BOOK_TITLE
  BOOK_COVER_SPINE_TITLE      Optional; defaults to BOOK_SUBTITLE or BOOK_TITLE
  BOOK_COVER_SPINE_AUTHOR     Optional; defaults to BOOK_AUTHOR

  Spine font sizes are calculated from the actual spine width and text length.
  Wider books get larger, more readable spine type; narrow spines are clamped
  down so the text stays inside the spine panel.

Page count resolution
─────────────────────
  The renderer always reads the page count from an interior PDF.
  By default it uses dist/{{BOOK_OUTPUT_BASENAME}}-print.pdf.
  Use --pdf FILE only when the interior PDF is somewhere else.

Output naming
─────────────
  Covers are written to dist/ by default and use names compatible with
  the existing print-content PDFs, for example:

    what-scripture-says-vol1-print.pdf
    what-scripture-says-vol1-paperback-cover.pdf
    what-scripture-says-vol1-hardcover-cover.pdf

KDP geometry
────────────
  Paperback:
    spine = pages × paper thickness
    width = bleed + back + spine + front + bleed
    height = bleed + trim height + bleed

  Hardcover case laminate:
    spine = pages × paper thickness + KDP hardcover case-laminate spine allowance
    width = wrap + back + hinge + spine + hinge + front + wrap
    height = KDP hardcover full-wrap height
    non-background artwork is then inset to KDP hardcover safe zones

  Paper thickness and cover-size formulas live in kdp_cover_geometry.py,
  which is unit-tested against KDP's cover-calculator output.

  Default trim: 6.0 × 9.0 inches.
"""

import argparse
import html as html_lib
import math
import os
import re
import shlex
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from kdp_cover_geometry import CSS_DPI, PAPER_THICKNESS as PAPER, cover_geometry_tokens


def page_count_from_pdf(path: Path) -> int:
    """Return the page count of a PDF file using pypdf."""
    try:
        from pypdf import PdfReader
    except ImportError:
        sys.exit("pypdf is required to use --pdf.\n"
                 "Install: pip3 install pypdf --break-system-packages")
    try:
        reader = PdfReader(str(path))
        count = len(reader.pages)
        if count < 1:
            sys.exit(f"PDF reports 0 pages: {path}")
        return count
    except Exception as e:
        sys.exit(f"Could not read PDF '{path}': {e}")


# KDP cover geometry is centralized in kdp_cover_geometry.py and unit-tested
# against KDP cover-calculator screenshots. Keep this renderer focused on
# templating and PDF generation; do not reintroduce cover-size formulas here.
KDP_SPINE_TEXT_MIN_PAGES = 79
KDP_SPINE_TEXT_MIN_EDGE_MARGIN_IN = 0.375
DEFAULT_SPINE_TEXT_EDGE_MARGIN_IN = 0.50

# Spine type is sized dynamically. These are CSS-pixel bounds used after
# the real spine width has been calculated from the interior PDF page count.
SPINE_TITLE_FONT_MIN_PX = 7.5
SPINE_TITLE_FONT_MAX_PX = 19.0
SPINE_SERIES_FONT_MIN_PX = 7.0
SPINE_SERIES_FONT_MAX_PX = 13.5
SPINE_AUTHOR_FONT_MIN_PX = 7.0
SPINE_AUTHOR_FONT_MAX_PX = 12.0


@dataclass(frozen=True)
class CoverTarget:
    book_dir: Path
    env_path: Path
    template: Path
    title: str
    output_basename: str
    default_paper: str

    @property
    def label(self) -> str:
        return self.title or self.output_basename

    @property
    def safe_id(self) -> str:
        rel = str(self.book_dir).replace(os.sep, "-")
        return re.sub(r"[^A-Za-z0-9_.-]+", "-", rel).strip("-._") or "cover"


@dataclass(frozen=True)
class SpineTextConfig:
    show: bool
    policy: str
    min_pages: int
    safe_margin_in: float
    safe_margin_px: float
    title_font_px: float
    series_font_px: float
    author_font_px: float
    rule_margin_px: float

    @property
    def status(self) -> str:
        return "shown" if self.show else "hidden"


def git_workspace_root() -> Path:
    """Return the Git workspace root for the current invocation."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=Path.cwd(),
            capture_output=True,
            text=True,
            check=True,
        )
        return Path(result.stdout.strip()).resolve()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return Path.cwd().resolve()


def resolve_under_workspace(path: str | Path, workspace: Path) -> Path:
    p = Path(path).expanduser()
    if not p.is_absolute():
        p = workspace / p
    return p.resolve()


def load_env(path: Path) -> dict[str, str]:
    """Parse the simple shell-style KEY=value book.env files used by this repo."""
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
            sys.exit(f"Invalid env key in {path}:{lineno}: {key}")
        try:
            parts = shlex.split(raw, comments=False, posix=True)
            value = parts[0] if parts else ""
        except ValueError as e:
            sys.exit(f"Could not parse {path}:{lineno}: {e}")
        env[key] = value
    return env


def optional_int(value: str | None, name: str, env_path: Path) -> int | None:
    if value is None or value == "":
        return None
    try:
        parsed = int(value)
    except ValueError:
        sys.exit(f"{env_path} must define {name} as an integer page count, got: {value!r}")
    if parsed < 1:
        sys.exit(f"{env_path} must define {name} as a positive page count, got: {parsed}")
    return parsed


def optional_float(value: str | None, name: str, env_path: Path) -> float | None:
    if value is None or value == "":
        return None
    try:
        parsed = float(value)
    except ValueError:
        sys.exit(f"{env_path} must define {name} as a number, got: {value!r}")
    if parsed <= 0:
        sys.exit(f"{env_path} must define {name} as a positive number, got: {parsed}")
    return parsed


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def spine_env_strings(target: CoverTarget) -> dict[str, str]:
    """Return spine strings, with useful metadata-driven fallbacks."""
    cfg = load_env(target.env_path)
    series = cfg.get("BOOK_COVER_SPINE_SERIES") or cfg.get("BOOK_TITLE") or target.title
    title = cfg.get("BOOK_COVER_SPINE_TITLE") or cfg.get("BOOK_SUBTITLE") or target.title
    author = cfg.get("BOOK_COVER_SPINE_AUTHOR") or cfg.get("BOOK_AUTHOR") or ""
    return {
        "BOOK_COVER_SPINE_SERIES": series,
        "BOOK_COVER_SPINE_TITLE": title,
        "BOOK_COVER_SPINE_AUTHOR": author,
    }


def estimate_spine_text_width(series: str, title: str, author: str,
                              series_font: float, title_font: float,
                              author_font: float, rule_margin: float) -> float:
    """Estimate the horizontal length of rotated spine text in CSS pixels.

    This intentionally errs slightly high. It is not a font engine; it is a
    guardrail that scales the spine typography down before the PDF renderer can
    clip long strings on short/narrow spines.
    """
    def text_width(text: str, font_px: float, avg_em: float, letterspace_em: float) -> float:
        text = text.strip()
        if not text:
            return 0.0
        # letter-spacing adds after most characters in CSS. Approximate it.
        return (len(text) * avg_em * font_px) + (max(0, len(text) - 1) * letterspace_em * font_px)

    series_w = text_width(series.upper(), series_font, 0.54, 0.10)
    title_w = text_width(title, title_font, 0.50, 0.02)
    author_w = text_width(author.upper(), author_font, 0.54, 0.14)
    # Two flexible rules, each with left/right margins and a small visible rule.
    rules_w = (4 * rule_margin) + 28
    return series_w + title_w + author_w + rules_w


def spine_font_layout(target: CoverTarget, spine_width_px: float, safe_margin_px: float,
                      panel_height_px: float) -> dict[str, float]:
    """Choose readable spine font sizes while respecting narrow spines.

    The font height is constrained by the physical spine width. A second pass
    estimates length along the spine and scales down if the series/title/author
    combination would crowd the KDP top/bottom safety margins.
    """
    strings = spine_env_strings(target)

    # Primary clamp: font height cannot exceed what the spine width can carry.
    title_font = clamp(spine_width_px * 0.30, SPINE_TITLE_FONT_MIN_PX, SPINE_TITLE_FONT_MAX_PX)
    series_font = clamp(title_font * 0.72, SPINE_SERIES_FONT_MIN_PX, SPINE_SERIES_FONT_MAX_PX)
    author_font = clamp(title_font * 0.64, SPINE_AUTHOR_FONT_MIN_PX, SPINE_AUTHOR_FONT_MAX_PX)
    rule_margin = clamp(title_font * 0.55, 4.0, 10.0)

    available_len = max(1.0, panel_height_px - (2 * safe_margin_px))
    estimated = estimate_spine_text_width(
        strings["BOOK_COVER_SPINE_SERIES"],
        strings["BOOK_COVER_SPINE_TITLE"],
        strings["BOOK_COVER_SPINE_AUTHOR"],
        series_font,
        title_font,
        author_font,
        rule_margin,
    )

    if estimated > available_len:
        scale = available_len / estimated
        title_font = clamp(title_font * scale, SPINE_TITLE_FONT_MIN_PX, SPINE_TITLE_FONT_MAX_PX)
        series_font = clamp(series_font * scale, SPINE_SERIES_FONT_MIN_PX, SPINE_SERIES_FONT_MAX_PX)
        author_font = clamp(author_font * scale, SPINE_AUTHOR_FONT_MIN_PX, SPINE_AUTHOR_FONT_MAX_PX)
        rule_margin = clamp(rule_margin * scale, 3.0, 10.0)

    return {
        "title_font_px": round(title_font, 1),
        "series_font_px": round(series_font, 1),
        "author_font_px": round(author_font, 1),
        "rule_margin_px": round(rule_margin, 1),
    }


def resolve_spine_text_config(target: CoverTarget, pages: int, geometry: dict) -> SpineTextConfig:
    """Resolve KDP spine-text policy from book.env and actual page count.

    KDP requires at least 79 pages for spine text and requires spine text
    to sit at least 0.375in from the top and bottom cover edges. This
    defaults to a more conservative 0.50in edge margin.
    """
    cfg = load_env(target.env_path)
    policy = (cfg.get("BOOK_COVER_SPINE_TEXT", "auto") or "auto").strip().lower()
    aliases = {
        "1": "true", "yes": "true", "y": "true", "on": "true",
        "0": "false", "no": "false", "n": "false", "off": "false",
    }
    policy = aliases.get(policy, policy)
    if policy not in {"auto", "true", "false"}:
        sys.exit(
            f"{target.env_path} has unsupported BOOK_COVER_SPINE_TEXT={policy!r}. "
            "Use auto, true, or false."
        )

    min_pages = optional_int(
        cfg.get("BOOK_COVER_SPINE_TEXT_MIN_PAGES"),
        "BOOK_COVER_SPINE_TEXT_MIN_PAGES",
        target.env_path,
    ) or KDP_SPINE_TEXT_MIN_PAGES

    safe_margin_in = optional_float(
        cfg.get("BOOK_COVER_SPINE_SAFE_MARGIN_IN"),
        "BOOK_COVER_SPINE_SAFE_MARGIN_IN",
        target.env_path,
    ) or DEFAULT_SPINE_TEXT_EDGE_MARGIN_IN
    safe_margin_in = max(safe_margin_in, KDP_SPINE_TEXT_MIN_EDGE_MARGIN_IN)

    if policy == "true":
        show = True
    elif policy == "false":
        show = False
    else:
        show = pages >= min_pages

    safe_margin_px = px(safe_margin_in)
    fonts = spine_font_layout(
        target,
        spine_width_px=float(geometry["SPINE"]),
        safe_margin_px=safe_margin_px,
        panel_height_px=float(geometry["PANEL_H"]),
    )

    return SpineTextConfig(
        show=show,
        policy=policy,
        min_pages=min_pages,
        safe_margin_in=safe_margin_in,
        safe_margin_px=safe_margin_px,
        **fonts,
    )


def load_cover_target(book_arg: str | Path, workspace: Path) -> CoverTarget:
    book_dir = resolve_under_workspace(book_arg, workspace)
    env_path = book_dir / "book.env"
    if not book_dir.is_dir():
        sys.exit(f"Book directory not found: {book_dir}")
    if not env_path.is_file():
        sys.exit(f"Missing {env_path}. Cover targets must be driven by book.env.")

    cfg = load_env(env_path)
    for var in ("BOOK_TITLE", "BOOK_OUTPUT_BASENAME"):
        if not cfg.get(var):
            sys.exit(f"{env_path} must define {var}.")

    template_name = cfg.get("BOOK_COVER_TEMPLATE", "cover.html") or "cover.html"
    template = Path(template_name).expanduser()
    if not template.is_absolute():
        template = book_dir / template
    template = template.resolve()
    if not template.is_file():
        sys.exit(f"Cover template not found: {template}\nSet BOOK_COVER_TEMPLATE in {env_path}, or add cover.html to the book directory.")

    paper = cfg.get("BOOK_COVER_PAPER", "cream") or "cream"
    if paper not in PAPER:
        sys.exit(f"{env_path} has unsupported BOOK_COVER_PAPER={paper!r}. Use cream or white.")

    return CoverTarget(
        book_dir=book_dir,
        env_path=env_path,
        template=template,
        title=cfg["BOOK_TITLE"],
        output_basename=cfg["BOOK_OUTPUT_BASENAME"],
        default_paper=paper,
    )


def discover_cover_targets(workspace: Path) -> list[CoverTarget]:
    """Discover cover-capable book directories without a hard-coded target registry."""
    candidates: list[Path] = []

    for child in workspace.iterdir():
        if child.name.startswith(".") or child.name in {"build", "dist", "tools"}:
            continue
        if child.is_dir() and (child / "book.env").is_file():
            candidates.append(child)

    booklets_dir = workspace / "booklets"
    if booklets_dir.is_dir():
        for child in booklets_dir.iterdir():
            if child.is_dir() and (child / "book.env").is_file():
                candidates.append(child)

    targets: list[CoverTarget] = []
    for candidate in sorted(set(candidates)):
        try:
            target = load_cover_target(candidate, workspace)
        except SystemExit as e:
            # --all should skip directories that have book.env but no cover template.
            # A direct invocation still reports the error via load_cover_target().
            if (candidate / "cover.html").exists():
                raise e
            continue
        targets.append(target)
    return targets


def executable_from_env(var_name: str) -> str | None:
    """Return executable path from an environment variable if valid."""
    env_path = os.environ.get(var_name)
    if not env_path:
        return None
    path = Path(env_path).expanduser()
    if path.is_file() and os.access(path, os.X_OK):
        return str(path)
    return None


def first_executable(names: list[str], extra_paths: list[str] | None = None) -> str | None:
    """Return the first executable found from PATH or common absolute paths."""
    for name in names:
        found = shutil.which(name)
        if found:
            return found

    for candidate in extra_paths or []:
        path = Path(candidate).expanduser()
        if path.is_file() and os.access(path, os.X_OK):
            return str(path)

    return None


def find_wkhtmltopdf() -> str | None:
    """Return a usable wkhtmltopdf executable path, or None."""
    return (
        executable_from_env("WKHTMLTOPDF")
        or first_executable(
            ["wkhtmltopdf"],
            [
                "/usr/bin/wkhtmltopdf",
                "/usr/local/bin/wkhtmltopdf",
                "/snap/bin/wkhtmltopdf",
                "/opt/homebrew/bin/wkhtmltopdf",
                "/usr/local/opt/wkhtmltopdf/bin/wkhtmltopdf",
            ],
        )
    )


def find_chrome() -> str | None:
    """Return a usable Chrome/Chromium executable path, or None."""
    return (
        executable_from_env("CHROME")
        or executable_from_env("CHROMIUM")
        or first_executable(
            [
                "chromium",
                "chromium-browser",
                "google-chrome",
                "google-chrome-stable",
                "chrome",
                "chrome.exe",
                "msedge",
                "microsoft-edge",
            ],
            [
                "/usr/bin/chromium",
                "/usr/bin/chromium-browser",
                "/usr/bin/google-chrome",
                "/usr/bin/google-chrome-stable",
                "/opt/google/chrome/chrome",
                "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
                "/Applications/Chromium.app/Contents/MacOS/Chromium",
            ],
        )
    )


def has_weasyprint() -> bool:
    """Return True if the Python WeasyPrint renderer is importable."""
    try:
        import weasyprint  # noqa: F401
        return True
    except Exception:
        return False



def validate_local_url_assets(html: str, template: Path) -> None:
    """Fail fast when a cover template references missing local assets.

    WeasyPrint will otherwise silently fall back to a different font when an
    @font-face src file is missing. That makes local and CI cover output drift,
    especially in the spine where font metrics matter.
    """
    missing: list[str] = []
    for match in re.finditer(r"url\(\s*(['\"]?)(/[^)'\"\s]+)\1\s*\)", html):
        asset = Path(match.group(2))
        if not asset.is_file():
            missing.append(str(asset))

    if missing:
        details = "\n".join(f"  - {path}" for path in sorted(set(missing)))
        sys.exit(
            f"Cover template references missing local asset(s): {template}\n"
            f"{details}\n\n"
            "Install the missing font/image package in this environment before "
            "rendering covers. For the current What Scripture Says cover templates, "
            "the Debian/Ubuntu package is usually: fonts-ebgaramond"
        )

def render_with_weasyprint(html: str, out: Path, workspace: Path) -> subprocess.CompletedProcess:
    """Render HTML to PDF with WeasyPrint and return a subprocess-like result."""
    try:
        from weasyprint import HTML
        HTML(string=html, base_url=str(workspace)).write_pdf(str(out))
        return subprocess.CompletedProcess(["weasyprint"], 0, "", "")
    except Exception as e:
        return subprocess.CompletedProcess(["weasyprint"], 1, "", str(e))


def choose_renderer(requested: str) -> tuple[str, str]:
    """Choose the renderer and return (renderer_name, executable_path_or_label)."""
    requested = requested.lower()

    if requested in ("auto", "weasyprint"):
        if has_weasyprint():
            return "weasyprint", "python:weasyprint"
        if requested == "weasyprint":
            renderer_missing_error("WeasyPrint")

    if requested in ("auto", "wkhtmltopdf"):
        exe = find_wkhtmltopdf()
        if exe:
            return "wkhtmltopdf", exe
        if requested == "wkhtmltopdf":
            renderer_missing_error("wkhtmltopdf")

    if requested in ("auto", "chrome", "chromium"):
        exe = find_chrome()
        if exe:
            return "chrome", exe
        if requested in ("chrome", "chromium"):
            renderer_missing_error("Chrome/Chromium")

    renderer_missing_error("WeasyPrint, wkhtmltopdf, or Chrome/Chromium")


def renderer_missing_error(name: str) -> None:
    path_value = os.environ.get("PATH", "")
    sys.exit(
        f"Could not find {name} in this dev container.\n\n"
        "This script supports WeasyPrint, wkhtmltopdf, or headless Chrome/Chromium. "
        "Your container's apt repositories do not appear to provide wkhtmltopdf, "
        "so install Chromium instead inside the dev container:\n\n"
        "  sudo apt-get update && sudo apt-get install -y chromium\n\n"
        "Then rerun, for example:\n\n"
        "  python3 tools/bin/render-cover.py book1\n\n"
        "Optional overrides:\n"
        "  CHROME=/full/path/to/chromium python3 tools/bin/render-cover.py book1\n"
        "  WKHTMLTOPDF=/full/path/to/wkhtmltopdf python3 tools/bin/render-cover.py book1\n\n"
        f"PATH seen by Python:\n  {path_value}"
    )


def inject_print_page_size(html: str, g: dict) -> str:
    """Add print-page geometry so headless Chrome emits the exact KDP wrap size."""
    css = (
        "\n@page { "
        f"size: {g['total_w_in']:.4f}in {g['total_h_in']:.4f}in; "
        "margin: 0; }\n"
        "@media print {\n"
        "  html, body { margin: 0 !important; -webkit-print-color-adjust: exact; print-color-adjust: exact; }\n"
        "}\n"
    )
    return html.replace("<style>", "<style>" + css, 1)


def inject_hardcover_safe_layout(html: str, g: dict) -> str:
    """Move non-background hardcover artwork inside KDP's hardcover safety zones.

    KDP case-laminate hardcovers need full-bleed background through the wrap,
    but text, barcodes, frames, and ornaments must not sit in the wrap, hinge,
    or outside-cover safety margins. The base template is intentionally tight
    for paperback, so hardcover gets a conservative override here.
    """
    safe = px(0.635)
    content = round(safe + 13, 1)
    barcode_bottom = px(0.76)
    barcode_h = px(1.2)
    barcode_top = round(g["PANEL_H"] - barcode_bottom - barcode_h, 1)

    css = f"""

/* ── HARDCOVER SAFE-LAYOUT OVERRIDES ──
   Background still fills the entire case-laminate wrap, but all intentional
   artwork/text is kept out of KDP's wrap/hinge/margin danger zones. */
.hardcover .frame {{ top:{safe}px; left:{safe}px; right:{safe}px; bottom:{safe}px; }}
.hardcover .frame-inner {{ top:4px; left:4px; right:4px; bottom:4px; }}

.hardcover .front-series {{ top:82px; }}
.hardcover .front-title {{ top:340px; }}
.hardcover .front-ornament {{ top:715px; }}
.hardcover .front-author {{ top:752px; }}

.hardcover .back-series-head {{ top:76px; left:{content}px; right:{content}px; }}
.hardcover .back-top-rule {{ top:98px; left:{content}px; right:{content}px; }}
.hardcover .back-blurb {{ top:116px; left:{content}px; right:{content}px; font-size:12.4px; line-height:1.58; }}
.hardcover .back-bottom-rule {{ top:652px; left:{content}px; right:{content}px; }}
.hardcover .back-bio {{ top:668px; left:{content}px; right:300px; font-size:10.5px; line-height:1.48; }}
.hardcover .back-url {{ top:782px; left:{content}px; }}
.hardcover .barcode-box {{ top:{barcode_top}px; right:74px; width:192px; height:115px; }}
"""
    html = html.replace("<body>", '<body class="hardcover">', 1)
    return html.replace("</style>", css + "\n</style>", 1)


def inject_spine_text_layout(html: str, spine_cfg: SpineTextConfig) -> str:
    """Apply KDP spine-text visibility and top/bottom safety margins.

    The rotated spine container's left/right padding corresponds to physical
    top/bottom clearance on the finished spine. This late CSS override protects
    templates that still have older hard-coded spine padding.
    """
    display = "flex" if spine_cfg.show else "none"
    css = f"""

/* ── KDP SPINE-TEXT SAFETY / RESPONSIVE TYPE OVERRIDES ── */
.spine-rotator {{
  box-sizing: border-box;
  display: {display} !important;
  padding-left: {spine_cfg.safe_margin_px}px !important;
  padding-right: {spine_cfg.safe_margin_px}px !important;
}}
.spine-series {{ font-size: {spine_cfg.series_font_px}px !important; }}
.spine-title  {{ font-size: {spine_cfg.title_font_px}px !important; }}
.spine-author {{ font-size: {spine_cfg.author_font_px}px !important; }}
.spine-rule   {{ margin-left: {spine_cfg.rule_margin_px}px !important; margin-right: {spine_cfg.rule_margin_px}px !important; }}
"""
    return html.replace("</style>", css + "\n</style>", 1)


def build_wkhtmltopdf_cmd(exe: str, tmp: Path, out: Path, g: dict, dpi: int) -> list[str]:
    return [
        exe,
        "--page-width",  f"{g['total_w_in']:.4f}in",
        "--page-height", f"{g['total_h_in']:.4f}in",
        "--margin-top",    "0", "--margin-right",  "0",
        "--margin-bottom", "0", "--margin-left",   "0",
        "--dpi", str(dpi),
        "--zoom", "1",
        "--background",
        "--enable-local-file-access",
        "--load-error-handling", "ignore",
        "--load-media-error-handling", "ignore",
        str(tmp), str(out),
    ]


def build_chrome_cmd(exe: str, tmp: Path, out: Path, g: dict) -> list[str]:
    width = max(1, math.ceil(g["TOTAL_W"]))
    height = max(1, math.ceil(g["TOTAL_H"]))
    return [
        exe,
        "--headless",
        "--disable-gpu",
        "--no-sandbox",
        "--disable-dev-shm-usage",
        "--no-pdf-header-footer",
        f"--window-size={width},{height}",
        f"--print-to-pdf={out}",
        "--timeout=5000",
        tmp.as_uri(),
    ]


def px(inches: float) -> float:
    """Convert inches to CSS pixels and keep output stable/readable."""
    return round(inches * CSS_DPI, 1)


def geo(pages: int, paper: str = "cream", binding: str = "paperback") -> dict:
    """Return geometry tokens for paperback or hardcover KDP cover rendering."""
    return cover_geometry_tokens(pages=pages, paper=paper, binding=binding)


def inject_tokens(html: str, geometry: dict, target: CoverTarget) -> str:
    """Replace geometry tokens and book.env tokens in cover.html."""
    replacements = {k: str(v) for k, v in geometry.items()}
    replacements.update({
        "BOOK_TITLE": target.title,
        "BOOK_OUTPUT_BASENAME": target.output_basename,
    })

    # Also expose every book.env value to the template as {{VAR}}. This keeps
    # template text optional but lets future covers avoid duplicating metadata.
    env_values = load_env(target.env_path)
    replacements.update(env_values)

    # Spine text has metadata-driven defaults so templates can be generic.
    replacements.update(spine_env_strings(target))

    def repl(match: re.Match[str]) -> str:
        key = match.group(1).strip()
        value = replacements.get(key)
        if value is None:
            return match.group(0)
        return html_lib.escape(value) if key.startswith("BOOK_") else str(value)

    return re.sub(r"\{\{\s*([A-Za-z_][A-Za-z0-9_]*)\s*\}\}", repl, html)


def default_interior_pdf(target: CoverTarget, workspace: Path) -> Path:
    """Return the conventional print-PDF path for this book target."""
    return workspace / "dist" / f"{target.output_basename}-print.pdf"


def resolve_interior_pdf(target: CoverTarget, args: argparse.Namespace, workspace: Path) -> Path:
    """Resolve the interior PDF whose real page count drives cover geometry."""
    pdf = resolve_under_workspace(args.pdf, workspace) if args.pdf else default_interior_pdf(target, workspace)
    if not pdf.is_file():
        expected = default_interior_pdf(target, workspace)
        raise SystemExit(
            f"Interior PDF required to calculate cover geometry: {pdf}\n"
            "Build the content PDF first, then render the cover. For the default "
            f"layout this renderer expects: {expected}\n"
            "Use --pdf FILE only if the interior PDF is in a nonstandard location."
        )
    return pdf


def resolve_pages(target: CoverTarget, args: argparse.Namespace, workspace: Path) -> int:
    pdf = resolve_interior_pdf(target, args, workspace)
    pages = page_count_from_pdf(pdf)
    print(f"Page count from PDF: {pages}  ({pdf})")
    return pages


def render(target: CoverTarget, pages: int, paper: str, binding: str, preview: bool,
           outdir: str | Path, workspace: Path, requested_renderer: str) -> None:
    g = geo(pages, paper, binding)
    spine_cfg = resolve_spine_text_config(target, pages, g)
    g["SPINE_TEXT_DISPLAY"] = "flex" if spine_cfg.show else "none"
    g["SPINE_TEXT_SAFE_PAD"] = spine_cfg.safe_margin_px

    renderer_name, renderer_exe = choose_renderer(requested_renderer)

    raw_html = target.template.read_text(encoding="utf-8")
    html = inject_tokens(raw_html, g, target)

    if binding == "hardcover":
        html = inject_hardcover_safe_layout(html, g)

    html = inject_spine_text_layout(html, spine_cfg)

    if renderer_name in ("chrome", "weasyprint"):
        html = inject_print_page_size(html, g)

    validate_local_url_assets(html, target.template)

    tmp = workspace / f"_tmp_{target.safe_id}_{binding}.html"
    tmp.write_text(html, encoding="utf-8")

    outdir = Path(outdir)
    if not outdir.is_absolute():
        outdir = workspace / outdir
    outdir.mkdir(parents=True, exist_ok=True)

    suf = "-preview" if preview else ""
    out = outdir / f"{target.output_basename}-{binding}-cover{suf}.pdf"
    dpi = 96 if preview else 300

    if renderer_name == "wkhtmltopdf":
        cmd = build_wkhtmltopdf_cmd(renderer_exe, tmp, out, g, dpi)
    elif renderer_name == "chrome":
        cmd = build_chrome_cmd(renderer_exe, tmp, out, g)
    else:
        cmd = ["weasyprint"]

    print(f"\n{'─'*58}")
    print(f"Book:    {target.label}")
    print(f"Dir:     {target.book_dir.relative_to(workspace) if target.book_dir.is_relative_to(workspace) else target.book_dir}")
    print(f"Template:{' ':1}{target.template.relative_to(workspace) if target.template.is_relative_to(workspace) else target.template}")
    print(f"Binding: {binding}  ({g['binding_note']})")
    print(f"Pages:   {pages}  ({paper} paper)")
    print(f"Spine:   {g['spine_in']:.4f}\"  ({g['SPINE']} CSS px)")
    print(f"Spine text: {spine_cfg.status}  (policy={spine_cfg.policy}, min_pages={spine_cfg.min_pages}, edge_margin={spine_cfg.safe_margin_in:.3f}in)")
    if spine_cfg.show:
        print(f"Spine type: title={spine_cfg.title_font_px}px  series={spine_cfg.series_font_px}px  author={spine_cfg.author_font_px}px")
    print(f"Wrap:    {g['total_w_in']:.4f}\" × {g['total_h_in']:.4f}\"")
    print(f"CSS px:  {g['TOTAL_W']} × {g['TOTAL_H']}")
    print(f"Zones:   back x={g['BACK_LEFT']}  spine x={g['SPINE_LEFT']}  front x={g['FRONT_LEFT']}")
    print(f"Output:  {out}  [{dpi}dpi{'  preview' if preview else ''}]")
    print(f"Renderer:{' ':2}{renderer_name} ({renderer_exe})")
    print(f"{'─'*58}")

    if renderer_name == "weasyprint":
        r = render_with_weasyprint(html, out, workspace)
    else:
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=90)
        except subprocess.TimeoutExpired as e:
            tmp.unlink(missing_ok=True)
            sys.exit(f"Renderer timed out after {e.timeout} seconds: {renderer_name} ({renderer_exe})")
        except FileNotFoundError as e:
            tmp.unlink(missing_ok=True)
            sys.exit(f"Renderer executable disappeared or is not executable: {e}")
    tmp.unlink(missing_ok=True)

    if out.exists() and out.stat().st_size > 1000:
        kb = out.stat().st_size / 1024
        print(f"✓  {out}  ({kb:.0f} KB)")
        warns = [l for l in r.stderr.splitlines() if l.strip() and "QStandardPaths" not in l]
        for w in warns[:4]:
            print(f"   {w}")
    else:
        print("✗  Generation failed", file=sys.stderr)
        print(r.stderr, file=sys.stderr)
        sys.exit(1)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("book_dir", nargs="?", help="Book/booklet directory containing book.env and cover.html, e.g. book1 or booklets/marriage-and-family.")
    ap.add_argument("--pdf", default=None, metavar="FILE", help="Interior PDF; page count is read from it automatically. Defaults to dist/<BOOK_OUTPUT_BASENAME>-print.pdf.")
    ap.add_argument("--paper", choices=["cream", "white"], default=None, help="Paper color/thickness. Defaults to BOOK_COVER_PAPER or cream.")
    ap.add_argument("--binding", choices=["paperback", "hardcover"], default="paperback")
    ap.add_argument("--all-bindings", action="store_true", help="Render both paperback and hardcover for each selected book.")
    ap.add_argument("--preview", action="store_true")
    ap.add_argument("--all", action="store_true", help="Discover all directories with book.env and cover.html; no hard-coded book list is used.")
    ap.add_argument("--output-dir", default="dist")
    ap.add_argument(
        "--renderer",
        choices=["auto", "weasyprint", "wkhtmltopdf", "chrome", "chromium"],
        default="auto",
        help="PDF renderer. Default: auto, preferring WeasyPrint, then wkhtmltopdf, then Chrome/Chromium.",
    )
    args = ap.parse_args()

    if args.all and args.book_dir:
        ap.error("use either a book_dir argument or --all, not both")
    if not args.all and not args.book_dir:
        ap.error("specify a book_dir containing book.env, or use --all")
    if args.all and args.pdf:
        ap.error("--pdf can only be used with one book_dir; page counts differ by book")

    workspace = git_workspace_root()
    targets = discover_cover_targets(workspace) if args.all else [load_cover_target(args.book_dir, workspace)]
    if not targets:
        sys.exit("No cover targets found. A target must contain book.env and cover.html.")

    bindings = ["paperback", "hardcover"] if args.all_bindings else [args.binding]

    for target in targets:
        pages = resolve_pages(target, args, workspace)
        paper = args.paper or target.default_paper
        for binding in bindings:
            render(target, pages, paper, binding, args.preview, args.output_dir, workspace, args.renderer)
    print("\nDone.")


if __name__ == "__main__":
    main()
