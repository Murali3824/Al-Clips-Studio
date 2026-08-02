"""Scene-local face identity and continuity diagnostics.

This stage intentionally produces data only.  Crop planning and rendering do not
read this artifact yet, so it cannot change a rendered video.
"""

import json
import math
from pathlib import Path

import cv2

from media_utils import find_input_video


MODEL_NAME = "face_detection_yunet_2023mar.onnx"
MAX_TRACK_GAP_SECONDS = 2.0
MIN_MATCH_SCORE = 0.48


def _iou(a: list[float], b: list[float]) -> float:
    ax, ay, aw, ah = (float(value) for value in a[:4])
    bx, by, bw, bh = (float(value) for value in b[:4])
    left, top = max(ax, bx), max(ay, by)
    right, bottom = min(ax + aw, bx + bw), min(ay + ah, by + bh)
    overlap = max(0.0, right - left) * max(0.0, bottom - top)
    union = aw * ah + bw * bh - overlap
    return overlap / union if union > 0 else 0.0


def _center_distance(a: list[float], b: list[float]) -> float:
    ax, ay, aw, ah = (float(value) for value in a[:4])
    bx, by, bw, bh = (float(value) for value in b[:4])
    distance = math.hypot((ax + aw / 2.0) - (bx + bw / 2.0), (ay + ah / 2.0) - (by + bh / 2.0))
    return distance / max(1.0, (aw + ah + bw + bh) / 4.0)


