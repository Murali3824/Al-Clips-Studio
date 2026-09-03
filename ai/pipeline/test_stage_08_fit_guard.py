"""Focused regression tests for Change 2 composition-aware fit guard."""

import unittest

from stages.stage_08_smooth_crop import _resolve_fit_guard


class FitGuardTests(unittest.TestCase):
    def test_feasible_crop_keeps_full_crop_layout(self):
        use_blur_pad, reasons = _resolve_fit_guard({"reasons": []})
        self.assertFalse(use_blur_pad)
        self.assertEqual(reasons, [])

    def test_partial_clip_remains_reviewable_without_forced_fallback(self):
        use_blur_pad, reasons = _resolve_fit_guard(
            {"reasons": ["selected_subject_partially_clipped"]}
        )
        self.assertFalse(use_blur_pad)
        self.assertEqual(reasons, [])

    def test_material_clip_uses_existing_blur_pad_fallback(self):
        use_blur_pad, reasons = _resolve_fit_guard(
            {"reasons": ["selected_subject_materially_clipped"]}
        )
        self.assertTrue(use_blur_pad)
        self.assertEqual(reasons, ["selected_subject_materially_clipped"])

    def test_missing_subject_uses_existing_blur_pad_fallback(self):
        use_blur_pad, reasons = _resolve_fit_guard(
            {"reasons": ["selected_subject_missing_for_most_of_clip"]}
        )
        self.assertTrue(use_blur_pad)
        self.assertEqual(reasons, ["selected_subject_missing_for_most_of_clip"])


if __name__ == "__main__":
    unittest.main()
