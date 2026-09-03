import unittest

from stages.stage_08a_camera_planning import EASING_SINE, _camera_target, _damped_micro_pan, _engagement_zoom_target, _limit_target, _motion_metrics, _plan_segment, _portrait_fill_zoom, _scene_segments, _stable_face_anchor


class CameraPlanningTests(unittest.TestCase):
    def test_camera_target_stays_inside_approved_composition(self):
        crop = {"x": 500, "y": 0, "width": 608, "height": 1080}
        target = _camera_target(crop, {"bbox": [1040, 170, 150, 210]})
        self.assertGreaterEqual(target["x"], crop["x"])
        self.assertLessEqual(target["x"] + target["width"], crop["x"] + crop["width"])
        self.assertGreaterEqual(target["y"], crop["y"])
        self.assertLessEqual(target["y"] + target["height"], crop["y"] + crop["height"])

    def test_motion_limit_caps_velocity(self):
        start = {"x": 500.0, "y": 0.0, "zoom": 1.0, "width": 608.0, "height": 1080.0}
        limited = _limit_target(start, {**start, "x": 1000.0, "y": 500.0, "zoom": 1.2}, 1.0)
        self.assertLessEqual(limited["x"] - start["x"], 45.0)
        self.assertLessEqual(limited["y"] - start["y"], 35.0)
        self.assertLessEqual(limited["zoom"] - start["zoom"], 0.015)

    def test_static_target_is_frozen(self):
        start = {"x": 500.0, "y": 0.0, "zoom": 1.0}
        velocity, acceleration, jerk, moving = _motion_metrics(start, start, 3.0)
        self.assertFalse(moving)
        self.assertEqual(velocity["x"], 0.0)
        self.assertEqual(acceleration["zoom"], 0.0)
        self.assertEqual(jerk["x"], 0.0)

    def test_scene_cut_splits_camera_segments(self):
        plan = {"start": 0.0, "end": 10.0, "layoutSegments": [{"start": 0.0, "end": 10.0, "layout": "full-crop"}]}
        segments = _scene_segments(plan, [{"index": 1, "start": 0.0, "end": 4.0}, {"index": 2, "start": 4.0, "end": 10.0}])
        self.assertEqual(len(segments), 2)
        self.assertEqual([item["sceneIndex"] for item in segments], [1, 2])

    def test_static_or_blur_segment_uses_exact_composition_rectangle(self):
        plan = {"x": 500, "y": 0, "width": 608, "height": 1080, "identitySubjectSelections": []}
        segment = _plan_segment(plan, {"start": 0.0, "end": 2.0, "layout": "blur-pad", "sceneIndex": 1}, {"scenes": []})
        position = segment["keyframes"][0]["position"]
        self.assertEqual((position["x"], position["y"], position["zoom"]), (500.0, 0.0, 1.0))

    def test_stable_full_crop_can_receive_a_capped_engagement_zoom(self):
        crop = {"x": 500, "y": 0, "width": 608, "height": 1080}
        target = _engagement_zoom_target(crop, {"bbox": [650, 160, 180, 320]}, 12.0)
        self.assertIsNotNone(target)
        self.assertGreater(target["zoom"], 1.0)
        self.assertLessEqual(target["zoom"], 1.012)

    def test_short_or_unframed_segment_does_not_receive_engagement_zoom(self):
        crop = {"x": 500, "y": 0, "width": 608, "height": 1080}
        self.assertIsNone(_engagement_zoom_target(crop, {"bbox": [650, 160, 180, 320]}, 3.0))
        self.assertIsNone(_engagement_zoom_target(crop, None, 12.0))

    def test_micro_pan_dead_zone_suppresses_detection_noise_without_touching_zoom(self):
        start = {"x": 500.0, "y": 0.0, "zoom": 1.0}
        damped = _damped_micro_pan(start, {"x": 503.0, "y": 3.0, "zoom": 1.012})
        self.assertEqual((damped["x"], damped["y"]), (500.0, 0.0))
        self.assertEqual(damped["zoom"], 1.012)

    def test_micro_pan_damps_but_retains_meaningful_subject_motion(self):
        start = {"x": 500.0, "y": 0.0, "zoom": 1.0}
        damped = _damped_micro_pan(start, {"x": 515.0, "y": 10.0, "zoom": 1.0})
        self.assertGreater(damped["x"], 500.0)
        self.assertLess(damped["x"], 515.0)
        self.assertGreater(damped["y"], 0.0)
        self.assertLess(damped["y"], 10.0)

    def test_sine_profile_has_gentler_peak_acceleration_for_the_same_path(self):
        start = {"x": 500.0, "y": 0.0, "zoom": 1.0}
        end = {"x": 520.0, "y": 0.0, "zoom": 1.0}
        _, cubic_acceleration, _, _ = _motion_metrics(start, end, 10.0)
        _, sine_acceleration, _, _ = _motion_metrics(start, end, 10.0, EASING_SINE)
        self.assertLess(sine_acceleration["x"], cubic_acceleration["x"])

    def test_face_anchor_rejects_a_single_endpoint_box_outlier(self):
        faces = [
            {"time": 0.0, "bbox": [900, 160, 200, 300], "confidence": 0.9},
            {"time": 0.5, "bbox": [902, 160, 200, 300], "confidence": 0.9},
            {"time": 1.0, "bbox": [899, 160, 200, 300], "confidence": 0.9},
            {"time": 1.5, "bbox": [650, 160, 200, 300], "confidence": 0.1},
        ]
        anchor = _stable_face_anchor(faces, toward_start=True)
        self.assertGreater(anchor["bbox"][0], 890)

    def test_face_anchor_uses_last_local_window_for_end_composition(self):
        faces = [
            {"time": 0.0, "bbox": [600, 160, 200, 300], "confidence": 0.9},
            {"time": 5.0, "bbox": [900, 160, 200, 300], "confidence": 0.9},
            {"time": 5.5, "bbox": [904, 160, 200, 300], "confidence": 0.9},
        ]
        anchor = _stable_face_anchor(faces, toward_start=False)
        self.assertGreater(anchor["bbox"][0], 890)

    def test_portrait_fill_increases_safe_single_speaker_prominence(self):
        plan = {"x": 500, "y": 0, "width": 608, "height": 1080}
        faces = [{"subjectId": "speaker", "bbox": [650, 170, 240, 340], "confidence": 0.9}] * 4
        zoom, reason = _portrait_fill_zoom(plan, {"layout": "full-crop"}, faces, 12.0)
        self.assertGreater(zoom, 1.0)
        self.assertEqual(reason, "single_speaker_portrait_fill_safe")

    def test_portrait_fill_refuses_an_unsafe_face_near_the_crop_edge(self):
        plan = {"x": 500, "y": 0, "width": 608, "height": 1080}
        faces = [{"subjectId": "speaker", "bbox": [505, 40, 240, 340], "confidence": 0.9}] * 4
        zoom, reason = _portrait_fill_zoom(plan, {"layout": "full-crop"}, faces, 12.0)
        self.assertEqual(zoom, 1.0)
        self.assertEqual(reason, "portrait_fill_rejected_by_face_safety")



if __name__ == "__main__":
    unittest.main()
