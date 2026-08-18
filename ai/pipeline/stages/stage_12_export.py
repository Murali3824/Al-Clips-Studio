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

        end_thumb = clip.get("endThumbnail")
        if end_thumb and isinstance(end_thumb, dict) and end_thumb.get("enabled"):
            img_rel_path = end_thumb.get("imagePath")
            if img_rel_path:
                img_full_path = Path(img_rel_path)
                if not img_full_path.is_absolute():
                    img_full_path = context["output_dir"] / img_rel_path
                if img_full_path.exists():
                    try:
                        from retrim import _append_end_thumbnail
                        temp_out = context["temp_dir"] / f"{clip['id']}_export_end_thumb.mp4"
                        _append_end_thumbnail(str(target), str(img_full_path), str(temp_out), 1080, 1920, 0.5)
                        if temp_out.exists():
                            shutil.move(str(temp_out), str(target))
                    except Exception as e:
                        print(f"Warning: stage_12_export end thumbnail failed: {e}")

        exported.append({**clip, "path": str(target)})

    (context["output_dir"] / "clips.json").write_text(
        json.dumps({"clips": exported}, indent=2),
        encoding="utf-8",
    )
