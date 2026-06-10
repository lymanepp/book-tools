#!/usr/bin/env python3
"""Unit tests for KDP cover-calculator geometry.

These numbers come from the eight KDP calculator screenshots captured for
6×9, black-and-white, left-to-right books.
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
        # binding, paper, pages, full_w, full_h, front_w, front_h,
        # spine_w, spine_h, spine_safe_w, spine_safe_h,
        # margin_w, margin_h, barcode_w, barcode_h
        cases = [
            (
                "hardcover", "white", 76,
                13.935, 10.417, 6.197, 9.236,
                0.360, 9.236, 0.235, 8.986,
                0.125, 0.125, 0.250, 0.375,
            ),
            (
                "hardcover", "white", 400,
                14.665, 10.417, 6.197, 9.236,
                1.090, 9.236, 0.965, 8.986,
                0.125, 0.125, 0.250, 0.375,
            ),
            (
                "hardcover", "cream", 76,
                13.954, 10.417, 6.197, 9.236,
                0.379, 9.236, 0.254, 8.986,
                0.125, 0.125, 0.250, 0.375,
            ),
            (
                "hardcover", "cream", 400,
                14.764, 10.417, 6.197, 9.236,
                1.189, 9.236, 1.064, 8.986,
                0.125, 0.125, 0.250, 0.375,
            ),
            (
                "paperback", "white", 76,
                12.421, 9.250, 6.000, 9.000,
                0.171, 9.000, 0.046, 8.750,
                0.125, 0.125, 0.250, 0.250,
            ),
            (
                "paperback", "white", 400,
                13.151, 9.250, 6.000, 9.000,
                0.901, 9.000, 0.776, 8.750,
                0.125, 0.125, 0.250, 0.250,
            ),
            (
                "paperback", "cream", 76,
                12.440, 9.250, 6.000, 9.000,
                0.190, 9.000, 0.065, 8.750,
                0.125, 0.125, 0.250, 0.250,
            ),
            (
                "paperback", "cream", 400,
                13.250, 9.250, 6.000, 9.000,
                1.000, 9.000, 0.875, 8.750,
                0.125, 0.125, 0.250, 0.250,
            ),
        ]

        for (
            binding, paper, pages,
            full_w, full_h, front_w, front_h,
            spine_w, spine_h, spine_safe_w, spine_safe_h,
            margin_w, margin_h, barcode_w, barcode_h,
        ) in cases:
            with self.subTest(binding=binding, paper=paper, pages=pages):
                g = calculate_kdp_cover_geometry(binding=binding, paper=paper, page_count=pages)
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
        g = calculate_kdp_cover_geometry(binding="paperback", paper="cream", page_count=211)
        self.assert_close(g.spine_width_in, 0.5275, "paperback cream 211 spine")
        self.assert_close(g.full_cover_width_in, 12.7775, "paperback cream 211 full width")

    def test_hardcover_spine_includes_case_laminate_allowance(self) -> None:
        white = calculate_kdp_cover_geometry(binding="hardcover", paper="white", page_count=211)
        cream = calculate_kdp_cover_geometry(binding="hardcover", paper="cream", page_count=211)
        self.assert_close(white.spine_width_in, 0.664172, "hardcover white 211 spine")
        self.assert_close(white.full_cover_width_in, 14.239172, "hardcover white 211 full width")
        self.assert_close(cream.spine_width_in, 0.7165, "hardcover cream 211 spine")
        self.assert_close(cream.full_cover_width_in, 14.2915, "hardcover cream 211 full width")

    def test_rejects_unsupported_settings(self) -> None:
        with self.assertRaises(ValueError):
            calculate_kdp_cover_geometry(binding="spiral", paper="cream", page_count=76)
        with self.assertRaises(ValueError):
            calculate_kdp_cover_geometry(binding="paperback", paper="blue", page_count=76)
        with self.assertRaises(ValueError):
            calculate_kdp_cover_geometry(binding="paperback", paper="cream", page_count=0)


if __name__ == "__main__":
    unittest.main()
