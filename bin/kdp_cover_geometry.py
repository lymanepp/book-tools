#!/usr/bin/env python3
"""KDP cover-geometry calculator.

This module is intentionally standalone: it has no dependency on the cover
renderer, and it can be unit-tested directly against KDP cover-calculator
numbers. The renderer should consume this module rather than reimplementing
KDP geometry inline.

The formulas below are calibrated from KDP's cover calculator for:
  - Binding: paperback / hardcover case laminate
  - Interior: black & white / standard color / premium color
  - Paper: white / cream where KDP allows the combination
  - Direction: left-to-right
  - Units: inches

The checked-in tests validate the 6×9 values used by the book pipeline.
The formulas are parameterized by trim size, with the current constants derived
from KDP's 6×9 calculator output.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

Binding = Literal["paperback", "hardcover"]
Paper = Literal["white", "cream"]
InteriorType = Literal["black_and_white", "standard_color", "premium_color"]
ReadingDirection = Literal["left_to_right"]

CSS_DPI = 96

SUPPORTED_BINDINGS = ("paperback", "hardcover")
SUPPORTED_PAPERS = ("white", "cream")
SUPPORTED_INTERIOR_TYPES = ("black_and_white", "standard_color", "premium_color")
SUPPORTED_READING_DIRECTIONS = ("left_to_right",)

# KDP paper-stack thickness, inches/page. The keys intentionally include the
# interior type because color interiors use a different stock from B&W white.
PAPER_THICKNESS = {
    ("black_and_white", "white"): 0.002252,
    ("black_and_white", "cream"): 0.002500,
    ("standard_color", "white"): 0.002252,
    ("premium_color", "white"): 0.002347,
}

INTERIOR_ALIASES = {
    "black_and_white": "black_and_white",
    "black-and-white": "black_and_white",
    "black and white": "black_and_white",
    "black & white": "black_and_white",
    "b&w": "black_and_white",
    "bw": "black_and_white",
    "standard_color": "standard_color",
    "standard-color": "standard_color",
    "standard color": "standard_color",
    "premium_color": "premium_color",
    "premium-color": "premium_color",
    "premium color": "premium_color",
}

PAPER_ALIASES = {
    "white": "white",
    "white_paper": "white",
    "white paper": "white",
    "cream": "cream",
    "cream_paper": "cream",
    "cream paper": "cream",
}

# Paperback KDP constants.
PB_BLEED = 0.125
PB_MARGIN = 0.125
PB_BARCODE_MARGIN_X = 0.250
PB_BARCODE_MARGIN_Y = 0.250

# Hardcover case-laminate KDP constants.
# KDP's 6×9 calculator values are:
#   Wrap  = 0.591" displayed, modeled as 0.5905" internally
#   Hinge = 0.394" total, modeled as 0.197" on each side of the spine
#   Extra case-laminate spine allowance = 0.189"
#   Total height = trim_h + 2*0.7085 = 10.417" for 6×9.
HC_WRAP = 0.5905
HC_HINGE_PER_SIDE = 0.197
HC_SPINE_EXTRA = 0.189
HC_VERTICAL_OUTER = 0.7085
HC_MARGIN = 0.125
HC_BARCODE_MARGIN_X = 0.250
HC_BARCODE_MARGIN_Y = 0.375

SPINE_MARGIN = 0.0625


@dataclass(frozen=True)
class KdpCoverGeometry:
    binding: Binding
    interior_type: InteriorType
    paper: Paper
    page_count: int
    trim_width_in: float
    trim_height_in: float
    paper_thickness_in: float

    full_cover_width_in: float
    full_cover_height_in: float
    front_cover_width_in: float
    front_cover_height_in: float
    safe_area_width_in: float
    safe_area_height_in: float

    spine_width_in: float
    spine_height_in: float
    spine_safe_area_width_in: float
    spine_safe_area_height_in: float
    spine_margin_width_in: float
    spine_margin_height_in: float

    bleed_width_in: float | None
    bleed_height_in: float | None
    margin_width_in: float
    margin_height_in: float
    wrap_width_in: float | None
    wrap_height_in: float | None
    hinge_width_in: float | None
    hinge_height_in: float | None
    barcode_margin_width_in: float
    barcode_margin_height_in: float

    # Renderer-layout helpers. These describe where the renderer's panels
    # begin on the full-wrap canvas. For hardcover, the front/back faces are
    # trim-sized faces separated from the spine by one hinge panel per side.
    outer_left_in: float
    outer_top_in: float
    face_width_in: float
    panel_top_in: float
    panel_height_in: float
    hinge_per_side_in: float

    @property
    def paper_stack_spine_width_in(self) -> float:
        return self.page_count * self.paper_thickness_in

    def as_kdp_table(self) -> dict[str, tuple[float, float]]:
        """Return KDP-calculator-style rows as {description: (width, height)}."""
        rows: dict[str, tuple[float, float]] = {
            "Full Cover": (self.full_cover_width_in, self.full_cover_height_in),
            "Front Cover": (self.front_cover_width_in, self.front_cover_height_in),
            "Spine": (self.spine_width_in, self.spine_height_in),
            "Spine Safe Area": (self.spine_safe_area_width_in, self.spine_safe_area_height_in),
            "Spine Margin": (self.spine_margin_width_in, self.spine_margin_height_in),
            "Barcode Margin": (self.barcode_margin_width_in, self.barcode_margin_height_in),
        }
        if self.binding == "paperback":
            rows["Safe Area"] = (self.safe_area_width_in, self.safe_area_height_in)
            rows["Bleed"] = (self.bleed_width_in or 0.0, self.bleed_height_in or 0.0)
            rows["Margin"] = (self.margin_width_in, self.margin_height_in)
        else:
            rows["Margin"] = (self.margin_width_in, self.margin_height_in)
            rows["Wrap"] = (self.wrap_width_in or 0.0, self.wrap_height_in or 0.0)
            rows["Hinge"] = (self.hinge_width_in or 0.0, self.hinge_height_in or 0.0)
        return rows


def px(inches: float) -> float:
    """Convert inches to CSS pixels and keep output stable/readable."""
    return round(inches * CSS_DPI, 1)


def normalize_interior_type(interior_type: str) -> InteriorType:
    normalized = INTERIOR_ALIASES.get(str(interior_type).strip().lower())
    if normalized is None:
        allowed = ", ".join(SUPPORTED_INTERIOR_TYPES)
        raise ValueError(f"Unsupported interior type: {interior_type!r}; use one of: {allowed}")
    return normalized  # type: ignore[return-value]


def normalize_paper(paper: str) -> Paper:
    normalized = PAPER_ALIASES.get(str(paper).strip().lower())
    if normalized is None:
        allowed = ", ".join(SUPPORTED_PAPERS)
        raise ValueError(f"Unsupported paper type: {paper!r}; use one of: {allowed}")
    return normalized  # type: ignore[return-value]


def _validate(
    binding: str,
    paper: str,
    page_count: int,
    trim_size: tuple[float, float],
    interior_type: str,
    reading_direction: str,
) -> tuple[Binding, Paper, InteriorType, float, float]:
    if binding not in SUPPORTED_BINDINGS:
        raise ValueError(f"Unsupported binding: {binding!r}; use paperback or hardcover")
    binding_t: Binding = binding  # type: ignore[assignment]

    paper_t = normalize_paper(paper)
    interior_t = normalize_interior_type(interior_type)

    if (interior_t, paper_t) not in PAPER_THICKNESS:
        supported = ", ".join(f"{i}/{p}" for i, p in sorted(PAPER_THICKNESS))
        raise ValueError(
            f"Unsupported interior/paper combination: {interior_t}/{paper_t}. "
            f"Supported combinations: {supported}"
        )
    if reading_direction != "left_to_right":
        raise ValueError("Only left_to_right cover geometry is modeled by this calculator")
    if not isinstance(page_count, int) or page_count < 1:
        raise ValueError(f"page_count must be a positive integer, got {page_count!r}")
    if len(trim_size) != 2:
        raise ValueError("trim_size must be a (width, height) tuple")
    trim_w, trim_h = float(trim_size[0]), float(trim_size[1])
    if trim_w <= 0 or trim_h <= 0:
        raise ValueError(f"trim_size values must be positive, got {trim_size!r}")
    return binding_t, paper_t, interior_t, trim_w, trim_h


def calculate_kdp_cover_geometry(
    *,
    binding: str,
    paper: str,
    page_count: int,
    trim_size: tuple[float, float] = (6.0, 9.0),
    interior_type: str = "black_and_white",
    reading_direction: str = "left_to_right",
) -> KdpCoverGeometry:
    """Calculate KDP full-wrap cover geometry in inches.

    Parameters are explicit because KDP's cover calculator is driven by the
    same concepts: binding type, interior type, paper type, reading direction,
    trim size, and formatted page count.
    """
    binding_t, paper_t, interior_t, trim_w, trim_h = _validate(
        binding, paper, page_count, trim_size, interior_type, reading_direction
    )
    thickness = PAPER_THICKNESS[(interior_t, paper_t)]
    paper_stack_spine = page_count * thickness

    if binding_t == "paperback":
        spine = paper_stack_spine
        full_w = 2 * trim_w + spine + 2 * PB_BLEED
        full_h = trim_h + 2 * PB_BLEED
        front_w = trim_w
        front_h = trim_h
        safe_w = trim_w - PB_MARGIN
        safe_h = trim_h - 2 * PB_MARGIN
        spine_h = trim_h
        spine_safe_w = max(0.0, spine - 2 * SPINE_MARGIN)
        spine_safe_h = trim_h - 2 * PB_MARGIN
        return KdpCoverGeometry(
            binding=binding_t,
            interior_type=interior_t,
            paper=paper_t,
            page_count=page_count,
            trim_width_in=trim_w,
            trim_height_in=trim_h,
            paper_thickness_in=thickness,
            full_cover_width_in=full_w,
            full_cover_height_in=full_h,
            front_cover_width_in=front_w,
            front_cover_height_in=front_h,
            safe_area_width_in=safe_w,
            safe_area_height_in=safe_h,
            spine_width_in=spine,
            spine_height_in=spine_h,
            spine_safe_area_width_in=spine_safe_w,
            spine_safe_area_height_in=spine_safe_h,
            spine_margin_width_in=SPINE_MARGIN,
            spine_margin_height_in=SPINE_MARGIN,
            bleed_width_in=PB_BLEED,
            bleed_height_in=PB_BLEED,
            margin_width_in=PB_MARGIN,
            margin_height_in=PB_MARGIN,
            wrap_width_in=None,
            wrap_height_in=None,
            hinge_width_in=None,
            hinge_height_in=None,
            barcode_margin_width_in=PB_BARCODE_MARGIN_X,
            barcode_margin_height_in=PB_BARCODE_MARGIN_Y,
            outer_left_in=PB_BLEED,
            outer_top_in=0.0,
            face_width_in=trim_w,
            panel_top_in=0.0,
            panel_height_in=full_h,
            hinge_per_side_in=0.0,
        )

    # Hardcover case laminate.
    spine = paper_stack_spine + HC_SPINE_EXTRA
    full_w = 2 * trim_w + spine + 2 * HC_WRAP + 2 * HC_HINGE_PER_SIDE
    full_h = trim_h + 2 * HC_VERTICAL_OUTER
    front_w = trim_w + HC_HINGE_PER_SIDE
    front_h = full_h - 2 * HC_WRAP
    spine_safe_w = max(0.0, spine - 2 * SPINE_MARGIN)
    spine_safe_h = front_h - 2 * HC_MARGIN
    return KdpCoverGeometry(
        binding=binding_t,
        interior_type=interior_t,
        paper=paper_t,
        page_count=page_count,
        trim_width_in=trim_w,
        trim_height_in=trim_h,
        paper_thickness_in=thickness,
        full_cover_width_in=full_w,
        full_cover_height_in=full_h,
        front_cover_width_in=front_w,
        front_cover_height_in=front_h,
        safe_area_width_in=front_w - HC_MARGIN,
        safe_area_height_in=front_h - 2 * HC_MARGIN,
        spine_width_in=spine,
        spine_height_in=front_h,
        spine_safe_area_width_in=spine_safe_w,
        spine_safe_area_height_in=spine_safe_h,
        spine_margin_width_in=SPINE_MARGIN,
        spine_margin_height_in=SPINE_MARGIN,
        bleed_width_in=None,
        bleed_height_in=None,
        margin_width_in=HC_MARGIN,
        margin_height_in=HC_MARGIN,
        wrap_width_in=HC_WRAP,
        wrap_height_in=HC_WRAP,
        hinge_width_in=2 * HC_HINGE_PER_SIDE,
        hinge_height_in=full_h,
        barcode_margin_width_in=HC_BARCODE_MARGIN_X,
        barcode_margin_height_in=HC_BARCODE_MARGIN_Y,
        outer_left_in=HC_WRAP,
        outer_top_in=HC_WRAP,
        face_width_in=trim_w,
        panel_top_in=HC_WRAP,
        panel_height_in=front_h,
        hinge_per_side_in=HC_HINGE_PER_SIDE,
    )


def cover_geometry_tokens(
    pages: int,
    paper: str = "cream",
    binding: str = "paperback",
    trim_size: tuple[float, float] = (6.0, 9.0),
    interior_type: str = "black_and_white",
) -> dict[str, float | int | str]:
    """Return the legacy renderer token dictionary for a KDP geometry."""
    g = calculate_kdp_cover_geometry(
        binding=binding,
        paper=paper,
        page_count=pages,
        trim_size=trim_size,
        interior_type=interior_type,
    )

    total_w_px = px(g.full_cover_width_in)
    total_h_px = px(g.full_cover_height_in)
    outer_px = px(g.outer_left_in)
    top_outer_px = px(g.outer_top_in)
    face_px = px(g.face_width_in)
    spine_px = px(g.spine_width_in)
    hinge_px = px(g.hinge_per_side_in)
    panel_top_px = px(g.panel_top_in)
    panel_h_px = px(g.panel_height_in)

    back_left_px = outer_px
    back_hinge_left_px = round(back_left_px + face_px, 1)
    spine_left_px = round(back_left_px + face_px + hinge_px, 1)
    front_hinge_left_px = round(spine_left_px + spine_px, 1)
    front_left_px = round(front_hinge_left_px + hinge_px, 1)

    return {
        "binding": g.binding,
        "binding_note": "paperback bleed" if g.binding == "paperback" else "hardcover case laminate",
        "interior_type": g.interior_type,
        "PAGES": g.page_count,
        "spine_in": g.spine_width_in,
        "paper_stack_spine_in": g.paper_stack_spine_width_in,
        "total_w_in": g.full_cover_width_in,
        "total_h_in": g.full_cover_height_in,
        "outer_in": g.outer_left_in,
        "top_outer_in": g.outer_top_in,
        "hinge_in": g.hinge_per_side_in,
        "panel_h_in": g.panel_height_in,
        "BLEED": px(PB_BLEED),
        "WRAP": px(g.wrap_width_in if g.binding == "hardcover" else PB_BLEED),
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
        "SPINE_ROT_L": round(spine_px / 2 - panel_h_px / 2, 1),
        "SPINE_ROT_T": round(panel_h_px / 2 - spine_px / 2, 1),
        "SPINE_ROT_H": spine_px,
    }


__all__ = [
    "Binding",
    "Paper",
    "InteriorType",
    "ReadingDirection",
    "CSS_DPI",
    "PAPER_THICKNESS",
    "SUPPORTED_BINDINGS",
    "SUPPORTED_PAPERS",
    "SUPPORTED_INTERIOR_TYPES",
    "SUPPORTED_READING_DIRECTIONS",
    "KdpCoverGeometry",
    "calculate_kdp_cover_geometry",
    "cover_geometry_tokens",
    "normalize_interior_type",
    "normalize_paper",
    "px",
]
