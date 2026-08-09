#!/usr/bin/env python3
"""Regression tests for build-environment font detection."""
from __future__ import annotations

import importlib.util
from pathlib import Path
from types import SimpleNamespace
from unittest import TestCase, main
from unittest.mock import patch


def load_module():
    path = Path(__file__).with_name("check-build-env.py")
    spec = importlib.util.spec_from_file_location("check_build_env", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class FontMatchTests(TestCase):
    def setUp(self) -> None:
        self.module = load_module()

    def inventory(self, stdout: str):
        result = SimpleNamespace(returncode=0, stdout=stdout)
        with patch.object(self.module, "command_exists", return_value=True), \
             patch.object(self.module.subprocess, "run", return_value=result):
            return self.module.installed_font_faces()

    def test_compact_family_name_is_accepted(self) -> None:
        faces = self.inventory('/fonts/qplr.pfb\tTeXGyrePagella\tRegular\n')
        self.assertIsNotNone(
            self.module.find_font_face(faces, "TeX Gyre Pagella", "Regular")
        )

    def test_regular_face_does_not_satisfy_bold(self) -> None:
        faces = self.inventory(
            '/fonts/EBGaramond08-Regular.otf\tEB Garamond,EB Garamond 08\t08 Regular,Regular\n'
        )
        self.assertIsNone(self.module.find_font_face(faces, "EB Garamond", "Bold"))

    def test_actual_bold_face_is_selected(self) -> None:
        faces = self.inventory(
            '/fonts/EBGaramond08-Regular.otf\tEB Garamond,EB Garamond 08\t08 Regular,Regular\n'
            '/fonts/EBGaramond12-Bold.otf\tEB Garamond,EB Garamond 12\t12 Bold,Bold\n'
        )
        match = self.module.find_font_face(faces, "EB Garamond", "Bold")
        self.assertIsNotNone(match)
        self.assertIn("EBGaramond12-Bold.otf", match)


if __name__ == "__main__":
    main()
