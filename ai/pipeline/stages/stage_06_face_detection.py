import contextlib
import io
import json
import os
import warnings

import cv2

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


def _all_persons(result, frame_width: int, frame_height: int) -> list[dict]:
    if result.boxes is None or len(result.boxes) == 0:
        return []

    persons = []
    frame_center_x = frame_width / 2
    for box in result.boxes:
        class_id = int(box.cls[0])
        if class_id != YOLO_PERSON_CLASS:
            continue

        x1, y1, x2, y2 = [float(value) for value in box.xyxy[0].tolist()]
        width = max(1.0, x2 - x1)
        height = max(1.0, y2 - y1)
        confidence = float(box.conf[0])

        # Filter out low-confidence detections (posters, reflections, objects)
        if confidence < 0.40:
            continue

        # Filter out very small background detections (height < 10% or width < 6% of frame)
        rel_w = width / frame_width
        rel_h = height / frame_height
        if rel_w < 0.06 or rel_h < 0.10:
            continue

        area = width * height
        center_x = x1 + width / 2
        center_y = y1 + height / 2
        center_bonus = 1 - min(abs(center_x - frame_center_x) / max(frame_center_x, 1), 1)
        score = area * (0.75 + confidence) * (0.8 + center_bonus * 0.2)

        persons.append({
            "bbox": [round(x1, 3), round(y1, 3), round(width, 3), round(height, 3)],
            "center": [round(center_x, 3), round(center_y, 3)],
            "confidence": round(confidence, 4),
            "classId": class_id,
            "label": "person",
            "score": score,
        })

    return sorted(persons, key=lambda p: p["score"], reverse=True)


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

    model = _load_model(model_name_or_path)
    capture = cv2.VideoCapture(str(input_video))
    if not capture.isOpened():
        raise RuntimeError(f"Could not open video for YOLO detection: {input_video}")

    detections = []
    frame_index = 0
    sampled_frames = 0

    try:
        while True:
            ok, frame = capture.read()
            if not ok:
                break

            if frame_index % frame_interval == 0:
                sampled_frames += 1
                frame_height, frame_width = frame.shape[:2]
                with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                    results = model.predict(
                        frame,
                        imgsz=640,
                        conf=0.25,
                        classes=[YOLO_PERSON_CLASS],
                        verbose=False,
                    )
                persons = _all_persons(results[0], frame_width, frame_height)
                person_count = len(persons)
                primary_count = sum(
                    1 for p in persons 
                    if (p["bbox"][2] / frame_width) * (p["bbox"][3] / frame_height) >= 0.030
                )
                best = persons[0] if persons else None
                if best is not None:
                    best.pop("score", None)
                    detections.append({
                        "frame": frame_index,
                        "time": round(frame_index / fps, 3),
                        "detector": "yolov8-person",
                        "personCount": person_count,
                        "primaryPersonCount": primary_count,
                        **best,
                    })
                else:
                    detections.append({
                        "frame": frame_index,
                        "time": round(frame_index / fps, 3),
                        "detector": "yolov8-person",
                        "personCount": 0,
                        "primaryPersonCount": 0,
                    })

            frame_index += 1
    finally:
        capture.release()

    (context["temp_dir"] / "face_detections.json").write_text(
        json.dumps({
            "method": "yolov8-person",
            "model": model_name,
            "sampledFrames": sampled_frames,
            "frameInterval": frame_interval,
            "detections": detections,
        }, indent=2),
        encoding="utf-8",
    )
