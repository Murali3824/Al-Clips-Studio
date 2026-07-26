import json

import cv2


def _sharpness(frame) -> float:
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    return float(cv2.Laplacian(gray, cv2.CV_64F).var())


def _extract_best_frame(video_path, target_path) -> dict:
    capture = cv2.VideoCapture(str(video_path))
    if not capture.isOpened():
        raise RuntimeError(f"Could not open clip for thumbnail: {video_path}")

    frame_count = int(capture.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    fps = float(capture.get(cv2.CAP_PROP_FPS) or 30)
    sample_indexes = []
    if frame_count > 0:
        sample_indexes = [
            max(0, min(frame_count - 1, int(frame_count * ratio)))
            for ratio in (0.25, 0.4, 0.5, 0.6, 0.75)
        ]
    else:
        sample_indexes = [0]

    best = None
    try:
        for index in sample_indexes:
            capture.set(cv2.CAP_PROP_POS_FRAMES, index)
            ok, frame = capture.read()
            if not ok:
                continue
            score = _sharpness(frame)
            if best is None or score > best["score"]:
                best = {
                    "frame": frame,
                    "frameIndex": index,
                    "time": round(index / fps, 3),
                    "score": score,
                }
    finally:
        capture.release()

    if best is None:
        raise RuntimeError(f"No readable frames found for thumbnail: {video_path}")

    if not cv2.imwrite(str(target_path), best["frame"]):
        raise RuntimeError(f"Could not write thumbnail: {target_path}")

    return {
        "frameIndex": best["frameIndex"],
        "time": best["time"],
        "sharpness": round(best["score"], 3),
    }


def run(context):
    print("Generating thumbnails...", flush=True)
    thumbnails_dir = context["output_dir"] / "thumbnails"
    thumbnails_dir.mkdir(parents=True, exist_ok=True)

    clips_path = context["output_dir"] / "clips.json"
    clips = json.loads(clips_path.read_text(encoding="utf-8"))["clips"]
    updated_clips = []

    for clip in clips:
        clip_path = context["output_dir"] / "clips" / f"{clip['id']}.mp4"
        thumbnail_path = thumbnails_dir / f"{clip['id']}.png"
        thumbnail = _extract_best_frame(clip_path, thumbnail_path)
        updated_clips.append({
            **clip,
            "thumbnailPath": str(thumbnail_path),
            "thumbnail": thumbnail,
        })

    clips_path.write_text(
        json.dumps({"clips": updated_clips}, indent=2),
        encoding="utf-8",
    )
