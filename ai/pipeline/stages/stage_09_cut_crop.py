import json
from pathlib import Path

import sys
sys.path.append(str(Path(__file__).resolve().parent.parent))

from media_utils import find_input_video
from render_engine import (
    SHORTS_WIDTH,
    SHORTS_HEIGHT,
    encode_clip_with_layout_transitions,
)


def _load_crop_plans(context) -> dict:
    crop_path = context["temp_dir"] / "crop_coords.json"
    if not crop_path.exists():
        return {}
    crop_data = json.loads(crop_path.read_text(encoding="utf-8"))
    return {plan["clipId"]: plan for plan in crop_data.get("plans", [])}


def run(context):
    raw_clips_dir = context["temp_dir"] / "raw_clips"
    raw_clips_dir.mkdir(parents=True, exist_ok=True)

    input_video = find_input_video(context["upload_dir"])
    metadata = json.loads(
        (context["temp_dir"] / "video_metadata.json").read_text(encoding="utf-8")
    )
    video_duration = float(metadata["duration"])
    highlights = json.loads(
        (context["temp_dir"] / "highlights.json").read_text(encoding="utf-8")
    )["highlights"]
    crop_plans = _load_crop_plans(context)

    print("Starting video cut and crop...", flush=True)
    clips = []
    total_clips = len(highlights)
    for index, highlight in enumerate(highlights, start=1):
        print(f"Rendering clip {index}/{total_clips}...", flush=True)
        start = max(0.0, float(highlight["start"]))
        end = min(video_duration, float(highlight["end"]))
        duration = max(0.1, end - start)
        clip_path = raw_clips_dir / f"{highlight['id']}.mp4"
        plan = crop_plans.get(highlight["id"])

        layout_segments = plan.get("layoutSegments", []) if plan else []
        if not layout_segments:
            layout_segments = [{
                "start": start,
                "end": end,
                "layout": plan.get("layoutMode", "full-crop") if plan else "full-crop",
            }]

        encode_clip_with_layout_transitions(
            input_video=str(input_video),
            clip_start=start,
            clip_duration=duration,
            segments=layout_segments,
            plan=plan,
            output_path=str(clip_path),
            target_w=SHORTS_WIDTH,
            target_h=SHORTS_HEIGHT,
        )

        layout_mode = plan.get("layoutMode", "full-crop") if plan else "full-crop"
        clips.append({
            "id": highlight["id"],
            "path": str(clip_path),
            "start": start,
            "end": end,
            "duration": duration,
            "aiStart": start,
            "aiEnd": end,
            "userStart": start,
            "userEnd": end,
            "width": SHORTS_WIDTH,
            "height": SHORTS_HEIGHT,
            "aspectRatio": "9:16",
            "layoutMode": layout_mode,
            "layoutSegments": layout_segments,
            "crop": crop_plans.get(highlight["id"]),
            "score": highlight["score"],
            "hook": highlight["hook"],
            "reason": highlight.get("reason"),
            "source": highlight.get("source"),
            "model": highlight.get("model"),
        })

    (context["output_dir"] / "clips.json").write_text(
        json.dumps({"clips": clips}, indent=2),
        encoding="utf-8",
    )