def _appearance_similarity(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.5
    numerator = sum(x * y for x, y in zip(a, b))
    magnitude = math.sqrt(sum(x * x for x in a) * sum(y * y for y in b))
    return max(0.0, min(1.0, numerator / magnitude)) if magnitude else 0.5


def _match_score(track: dict, face: dict) -> float:
    return (
        0.55 * _iou(track["lastBbox"], face["bbox"])
        + 0.25 * max(0.0, 1.0 - _center_distance(track["lastBbox"], face["bbox"]))
        + 0.20 * _appearance_similarity(track.get("appearance", []), face.get("appearance", []))
    )


def _track_scene_faces(scene: dict, samples: list[dict]) -> tuple[list[dict], list[dict]]:
    """Create scene-scoped IDs and a continuity-constrained active-subject timeline."""
    scene_index = int(scene.get("index", 0))
    tracks: list[dict] = []
    active_subject_id = None
    active_missing_since = None
    switches: list[dict] = []

    for sample in sorted(samples, key=lambda item: (float(item["time"]), int(item["frame"]))):
        timestamp = float(sample["time"])
        faces = sorted(sample.get("faces", []), key=lambda face: float(face["confidence"]) * float(face["bbox"][2]) * float(face["bbox"][3]), reverse=True)
        available = [track for track in tracks if timestamp - float(track["lastTime"]) <= MAX_TRACK_GAP_SECONDS]
        matched_ids = set()
        for face in faces:
            candidates = [(track, _match_score(track, face)) for track in available if track["subjectId"] not in matched_ids]
            track, score = max(candidates, key=lambda item: item[1], default=(None, 0.0))
            if track is None or score < MIN_MATCH_SCORE:
                track = {
                    "subjectId": f"scene_{scene_index:03d}_face_{len(tracks) + 1:02d}",
                    "firstFrame": int(sample["frame"]),
                    "firstTime": timestamp,
                    "detections": [],
                }
                tracks.append(track)
            track["lastBbox"] = face["bbox"]
            track["lastTime"] = timestamp
            track["appearance"] = face.get("appearance", track.get("appearance", []))
            track["detections"].append({
                "frame": int(sample["frame"]),
                "time": round(timestamp, 3),
                "bbox": face["bbox"],
                "confidence": round(float(face["confidence"]), 4),
            })
            matched_ids.add(track["subjectId"])

        observed = [track for track in tracks if track["subjectId"] in matched_ids]
        if active_subject_id is None and observed:
            selected = max(observed, key=lambda track: float(track["detections"][-1]["confidence"]) * float(track["lastBbox"][2]) * float(track["lastBbox"][3]))
            active_subject_id = selected["subjectId"]
            switches.append({"frame": int(sample["frame"]), "time": round(timestamp, 3), "fromSubjectId": None, "toSubjectId": active_subject_id, "reason": "scene_initial_subject"})
        elif active_subject_id in matched_ids:
            active_missing_since = None
        elif active_subject_id is not None:
            active_missing_since = active_missing_since if active_missing_since is not None else timestamp
            if timestamp - active_missing_since > MAX_TRACK_GAP_SECONDS and observed:
                selected = max(observed, key=lambda track: float(track["detections"][-1]["confidence"]) * float(track["lastBbox"][2]) * float(track["lastBbox"][3]))
                if selected["subjectId"] != active_subject_id:
                    switches.append({"frame": int(sample["frame"]), "time": round(timestamp, 3), "fromSubjectId": active_subject_id, "toSubjectId": selected["subjectId"], "reason": "current_subject_disappeared"})
                    active_subject_id = selected["subjectId"]
                active_missing_since = None

    identities = []
    for track in tracks:
        detections = track["detections"]
        identities.append({
            "subjectId": track["subjectId"],
            "frameRange": [detections[0]["frame"], detections[-1]["frame"]],
            "timeRange": [detections[0]["time"], detections[-1]["time"]],
            "detectionCount": len(detections),
            "averageConfidence": round(sum(item["confidence"] for item in detections) / len(detections), 4),
            "detections": detections,
        })
    return identities, switches


def _face_appearance(frame, bbox: list[float]) -> list[float]:
    x, y, width, height = (float(value) for value in bbox[:4])
    x1, y1 = max(0, int(x)), max(0, int(y))
    x2, y2 = min(frame.shape[1], int(x + width)), min(frame.shape[0], int(y + height))
    patch = frame[y1:y2, x1:x2]
    if patch.size == 0:
        return []
    histogram = cv2.calcHist([cv2.cvtColor(patch, cv2.COLOR_BGR2GRAY)], [0], None, [16], [0, 256]).flatten()
    total = float(histogram.sum())
    return [round(float(value / total), 5) for value in histogram] if total else []


def _detect_faces(detector, frame) -> list[dict]:
    source_height, source_width = frame.shape[:2]
    scale = min(1.0, 960.0 / max(source_width, source_height))
    resized = cv2.resize(frame, (round(source_width * scale), round(source_height * scale))) if scale < 1.0 else frame
    detector.setInputSize((resized.shape[1], resized.shape[0]))
    _, detected = detector.detect(resized)
    if detected is None:
        return []
    faces = []
    for item in detected:
        x, y, width, height = (float(value) / scale for value in item[:4])
        bbox = [round(x, 3), round(y, 3), round(width, 3), round(height, 3)]
        faces.append({"bbox": bbox, "confidence": round(float(item[14]), 4), "appearance": _face_appearance(frame, bbox)})
    return faces


def _scene_samples(samples: list[dict], scene: dict) -> list[dict]:
    start, end = float(scene["start"]), float(scene["end"])
    return [sample for sample in samples if start <= float(sample["time"]) <= end]


def run(context):
    model_path = Path(context["root"]) / "models" / MODEL_NAME
    if not model_path.exists():
        raise FileNotFoundError(f"Face identity model not found: {model_path}")
    scenes = json.loads((context["temp_dir"] / "scene_cuts.json").read_text(encoding="utf-8")).get("scenes", [])
    metadata = json.loads((context["temp_dir"] / "video_metadata.json").read_text(encoding="utf-8"))
    fps = float(metadata.get("fps") or 30.0)
    interval = max(1, int(round(fps / 2.0)))
    detector = cv2.FaceDetectorYN.create(str(model_path), "", (320, 320), 0.60, 0.3, 5000)
    capture = cv2.VideoCapture(str(find_input_video(context["upload_dir"])))
    if not capture.isOpened():
        raise RuntimeError("Could not open input video for subject identity analysis")
    samples, frame_index = [], 0
    try:
        while True:
            ok, frame = capture.read()
            if not ok:
                break
            if frame_index % interval == 0:
                samples.append({"frame": frame_index, "time": round(frame_index / fps, 3), "faces": _detect_faces(detector, frame)})
            frame_index += 1
    finally:
        capture.release()
    scene_diagnostics = []
    for scene in scenes:
        identities, switches = _track_scene_faces(scene, _scene_samples(samples, scene))
        scene_diagnostics.append({"sceneIndex": int(scene["index"]), "start": scene["start"], "end": scene["end"], "identities": identities, "subjectSwitches": switches})
    (context["temp_dir"] / "subject_identities.json").write_text(json.dumps({"method": "yunet-scene-local-continuity", "model": MODEL_NAME, "sampledFrames": len(samples), "maxTrackGapSeconds": MAX_TRACK_GAP_SECONDS, "scenes": scene_diagnostics}, indent=2), encoding="utf-8")
