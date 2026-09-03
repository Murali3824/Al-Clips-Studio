import unittest

from stages.stage_07_subject_identity import _track_scene_faces


def face(frame, time, x, confidence=0.9, appearance=None):
    return {"frame": frame, "time": time, "faces": [{"bbox": [x, 100, 100, 120], "confidence": confidence, "appearance": appearance or [1.0, 0.0]}]}


class SubjectIdentityTests(unittest.TestCase):
    def test_keeps_identity_through_motion_and_brief_occlusion(self):
        scene = {"index": 3}
        identities, switches = _track_scene_faces(scene, [face(0, 0.0, 100), face(12, 0.5, 118), {"frame": 24, "time": 1.0, "faces": []}, face(36, 1.5, 138)])
        self.assertEqual(len(identities), 1)
        self.assertEqual(identities[0]["subjectId"], "scene_003_face_01")
        self.assertEqual(len(switches), 1)
        self.assertEqual(switches[0]["reason"], "scene_initial_subject")

    def test_requires_disappearance_before_switch(self):
        scene = {"index": 4}
        samples = [face(0, 0.0, 100), face(12, 0.5, 105), {"frame": 24, "time": 1.0, "faces": []}, face(84, 3.5, 700, appearance=[0.0, 1.0])]
        _, switches = _track_scene_faces(scene, samples)
        self.assertEqual(switches[-1]["reason"], "current_subject_disappeared")
        self.assertNotEqual(switches[-1]["fromSubjectId"], switches[-1]["toSubjectId"])

    def test_never_reuses_identity_across_scenes(self):
        first, _ = _track_scene_faces({"index": 1}, [face(0, 0.0, 100)])
        second, _ = _track_scene_faces({"index": 2}, [face(0, 0.0, 100)])
        self.assertNotEqual(first[0]["subjectId"], second[0]["subjectId"])


if __name__ == "__main__":
    unittest.main()
