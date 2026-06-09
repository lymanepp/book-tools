#!/usr/bin/env python3
"""
render-cover.py — KDP full-wrap cover renderer for lymanepp.com.

Usage
─────
  tools/bin/render-cover.py --book wss1 --binding paperback
  tools/bin/render-cover.py --book wss1 --binding hardcover
  tools/bin/render-cover.py --book wss1 --pdf dist/what-scripture-says-vol1-print.pdf
  tools/bin/render-cover.py --book wss1 --pages 315
  tools/bin/render-cover.py --book wss1 --preview
  tools/bin/render-cover.py --all --all-bindings

Page count resolution order
────────────────────────────
  1. --pages N          (explicit, always wins)
  2. --pdf FILE         (reads page count from the interior PDF automatically)
  3. book default       (wss1=309, wss2=329, left=360)

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

Editing text
────────────
  Open the HTML template and search EDIT — every editable string is flagged.
"""

import argparse, math, os, re, shutil, subprocess, sys
from pathlib import Path

def page_count_from_pdf(path: str) -> int:
    """Return the page count of a PDF file using pypdf."""
    try:
        from pypdf import PdfReader
    except ImportError:
        sys.exit("pypdf is required to use --pdf.\n"
                 "Install: pip3 install pypdf --break-system-packages")
    try:
        reader = PdfReader(path)
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
HC_OUTER = 0.635          # Horizontal outside/wrap+margin allowance.
HC_HINGE = 0.197          # Hinge allowance on each side of the spine.
HC_VERTICAL_OUTER = 0.7085 # Top/bottom outside/wrap+board allowance.

BOOKS = {
    "wss1": {
        "template": "book1/cover.html",
        "pages": 309,
        "prefix": "what-scripture-says-vol1",
        "label": "WSS Volume 1",
    },
    "wss2": {
        "template": "book2/cover.html",
        "pages": 329,
        "prefix": "what-scripture-says-vol2",
        "label": "WSS Volume 2",
    },
    "left": {
        "template": "cover-left.html",
        "pages": 360,
        "prefix": "how-the-left-lost-its-grip-on-reality",
        "label": "How the Left Lost Its Grip on Reality",
    },
}


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
        sys.exit("Could not determine the Git workspace root. Run this from inside the repository.")


def resolve_template(template: str, workspace: Path) -> Path:
    """Resolve an HTML template path from the Git workspace root."""
    tmpl = (workspace / template).resolve()
    if not tmpl.is_file():
        sys.exit(f"Template not found: {tmpl}")
    return tmpl


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
        "This script now supports either wkhtmltopdf or headless Chrome/Chromium. "
        "Your container's apt repositories do not appear to provide wkhtmltopdf, "
        "so install Chromium instead inside the dev container:\n\n"
        "  sudo apt-get update && sudo apt-get install -y chromium\n\n"
        "Then rerun:\n\n"
        "  tools/bin/render-cover.py --book wss1\n\n"
        "Optional overrides:\n"
        "  CHROME=/full/path/to/chromium tools/bin/render-cover.py --book wss1\n"
        "  WKHTMLTOPDF=/full/path/to/wkhtmltopdf tools/bin/render-cover.py --book wss1\n\n"
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
    safe = px(0.635)          # KDP hardcover text/image safe inset from book edge.
    content = round(safe + 13, 1)  # Keep text off the decorative frame itself.
    barcode_bottom = px(0.76) # KDP hardcover barcode bottom clearance.
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
        right_outer_in = BLEED
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
        right_outer_in = HC_OUTER
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

def render(book_id, pages, paper, binding, preview, outdir, workspace, requested_renderer):
    cfg = BOOKS[book_id]
    g = geo(pages, paper, binding)
    tmpl = resolve_template(cfg["template"], workspace)

    renderer_name, renderer_exe = choose_renderer(requested_renderer)

    html = tmpl.read_text()
    for k, v in g.items():
        html = html.replace(f"{{{{{k}}}}}", str(v))

    if binding == "hardcover":
        html = inject_hardcover_safe_layout(html, g)

    if renderer_name in ("chrome", "weasyprint"):
        html = inject_print_page_size(html, g)

    tmp = workspace / f"_tmp_{book_id}.html"
    tmp.write_text(html)

    outdir = Path(outdir)
    if not outdir.is_absolute():
        outdir = workspace / outdir
    outdir.mkdir(parents=True, exist_ok=True)

    suf = "-preview" if preview else ""
    out = outdir / f"{cfg['prefix']}-{binding}-cover{suf}.pdf"
    dpi = 96 if preview else 300

    if renderer_name == "wkhtmltopdf":
        cmd = build_wkhtmltopdf_cmd(renderer_exe, tmp, out, g, dpi)
    elif renderer_name == "chrome":
        cmd = build_chrome_cmd(renderer_exe, tmp, out, g)
    else:
        cmd = ["weasyprint"]

    print(f"\n{'─'*58}")
    print(f"Book:    {cfg['label']}")
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
        for w in warns[:4]: print(f"   {w}")
    else:
        print("✗  Generation failed", file=sys.stderr)
        print(r.stderr, file=sys.stderr)
        sys.exit(1)

def main():
    ap = argparse.ArgumentParser(description=__doc__,
         formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--book",    choices=list(BOOKS), default=None)
    ap.add_argument("--pages",   type=int, default=None,
        help="Final page count (overrides --pdf). Defaults: wss1=309, wss2=329, left=360.")
    ap.add_argument("--pdf", default=None, metavar="FILE",
        help="Path to the interior PDF; page count is read from it automatically. "
             "Overridden by --pages if both are supplied.")
    ap.add_argument("--paper",   choices=["cream", "white"], default="cream")
    ap.add_argument("--binding", choices=["paperback", "hardcover"], default="paperback")
    ap.add_argument("--all-bindings", action="store_true", help="Render both paperback and hardcover for each selected book.")
    ap.add_argument("--preview", action="store_true")
    ap.add_argument("--all",     action="store_true")
    ap.add_argument("--output-dir", default="dist")
    ap.add_argument(
        "--renderer",
        choices=["auto", "weasyprint", "wkhtmltopdf", "chrome", "chromium"],
        default="auto",
        help="PDF renderer. Default: auto, preferring WeasyPrint, then wkhtmltopdf, then Chrome/Chromium.",
    )
    args = ap.parse_args()

    targets = list(BOOKS) if args.all else ([args.book] if args.book else None)
    if not targets:
        ap.error("specify --book BOOK or --all")
    if args.all and args.pdf:
        ap.error("--pdf can only be used with a single --book; page counts differ by book. Use per-book commands or rely on defaults with --all.")

    # Resolve page count: explicit --pages > --pdf > book default
    if args.pages:
        resolved_pages = args.pages
    elif args.pdf:
        if not os.path.isfile(args.pdf):
            ap.error(f"PDF not found: {args.pdf}")
        resolved_pages = page_count_from_pdf(args.pdf)
        print(f"Page count from PDF: {resolved_pages}  ({args.pdf})")
    else:
        resolved_pages = None  # will fall back to per-book default below

    workspace = git_workspace_root()

    bindings = ["paperback", "hardcover"] if args.all_bindings else [args.binding]

    for b in targets:
        pages = resolved_pages if resolved_pages is not None else BOOKS[b]["pages"]
        for binding in bindings:
            render(b, pages, args.paper, binding, args.preview, args.output_dir, workspace, args.renderer)
    print("\nDone.")

if __name__ == "__main__":
    main()
