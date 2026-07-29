import contextlib
import io
import json
import os
import warnings

from media_utils import find_input_video

os.environ.setdefault("YOLO_VERBOSE", "False")

warnings.filterwarnings(
    "ignore",
    message=r"urllib3 .* doesn't match a supported version!",
)


YOLO_PERSON_CLASS = 0


def _load_model(model_name: str):
    from ultralytics import YOLO

    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        return YOLO(model_name)


def _box_to_detection(box, frame_index: int, fps: float) -> dict | None:
    if box.id is None:
        return None

    x1, y1, x2, y2 = [float(value) for value in box.xyxy[0].tolist()]
    width = max(1.0, x2 - x1)
    height = max(1.0, y2 - y1)
    center_x = x1 + width / 2
    center_y = y1 + height / 2
    return {
        "frame": frame_index,
        "time": round(frame_index / fps, 3),
        "bbox": [round(x1, 3), round(y1, 3), round(width, 3), round(height, 3)],
        "center": [round(center_x, 3), round(center_y, 3)],
        "confidence": round(float(box.conf[0]), 4),
        "classId": int(box.cls[0]),
        "label": "person",
        "trackId": int(box.id[0]),
        "tracker": "bytetrack",
    }


def _finalize_track(track_id: int, detections: list[dict]) -> dict:
    confidences = [
        float(item["confidence"])
        for item in detections
        if item.get("confidence") is not None
    ]
    return {
        "trackId": track_id,
        "start": round(float(detections[0]["time"]), 3),
        "end": round(float(detections[-1]["time"]), 3),
        "frames": [int(item["frame"]) for item in detections],
        "detections": detections,
        "detectionCount": len(detections),
        "averageConfidence": round(sum(confidences) / len(confidences), 4)
        if confidences
        else None,
    }


def run(context):
    input_video = find_input_video(context["upload_dir"])
    metadata = json.loads(
        (context["temp_dir"] / "video_metadata.json").read_text(encoding="utf-8")
    )
    fps = float(metadata.get("fps") or 30)
    frame_interval = max(1, int(round(fps / 2)))
    model_name = context["settings"].get("yoloModel", "yolov8n.pt")

    from pathlib import Path
    local_model_path = Path(context["root"]) / "models" / model_name
    if local_model_path.exists():
        model_name_or_path = str(local_model_path)
    else:
        model_name_or_path = model_name

    # Option 1: Scene-Aware ByteTrack
    scene_cuts_path = context["temp_dir"] / "scene_cuts.json"
    scenes = []
    if scene_cuts_path.exists():
        scene_cuts_data = json.loads(scene_cuts_path.read_text(encoding="utf-8"))
        scenes = scene_cuts_data.get("scenes", [])

    def _get_scene_index(frame_idx: int) -> int:
        for s in scenes:
            if s.get("startFrame", 0) <= frame_idx <= s.get("endFrame", 999999999):
                return int(s.get("index", 0))
        return 0

    model = _load_model(model_name_or_path)
    tracks_by_id: dict[int, list[dict]] = {}
    sampled_frames = 0
    current_scene_idx = -1

    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        results = model.track(
            source=str(input_video),
            stream=True,
            persist=True,
            tracker="bytetrack.yaml",
            classes=[YOLO_PERSON_CLASS],
            conf=0.25,
            imgsz=640,
            vid_stride=frame_interval,
            verbose=False,
        )
        for result_index, result in enumerate(results):
            sampled_frames += 1
            frame_index = result_index * frame_interval

            # Scene-cut boundary detection & tracker reset
            scene_idx = _get_scene_index(frame_index)
            if scene_idx != current_scene_idx:
                current_scene_idx = scene_idx
                with contextlib.suppress(Exception):
                    if hasattr(model, "predictor") and model.predictor and hasattr(model.predictor, "trackers"):
                        if model.predictor.trackers and len(model.predictor.trackers) > 0:
                            model.predictor.trackers[0].reset()

            if result.boxes is None or len(result.boxes) == 0:
                continue
            for box in result.boxes:
                detection = _box_to_detection(box, frame_index, fps)
                if detection is None:
                    continue
                # Scope trackId to scene boundary to prevent cross-cut track ID merging
                scoped_track_id = (scene_idx + 1) * 10000 + int(detection["trackId"])
                detection["trackId"] = scoped_track_id
                tracks_by_id.setdefault(scoped_track_id, []).append(detection)

    tracks = sorted(
        (
            _finalize_track(track_id, detections)
            for track_id, detections in tracks_by_id.items()
            if detections
        ),
        key=lambda item: item["detectionCount"],
        reverse=True,
    )

    (context["temp_dir"] / "face_tracks.json").write_text(
        json.dumps({
            "method": "ultralytics-bytetrack",
            "model": model_name,
            "tracker": "bytetrack.yaml",
            "sampledFrames": sampled_frames,
            "frameInterval": frame_interval,
            "tracks": tracks,
        }, indent=2),
        encoding="utf-8",
    )
