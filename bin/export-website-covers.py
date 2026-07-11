#!/usr/bin/env python3
"""Export website-ready book cover images from built KDP cover PDFs.

The book repository owns full-wrap paperback cover rendering. This helper crops
only the front 6x9 trim panel from the generated paperback cover PDFs and writes
WebP assets for the author website to dist/website-covers/.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

from PIL import Image
from pypdf import PdfReader

PDF_POINTS_PER_INCH = 72.0
BLEED_IN = 0.125
FRONT_TRIM_WIDTH_IN = 6.0
FRONT_TRIM_HEIGHT_IN = 9.0
DEFAULT_DPI = 300
DEFAULT_OUTPUT_SIZE = (900, 1350)
DEFAULT_WEBP_QUALITY = 88


@dataclass(frozen=True)
class CoverSpec:
    source: str
    output: str


COVER_SPECS: tuple[CoverSpec, ...] = (
    CoverSpec('what-scripture-says-vol1-paperback-cover.pdf', 'confronting-the-world.webp'),
    CoverSpec('what-scripture-says-vol2-paperback-cover.pdf', 'submitting-the-church.webp'),
)


def fail(message: str) -> None:
    raise SystemExit(f'export-website-covers: {message}')


def require_command(command: str) -> None:
    if shutil.which(command) is None:
        fail(f'Required command not found: {command}. Install poppler-utils.')


def parse_output_size(value: str) -> tuple[int, int]:
    try:
        width_text, height_text = value.lower().split('x', 1)
        width = int(width_text)
        height = int(height_text)
    except ValueError as exc:
        raise argparse.ArgumentTypeError('expected WIDTHxHEIGHT, for example 900x1350') from exc

    if width <= 0 or height <= 0:
        raise argparse.ArgumentTypeError('output size dimensions must be positive')

    return width, height


def page_size_points(pdf_path: Path) -> tuple[float, float]:
    reader = PdfReader(str(pdf_path))
    if not reader.pages:
        fail(f'{pdf_path} has no pages')

    page = reader.pages[0]
    box = page.mediabox
    return float(box.width), float(box.height)


def points_to_pixels(points: float, dpi: int) -> int:
    return round(points / PDF_POINTS_PER_INCH * dpi)


def front_trim_box_pixels(pdf_path: Path, dpi: int) -> tuple[int, int, int, int]:
    width_pt, height_pt = page_size_points(pdf_path)
    bleed_pt = BLEED_IN * PDF_POINTS_PER_INCH
    trim_width_pt = FRONT_TRIM_WIDTH_IN * PDF_POINTS_PER_INCH
    trim_height_pt = FRONT_TRIM_HEIGHT_IN * PDF_POINTS_PER_INCH

    if width_pt < trim_width_pt + bleed_pt or height_pt < trim_height_pt + bleed_pt:
        fail(f'Unexpected KDP cover geometry for {pdf_path}: {width_pt:g}pt x {height_pt:g}pt')

    # Pillow crop coordinates use the raster's top-left origin. The front trim
    # panel starts at total width minus right bleed minus the 6in trim width.
    left = points_to_pixels(width_pt - bleed_pt - trim_width_pt, dpi)
    top = points_to_pixels(bleed_pt, dpi)
    right = left + points_to_pixels(trim_width_pt, dpi)
    bottom = top + points_to_pixels(trim_height_pt, dpi)
    return left, top, right, bottom


def render_pdf_to_png(pdf_path: Path, output_base: Path, dpi: int) -> Path:
    subprocess.run(
        ['pdftocairo', '-singlefile', '-png', '-r', str(dpi), str(pdf_path), str(output_base)],
        check=True,
    )
    png_path = output_base.with_suffix('.png')
    if not png_path.exists():
        fail(f'pdftocairo did not produce expected image: {png_path}')
    return png_path


def find_source_pdf(source_dir: Path, filename: str) -> Path:
    direct_path = source_dir / filename
    if direct_path.exists():
        return direct_path

    matches = sorted(source_dir.rglob(filename)) if source_dir.exists() else []
    if not matches:
        fail(f'Missing source PDF under {source_dir}: {filename}')
    if len(matches) > 1:
        rendered = ', '.join(str(match) for match in matches)
        fail(f'Ambiguous source PDF name {filename}; found multiple matches: {rendered}')
    return matches[0]


def export_cover(
    spec: CoverSpec,
    source_dir: Path,
    output_dir: Path,
    dpi: int,
    output_size: tuple[int, int],
    quality: int,
) -> None:
    source_path = find_source_pdf(source_dir, spec.source)
    output_path = output_dir / spec.output

    print(f'export-website-covers: rendering {source_path}')
    with tempfile.TemporaryDirectory(prefix='wss-website-cover-') as temp_dir_name:
        rendered_base = Path(temp_dir_name) / 'rendered'
        rendered_png = render_pdf_to_png(source_path, rendered_base, dpi)
        crop_box = front_trim_box_pixels(source_path, dpi)

        output_dir.mkdir(parents=True, exist_ok=True)
        print(f'export-website-covers: writing {output_path}')
        with Image.open(rendered_png) as image:
            image.crop(crop_box).resize(output_size, Image.Resampling.LANCZOS).save(
                output_path,
                'WEBP',
                quality=quality,
                method=6,
            )


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description='Export website front-cover WebP assets from built paperback cover PDFs.')
    parser.add_argument('--source-dir', type=Path, default=Path('dist'), help='Directory containing built paperback cover PDFs.')
    parser.add_argument('--output-dir', type=Path, default=Path('dist/website-covers'), help='Directory for exported website WebP covers.')
    parser.add_argument('--dpi', type=int, default=int(os.environ.get('WEBSITE_COVER_DPI', DEFAULT_DPI)), help='Rasterization DPI for intermediate PNGs.')
    parser.add_argument('--output-size', type=parse_output_size, default=parse_output_size(os.environ.get('WEBSITE_COVER_OUTPUT_SIZE', '900x1350')), help='Final WebP size as WIDTHxHEIGHT.')
    parser.add_argument('--quality', type=int, default=int(os.environ.get('WEBSITE_COVER_QUALITY', DEFAULT_WEBP_QUALITY)), help='WebP quality, 1-100.')
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)

    if args.dpi <= 0:
        fail('--dpi must be positive')
    if not 1 <= args.quality <= 100:
        fail('--quality must be between 1 and 100')

    require_command('pdftocairo')

    for spec in COVER_SPECS:
        export_cover(spec, args.source_dir, args.output_dir, args.dpi, args.output_size, args.quality)

    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
