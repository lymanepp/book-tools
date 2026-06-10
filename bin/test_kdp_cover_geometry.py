#!/usr/bin/env python3
"""Unit tests for KDP cover-calculator geometry.

These numbers come from KDP calculator screenshots captured for 6×9,
left-to-right books. They cover black-and-white white/cream paper, standard color white paper, and premium
color white paper across paperback/hardcover where captured at 76 and 400 pages.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools" / "bin"))

from kdp_cover_geometry import calculate_kdp_cover_geometry  # noqa: E402


class KdpCoverGeometryTests(unittest.TestCase):
    def assert_close(self, actual: float, expected: float, label: str) -> None:
        self.assertAlmostEqual(
            actual,
            expected,
            delta=0.00075,
            msg=f"{label}: expected {expected:.3f}, got {actual:.6f}",
        )

    def test_kdp_screenshot_dimensions(self) -> None:
        # binding, interior_type, paper, pages, full_w, full_h, front_w, front_h,
        # spine_w, spine_h, spine_safe_w, spine_safe_h,
        # margin_w, margin_h, barcode_w, barcode_h
        cases = [
            (
                "hardcover", "black_and_white", "white", 76,
                13.935, 10.417, 6.197, 9.236,
                0.360, 9.236, 0.235, 8.986,
                0.125, 0.125, 0.250, 0.375,
            ),
            (
                "hardcover", "black_and_white", "white", 400,
                14.665, 10.417, 6.197, 9.236,
                1.090, 9.236, 0.965, 8.986,
                0.125, 0.125, 0.250, 0.375,
            ),
            (
                "hardcover", "black_and_white", "cream", 400,
                14.764, 10.417, 6.197, 9.236,
                1.189, 9.236, 1.064, 8.986,
                0.125, 0.125, 0.250, 0.375,
            ),
            (
                "hardcover", "black_and_white", "cream", 76,
                13.954, 10.417, 6.197, 9.236,
                0.379, 9.236, 0.254, 8.986,
                0.125, 0.125, 0.250, 0.375,
            ),
            (
                "paperback", "black_and_white", "cream", 76,
                12.440, 9.250, 6.000, 9.000,
                0.190, 9.000, 0.065, 8.750,
                0.125, 0.125, 0.250, 0.250,
            ),
            (
                "paperback", "black_and_white", "cream", 400,
                13.250, 9.250, 6.000, 9.000,
                1.000, 9.000, 0.875, 8.750,
                0.125, 0.125, 0.250, 0.250,
            ),
            (
                "paperback", "black_and_white", "white", 400,
                13.151, 9.250, 6.000, 9.000,
                0.901, 9.000, 0.776, 8.750,
                0.125, 0.125, 0.250, 0.250,
            ),
            (
                "paperback", "black_and_white", "white", 76,
                12.421, 9.250, 6.000, 9.000,
                0.171, 9.000, 0.046, 8.750,
                0.125, 0.125, 0.250, 0.250,
            ),
            (
                "paperback", "standard_color", "white", 76,
                12.421, 9.250, 6.000, 9.000,
                0.171, 9.000, 0.046, 8.750,
                0.125, 0.125, 0.250, 0.250,
            ),
            (
                "paperback", "standard_color", "white", 400,
                13.151, 9.250, 6.000, 9.000,
                0.901, 9.000, 0.776, 8.750,
                0.125, 0.125, 0.250, 0.250,
            ),
            (
                "hardcover", "premium_color", "white", 76,
                13.942, 10.417, 6.197, 9.236,
                0.367, 9.236, 0.242, 8.986,
                0.125, 0.125, 0.250, 0.375,
            ),
            (
                "hardcover", "premium_color", "white", 400,
                14.703, 10.417, 6.197, 9.236,
                1.128, 9.236, 1.003, 8.986,
                0.125, 0.125, 0.250, 0.375,
            ),
            (
                "paperback", "premium_color", "white", 400,
                13.189, 9.250, 6.000, 9.000,
                0.939, 9.000, 0.814, 8.750,
                0.125, 0.125, 0.250, 0.250,
            ),
            (
                "paperback", "premium_color", "white", 76,
                12.428, 9.250, 6.000, 9.000,
                0.178, 9.000, 0.053, 8.750,
                0.125, 0.125, 0.250, 0.250,
            ),
        ]

        for (
            binding, interior_type, paper, pages,
            full_w, full_h, front_w, front_h,
            spine_w, spine_h, spine_safe_w, spine_safe_h,
            margin_w, margin_h, barcode_w, barcode_h,
        ) in cases:
            with self.subTest(binding=binding, interior_type=interior_type, paper=paper, pages=pages):
                g = calculate_kdp_cover_geometry(
                    binding=binding,
                    interior_type=interior_type,
                    paper=paper,
                    page_count=pages,
                )
                self.assert_close(g.full_cover_width_in, full_w, "full cover width")
                self.assert_close(g.full_cover_height_in, full_h, "full cover height")
                self.assert_close(g.front_cover_width_in, front_w, "front cover width")
                self.assert_close(g.front_cover_height_in, front_h, "front cover height")
                self.assert_close(g.spine_width_in, spine_w, "spine width")
                self.assert_close(g.spine_height_in, spine_h, "spine height")
                self.assert_close(g.spine_safe_area_width_in, spine_safe_w, "spine safe width")
                self.assert_close(g.spine_safe_area_height_in, spine_safe_h, "spine safe height")
                self.assert_close(g.margin_width_in, margin_w, "margin width")
                self.assert_close(g.margin_height_in, margin_h, "margin height")
                self.assert_close(g.barcode_margin_width_in, barcode_w, "barcode margin width")
                self.assert_close(g.barcode_margin_height_in, barcode_h, "barcode margin height")

    def test_paperback_spine_is_paper_stack_only(self) -> None:
        g = calculate_kdp_cover_geometry(
            binding="paperback", interior_type="black_and_white", paper="cream", page_count=211
        )
        self.assert_close(g.spine_width_in, 0.5275, "paperback cream 211 spine")
        self.assert_close(g.full_cover_width_in, 12.7775, "paperback cream 211 full width")

    def test_hardcover_spine_includes_case_laminate_allowance(self) -> None:
        white = calculate_kdp_cover_geometry(
            binding="hardcover", interior_type="black_and_white", paper="white", page_count=211
        )
        cream = calculate_kdp_cover_geometry(
            binding="hardcover", interior_type="black_and_white", paper="cream", page_count=211
        )
        premium = calculate_kdp_cover_geometry(
            binding="hardcover", interior_type="premium_color", paper="white", page_count=211
        )
        self.assert_close(white.spine_width_in, 0.664172, "hardcover B&W white 211 spine")
        self.assert_close(white.full_cover_width_in, 14.239172, "hardcover B&W white 211 full width")
        self.assert_close(cream.spine_width_in, 0.7165, "hardcover B&W cream 211 spine")
        self.assert_close(cream.full_cover_width_in, 14.2915, "hardcover B&W cream 211 full width")
        self.assert_close(premium.spine_width_in, 0.684217, "hardcover premium white 211 spine")
        self.assert_close(premium.full_cover_width_in, 14.259217, "hardcover premium white 211 full width")

    def test_standard_color_uses_white_stock_geometry(self) -> None:
        standard = calculate_kdp_cover_geometry(
            binding="paperback", interior_type="standard_color", paper="white", page_count=400
        )
        bw_white = calculate_kdp_cover_geometry(
            binding="paperback", interior_type="black_and_white", paper="white", page_count=400
        )
        self.assert_close(standard.spine_width_in, bw_white.spine_width_in, "standard/B&W white spine")
        self.assert_close(standard.full_cover_width_in, bw_white.full_cover_width_in, "standard/B&W white full width")

    def test_aliases_are_accepted(self) -> None:
        premium = calculate_kdp_cover_geometry(
            binding="paperback", interior_type="Premium color", paper="White paper", page_count=76
        )
        standard = calculate_kdp_cover_geometry(
            binding="paperback", interior_type="Standard color", paper="White paper", page_count=76
        )
        self.assert_close(premium.full_cover_width_in, 12.428372, "premium alias full width")
        self.assert_close(standard.full_cover_width_in, 12.421152, "standard alias full width")

    def test_rejects_unsupported_settings(self) -> None:
        with self.assertRaises(ValueError):
            calculate_kdp_cover_geometry(binding="spiral", paper="cream", page_count=76)
        with self.assertRaises(ValueError):
            calculate_kdp_cover_geometry(binding="paperback", paper="blue", page_count=76)
        with self.assertRaises(ValueError):
            calculate_kdp_cover_geometry(binding="paperback", paper="cream", page_count=0)
        with self.assertRaises(ValueError):
            calculate_kdp_cover_geometry(
                binding="paperback", interior_type="premium_color", paper="cream", page_count=76
            )
        with self.assertRaises(ValueError):
            calculate_kdp_cover_geometry(
                binding="paperback", interior_type="standard_color", paper="cream", page_count=76
            )
        with self.assertRaises(ValueError):
            calculate_kdp_cover_geometry(
                binding="paperback", interior_type="economy_color", paper="white", page_count=76
            )


if __name__ == "__main__":
    unittest.main()
