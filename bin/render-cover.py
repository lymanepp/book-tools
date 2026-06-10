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
  python3 tools/bin/render-cover.py book1 --pages 315
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
  BOOK_COVER_PAGE_COUNT       Fallback page count when --pages/--pdf is omitted
  BOOK_COVER_TEMPLATE         Optional; defaults to cover.html
  BOOK_COVER_PAPER            Optional; cream or white; defaults to cream

Page count resolution order
────────────────────────────
  1. --pages N
  2. --pdf FILE
  3. BOOK_COVER_PAGE_COUNT from book.env

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
    spine = pages × paper thickness
    width = horizontal outer + back + hinge + spine + hinge + front + horizontal outer
    height = vertical outer + trim height + vertical outer
    non-background artwork is then inset to KDP hardcover safe zones

  Paper thickness:
    cream = 0.0025 inches/page
    white = 0.002252 inches/page

  Trim: 6.0 × 9.0 inches.
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


PAPER = {"cream": 0.0025, "white": 0.002252}
BLEED = 0.125
TRIM_W, TRIM_H = 6.0, 9.0
CSS_DPI = 96

# KDP hardcover/case-laminate geometry constants, in inches.
# These are calibrated to KDP's current cover-calculator output for 6×9
# case-laminate hardcovers. The KDP uploader validates the final PDF
# dimensions, so these constants must match the generated template size.
#
# For 6×9, 309-page cream-paper hardcover, KDP expects 14.437×10.417.
# Formula used here:
#   width  = 2*trim_w + spine + 2*HC_OUTER + 2*HC_HINGE
#   height = trim_h + 2*HC_VERTICAL_OUTER
HC_OUTER = 0.635
HC_HINGE = 0.197
HC_VERTICAL_OUTER = 0.7085


