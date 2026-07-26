import json
import shutil
from pathlib import Path


def run(context):
    print("Saving output clips...", flush=True)
    clips_dir = context["output_dir"] / "clips"
    clips_dir.mkdir(parents=True, exist_ok=True)

    clips = json.loads(
        (context["output_dir"] / "clips.json").read_text(encoding="utf-8")
    )["clips"]
    exported = []

    for clip in clips:
        source = clip.get("captionedPath") or str(
            context["temp_dir"] / "raw_clips" / f"{clip['id']}.mp4"
        )
        source_path = Path(source)
        if not source_path.is_absolute():
            source_path = context["root"] / source_path

        if not source_path.exists():
            raise FileNotFoundError(f"Processed clip not found: {source_path}")

        target = clips_dir / f"{clip['id']}.mp4"
        shutil.move(str(source_path), str(target))
        exported.append({**clip, "path": str(target)})

    (context["output_dir"] / "clips.json").write_text(
        json.dumps({"clips": exported}, indent=2),
        encoding="utf-8",
    )
