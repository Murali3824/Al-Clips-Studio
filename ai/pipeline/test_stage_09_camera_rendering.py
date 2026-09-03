import unittest

from render_engine import _position_at, camera_crop_filter, camera_render_trace


def camera_plan():
    return {
        "clipId": "clip_03", "start": 10.0, "end": 20.0,
        "sourceComposition": {"x": 500, "y": 0, "width": 608, "height": 1080},
        "segments": [{
            "start": 10.0, "end": 20.0, "sceneIndex": 3, "easing": "cubic_ease_in_out",
            "keyframes": [
                {"position": {"x": 500, "y": 0, "width": 608, "height": 1080, "zoom": 1.0}},
                {"position": {"x": 520, "y": 12, "width": 596, "height": 1058, "zoom": 1.02}},
            ],
        }],
    }


class CameraRenderTests(unittest.TestCase):
    def test_easing_reaches_planned_keyframes_exactly(self):
        plan = camera_plan()
        self.assertEqual(_position_at(plan, 10.0)["x"], 500.0)
        self.assertEqual(_position_at(plan, 20.0)["zoom"], 1.02)
        self.assertAlmostEqual(_position_at(plan, 15.0)["x"], 510.0)

    def test_filter_uses_per_frame_cubic_crop_expressions(self):
        filter_text = camera_crop_filter(camera_plan())
        self.assertIn("eval=frame", filter_text)
        self.assertIn("scale=w='iw*", filter_text)
        self.assertIn("gte(t\\,0.000000)*lte(t\\,10.000000)", filter_text)
        self.assertIn("3*((t-0.000000)/10.000000)", filter_text)

    def test_renderer_executes_planner_selected_sine_easing(self):
        plan = camera_plan()
        plan["segments"][0]["easing"] = "sine_ease_in_out"
        # At 25%, sine easing begins more deliberately than legacy cubic, while
        # retaining the same exact endpoints and segment timing.
        self.assertLess(_position_at(plan, 12.5)["x"], 503.125)
        self.assertEqual(_position_at(plan, 10.0)["x"], 500.0)
        self.assertEqual(_position_at(plan, 20.0)["x"], 520.0)
        self.assertIn("cos(PI*", camera_crop_filter(plan))

    def test_trace_contains_keyframes_and_midpoint(self):
        trace = camera_render_trace(camera_plan())
        self.assertEqual([item["time"] for item in trace], [10.0, 15.0, 20.0])
        self.assertEqual(trace[0]["position"]["x"], 500.0)
        self.assertEqual(trace[-1]["position"]["x"], 520.0)

    def test_shared_boundary_uses_the_next_scene_keyframe(self):
        plan = camera_plan()
        plan["segments"].insert(0, {
            "start": 0.0, "end": 10.0, "sceneIndex": 2, "easing": "cubic_ease_in_out",
            "keyframes": [{"position": {"x": 400, "y": 0, "width": 608, "height": 1080, "zoom": 1.0}}, {"position": {"x": 400, "y": 0, "width": 608, "height": 1080, "zoom": 1.0}}],
        })
        self.assertEqual(_position_at(plan, 10.0)["x"], 500.0)


if __name__ == "__main__":
    unittest.main()
