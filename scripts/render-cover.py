#!/usr/bin/env python3
"""
render.py — KDP full-wrap cover renderer for lymanepp.com.

Usage
─────
  python3 render.py --book wss1                        # default 309pp
  python3 render.py --book wss1 --pdf interior.pdf     # reads page count from PDF
  python3 render.py --book wss1 --pages 315            # explicit override
  python3 render.py --book wss1 --pdf book.pdf --pages 315  # --pages wins
  python3 render.py --book wss1 --preview              # fast 96dpi proof
  python3 render.py --book wss1 --paper white
  python3 render.py --book left --pdf left-interior.pdf

Page count resolution order
────────────────────────────
  1. --pages N          (explicit, always wins)
  2. --pdf FILE         (reads page count from the interior PDF automatically)
  3. book default       (wss1=309, wss2=329, left=360)

KDP spine formula
─────────────────
  Cream paper: pages × 0.0025 inches
  White paper: pages × 0.002347 inches
  Bleed: 0.125 inches all sides
  Trim:  6.0 × 9.0 inches

Editing text
────────────
  Open the HTML template and search EDIT — every editable string is flagged.
  For WSS Vol 2: swap the blurb blocks (HTML comments mark them),
  change Vol. I → Vol. II and Volume One → Volume Two, then run --book wss2.
"""

import argparse, os, re, subprocess, sys

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

PAPER = { "cream": 0.0025, "white": 0.002347 }
BLEED = 0.125
TRIM_W, TRIM_H = 6.0, 9.0
CSS_DPI = 96

BOOKS = {
    "wss1": {"template": "cover-wss1.html", "pages": 309, "out": "wss1-cover.pdf", "label": "WSS Volume 1"},
    "wss2": {"template": "cover-wss2.html", "pages": 329, "out": "wss2-cover.pdf", "label": "WSS Volume 2"},
    "left": {"template": "cover-left.html","pages": 360, "out": "left-cover.pdf", "label": "How the Left Lost Its Grip on Reality"},
}

def geo(pages, paper="cream"):
    spine_in  = pages * PAPER[paper]
    total_w   = TRIM_W * 2 + spine_in + BLEED * 2
    total_h   = TRIM_H + BLEED * 2
    bleed_px  = round(BLEED   * CSS_DPI, 1)
    face_px   = round(TRIM_W  * CSS_DPI, 1)
    spine_px  = round(spine_in * CSS_DPI, 1)
    total_w_px= round(total_w  * CSS_DPI, 1)
    total_h_px= round(total_h  * CSS_DPI, 1)
    return {
        "spine_in": spine_in, "total_w_in": total_w, "total_h_in": total_h,
        "BLEED":    bleed_px,
        "FACE":     face_px,
        "SPINE":    spine_px,
        "TOTAL_W":  total_w_px,
        "TOTAL_H":  total_h_px,
        "BACK_LEFT":  bleed_px,
        "SPINE_LEFT": round(bleed_px + face_px, 1),
        "FRONT_LEFT": round(bleed_px + face_px + spine_px, 1),
        # Spine rotation helpers (rotate(90deg) container positioning)
        "SPINE_ROT_L": round(spine_px / 2 - total_h_px / 2, 1),
        "SPINE_ROT_T": round(total_h_px / 2 - spine_px / 2, 1),
        "SPINE_ROT_H": spine_px,
    }

def render(book_id, pages, paper, preview, outdir):
    cfg = BOOKS[book_id]
    g   = geo(pages, paper)
    here = os.path.dirname(os.path.abspath(__file__))
    tmpl = os.path.join(here, cfg["template"])
    if not os.path.exists(tmpl):
        sys.exit(f"Template not found: {tmpl}")

    html = open(tmpl).read()
    for k, v in g.items():
        html = html.replace(f"{{{{{k}}}}}", str(v))

    tmp = os.path.join(here, f"_tmp_{book_id}.html")
    open(tmp, "w").write(html)

    os.makedirs(outdir, exist_ok=True)
    suf = "-preview" if preview else ""
    out = os.path.join(outdir, cfg["out"].replace(".pdf", f"{suf}.pdf"))
    dpi = 96 if preview else 300

    cmd = [
        "wkhtmltopdf",
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
        tmp, out,
    ]

    print(f"\n{'─'*58}")
    print(f"Book:    {cfg['label']}")
    print(f"Pages:   {pages}  ({paper} paper)")
    print(f"Spine:   {g['spine_in']:.4f}\"  ({g['SPINE']} CSS px)")
    print(f"Wrap:    {g['total_w_in']:.4f}\" × {g['total_h_in']:.4f}\"")
    print(f"CSS px:  {g['TOTAL_W']} × {g['TOTAL_H']}")
    print(f"Zones:   back x={g['BACK_LEFT']}  spine x={g['SPINE_LEFT']}  front x={g['FRONT_LEFT']}")
    print(f"Output:  {out}  [{dpi}dpi{'  preview' if preview else ''}]")
    print(f"{'─'*58}")

    r = subprocess.run(cmd, capture_output=True, text=True)
    os.unlink(tmp)

    if os.path.exists(out) and os.path.getsize(out) > 1000:
        kb = os.path.getsize(out) / 1024
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
    ap.add_argument("--paper",   choices=["cream","white"], default="cream")
    ap.add_argument("--preview", action="store_true")
    ap.add_argument("--all",     action="store_true")
    ap.add_argument("--output-dir", default="output")
    args = ap.parse_args()

    targets = list(BOOKS) if args.all else ([args.book] if args.book else None)
    if not targets:
        ap.error("specify --book BOOK or --all")

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

    for b in targets:
        pages = resolved_pages if resolved_pages is not None else BOOKS[b]["pages"]
        render(b, pages, args.paper, args.preview, args.output_dir)
    print("\nDone.")

if __name__ == "__main__":
    main()
