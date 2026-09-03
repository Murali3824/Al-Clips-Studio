"""Focused regression tests for composition measurement (Change 1)."""

import unittest

from stages.stage_08_smooth_crop import _measure_composition


class CompositionMeasurementTests(unittest.TestCase):
    def setUp(self):
        self.crop = {"x": 500, "y": 0, "width": 608, "height": 1080}
        self.contained_detection = {"bbox": [650, 150, 300, 700]}

    def test_contained_subject_passes_measured_constraints(self):
        result = _measure_composition(
            self.crop, 1920, 1080, [self.contained_detection] * 5, 2.0
        )
        self.assertEqual(result["status"], "pass")
        self.assertTrue(result["sourceBoundsValid"])
        self.assertEqual(result["selectedSubjectMinimumContainment"], 1.0)
        self.assertEqual(result["faceValidation"], "unavailable_person_boxes_only")

    def test_materially_clipped_subject_fails(self):
        result = _measure_composition(
            self.crop, 1920, 1080, [{"bbox": [950, 150, 500, 700]}] * 5, 2.0
        )
        self.assertEqual(result["status"], "fail")
        self.assertIn("selected_subject_materially_clipped", result["reasons"])

    def test_missing_subject_for_most_of_clip_fails(self):
        result = _measure_composition(
            self.crop, 1920, 1080, [self.contained_detection] * 2, 10.0
        )
        self.assertEqual(result["status"], "fail")
        self.assertIn("selected_subject_missing_for_most_of_clip", result["reasons"])


if __name__ == "__main__":
    unittest.main()
