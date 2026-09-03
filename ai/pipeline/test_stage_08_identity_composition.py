import unittest

from stages.stage_08_smooth_crop import _active_identity_faces, _identity_faces_for_track, _identity_safe_layout_segments, _measure_composition, _resolve_fit_guard


class IdentityCompositionTests(unittest.TestCase):
    def test_uses_only_the_identity_active_for_each_time_range(self):
        identities = {
            "scenes": [{
                "sceneIndex": 8, "start": 10.0, "end": 20.0,
                "identities": [
                    {"subjectId": "a", "detections": [{"frame": 1, "time": 11.0, "bbox": [100, 100, 120, 140], "confidence": 0.9}, {"frame": 2, "time": 16.0, "bbox": [100, 100, 120, 140], "confidence": 0.9}]},
                    {"subjectId": "b", "detections": [{"frame": 3, "time": 11.0, "bbox": [700, 100, 120, 140], "confidence": 0.9}, {"frame": 4, "time": 16.0, "bbox": [700, 100, 120, 140], "confidence": 0.9}]},
                ],
                "subjectSwitches": [{"time": 10.0, "toSubjectId": "a", "reason": "scene_initial_subject"}, {"time": 15.0, "toSubjectId": "b", "reason": "current_subject_disappeared"}],
            }]
        }
        anchors, selections = _active_identity_faces(identities, 10.0, 20.0)
        self.assertEqual([anchor["subjectId"] for anchor in anchors], ["a", "b"])
        self.assertEqual([selection["subjectId"] for selection in selections], ["a", "b"])

    def test_safe_identity_face_overrides_person_body_clipping(self):
        crop = {"x": 500, "y": 0, "width": 608, "height": 1080}
        persons = [{"bbox": [400, 0, 1000, 1000]}, {"bbox": [400, 0, 1000, 1000]}]
        faces = [{"bbox": [650, 180, 180, 220], "confidence": 0.9}, {"bbox": [650, 180, 180, 220], "confidence": 0.9}, {"bbox": [650, 180, 180, 220], "confidence": 0.9}]
        composition = _measure_composition(crop, 1920, 1080, persons, 1.0, faces)
        use_blur, reasons = _resolve_fit_guard(composition)
        self.assertEqual(composition["faceValidation"], "measured_identity_faces")
        self.assertFalse(use_blur, reasons)

    def test_face_coverage_uses_available_selected_subject_samples(self):
        crop = {"x": 500, "y": 0, "width": 608, "height": 1080}
        persons = [{"bbox": [500, 0, 800, 1000]}] * 60
        faces = [{"bbox": [650, 180, 180, 220], "confidence": 0.9}] * 56
        composition = _measure_composition(crop, 1920, 1080, persons, 60.0, faces, len(persons))
        self.assertGreaterEqual(composition["faceSampleCoverage"], 0.9)

    def test_rejects_an_active_face_not_inside_the_selected_person_track(self):
        faces = [
            {"time": 1.0, "bbox": [110, 100, 80, 100], "confidence": 0.9, "subjectId": "approved"},
            {"time": 1.0, "bbox": [700, 100, 80, 100], "confidence": 0.9, "subjectId": "other"},
        ]
        track = [{"time": 1.0, "bbox": [80, 50, 200, 300]}]
        associated = _identity_faces_for_track(faces, track)
        self.assertEqual([face["subjectId"] for face in associated], ["approved"])

    def test_uses_blur_pad_when_a_scene_lacks_the_approved_identity(self):
        segments = _identity_safe_layout_segments(
            [{"start": 0.0, "end": 20.0, "layout": "full-crop"}],
            [{"start": 0.0, "end": 10.0}, {"start": 10.0, "end": 20.0}],
            0.0, 20.0,
            [{"time": 12.0, "bbox": [0, 0, 1, 1]}],
        )
        self.assertEqual([segment["layout"] for segment in segments], ["blur-pad", "full-crop"])


if __name__ == "__main__":
    unittest.main()
