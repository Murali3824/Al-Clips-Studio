"""Focused regression tests for Change 3 scene-local subject selection."""

import unittest

from stages.stage_08_smooth_crop import _scene_subject_selections


def track(track_id, detections):
    return {"trackId": track_id, "detections": detections}


def detection(time, x=600, y=100, w=400, h=800, confidence=0.9):
    return {
        "time": time,
        "bbox": [x, y, w, h],
        "confidence": confidence,
    }


class SceneSubjectSelectionTests(unittest.TestCase):
    def test_selects_scene_local_track_not_previous_scene_track(self):
        tracks = [
            track(1, [detection(0.0), detection(0.5), detection(1.0)]),
            track(2, [detection(5.0), detection(5.5), detection(6.0)]),
        ]
        selections = _scene_subject_selections(
            tracks, [{"start": 5.0, "end": 6.0}], 0.0, 10.0, 1920, 1080
        )
        self.assertEqual(selections[0]["selection"], "best_visible_track")
        self.assertEqual(selections[0]["trackId"], 2)

    def test_reports_visible_subject_fallback_when_scene_has_no_track(self):
        selections = _scene_subject_selections(
            [], [{"start": 5.0, "end": 6.0}], 0.0, 10.0, 1920, 1080
        )
        self.assertEqual(selections[0]["selection"], "no_visible_subject")
        self.assertIsNone(selections[0]["trackId"])

    def test_reports_one_selection_for_each_intersecting_scene(self):
        tracks = [
            track(1, [detection(0.0), detection(0.5), detection(1.0)]),
            track(2, [detection(2.0), detection(2.5), detection(3.0)]),
        ]
        selections = _scene_subject_selections(
            tracks,
            [{"start": 0.0, "end": 1.0}, {"start": 2.0, "end": 3.0}],
            0.0,
            3.0,
            1920,
            1080,
        )
        self.assertEqual([item["trackId"] for item in selections], [1, 2])


if __name__ == "__main__":
    unittest.main()