@dataclass(frozen=True)
class CoverTarget:
    book_dir: Path
    env_path: Path
    template: Path
    title: str
    output_basename: str
    default_pages: int | None
    default_paper: str

    @property
    def label(self) -> str:
        return self.title or self.output_basename

    @property
    def safe_id(self) -> str:
        rel = str(self.book_dir).replace(os.sep, "-")
        return re.sub(r"[^A-Za-z0-9_.-]+", "-", rel).strip("-._") or "cover"


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

    pages = optional_int(cfg.get("BOOK_COVER_PAGE_COUNT"), "BOOK_COVER_PAGE_COUNT", env_path)

    return CoverTarget(
        book_dir=book_dir,
        env_path=env_path,
        template=template,
        title=cfg["BOOK_TITLE"],
        output_basename=cfg["BOOK_OUTPUT_BASENAME"],
        default_pages=pages,
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
    spine_in = pages * PAPER[paper]

    if binding == "paperback":
        left_outer_in = BLEED
        top_outer_in = 0.0
        panel_top_in = 0.0
        face_in = TRIM_W
        panel_h_in = TRIM_H + 2 * BLEED
        hinge_in = 0.0
        total_w_in = 2 * TRIM_W + spine_in + 2 * BLEED
        total_h_in = TRIM_H + 2 * BLEED
        binding_note = "paperback bleed"
    elif binding == "hardcover":
        left_outer_in = HC_OUTER
        top_outer_in = HC_VERTICAL_OUTER
        panel_top_in = HC_VERTICAL_OUTER
        face_in = TRIM_W
        panel_h_in = TRIM_H
        hinge_in = HC_HINGE
        total_w_in = 2 * TRIM_W + spine_in + 2 * HC_OUTER + 2 * HC_HINGE
        total_h_in = TRIM_H + 2 * HC_VERTICAL_OUTER
        binding_note = "hardcover case laminate"
    else:
        raise ValueError(f"Unsupported binding: {binding}")

    total_w_px = px(total_w_in)
    total_h_px = px(total_h_in)
    outer_px = px(left_outer_in)
    top_outer_px = px(top_outer_in)
    face_px = px(face_in)
    spine_px = px(spine_in)
    hinge_px = px(hinge_in)
    panel_top_px = px(panel_top_in)
    panel_h_px = px(panel_h_in)

    back_left_px = outer_px
    back_hinge_left_px = round(back_left_px + face_px, 1)
    spine_left_px = round(back_left_px + face_px + hinge_px, 1)
    front_hinge_left_px = round(spine_left_px + spine_px, 1)
    front_left_px = round(front_hinge_left_px + hinge_px, 1)

    return {
        "binding": binding,
        "binding_note": binding_note,
        "spine_in": spine_in,
        "total_w_in": total_w_in,
        "total_h_in": total_h_in,
        "outer_in": left_outer_in,
        "top_outer_in": top_outer_in,
        "hinge_in": hinge_in,
        "panel_h_in": panel_h_in,
        "BLEED": px(BLEED),
        "WRAP": px(HC_OUTER if binding == "hardcover" else BLEED),
        "OUTER": outer_px,
        "TOP_OUTER": top_outer_px,
        "HINGE": hinge_px,
        "FACE": face_px,
        "SPINE": spine_px,
        "TOTAL_W": total_w_px,
        "TOTAL_H": total_h_px,
        "PANEL_TOP": panel_top_px,
        "PANEL_H": panel_h_px,
        "BACK_LEFT": back_left_px,
        "BACK_HINGE_LEFT": back_hinge_left_px,
        "SPINE_LEFT": spine_left_px,
        "FRONT_HINGE_LEFT": front_hinge_left_px,
        "FRONT_LEFT": front_left_px,
        # Spine rotation helpers (rotate(90deg) container positioning)
        "SPINE_ROT_L": round(spine_px / 2 - panel_h_px / 2, 1),
        "SPINE_ROT_T": round(panel_h_px / 2 - spine_px / 2, 1),
        "SPINE_ROT_H": spine_px,
    }


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

    def repl(match: re.Match[str]) -> str:
        key = match.group(1).strip()
        value = replacements.get(key)
        if value is None:
            return match.group(0)
        return html_lib.escape(value) if key.startswith("BOOK_") else str(value)

    return re.sub(r"\{\{\s*([A-Za-z_][A-Za-z0-9_]*)\s*\}\}", repl, html)


def resolve_pages(target: CoverTarget, args: argparse.Namespace, workspace: Path) -> int:
    if args.pages is not None:
        return args.pages
    if args.pdf:
        pdf = resolve_under_workspace(args.pdf, workspace)
        if not pdf.is_file():
            raise SystemExit(f"PDF not found: {pdf}")
        pages = page_count_from_pdf(pdf)
        print(f"Page count from PDF: {pages}  ({pdf})")
        return pages
    if target.default_pages is not None:
        return target.default_pages
    raise SystemExit(
        f"No page count supplied for {target.book_dir}.\n"
        "Use --pages, use --pdf, or add BOOK_COVER_PAGE_COUNT to book.env."
    )


def render(target: CoverTarget, pages: int, paper: str, binding: str, preview: bool,
           outdir: str | Path, workspace: Path, requested_renderer: str) -> None:
    g = geo(pages, paper, binding)

    renderer_name, renderer_exe = choose_renderer(requested_renderer)

    raw_html = target.template.read_text(encoding="utf-8")
    html = inject_tokens(raw_html, g, target)

    if binding == "hardcover":
        html = inject_hardcover_safe_layout(html, g)

    if renderer_name in ("chrome", "weasyprint"):
        html = inject_print_page_size(html, g)

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
    ap.add_argument("--pages", type=int, default=None, help="Final page count. Overrides --pdf and BOOK_COVER_PAGE_COUNT.")
    ap.add_argument("--pdf", default=None, metavar="FILE", help="Interior PDF; page count is read from it automatically. Overridden by --pages.")
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

    if args.pages is not None and args.pages < 1:
        ap.error("--pages must be positive")
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
