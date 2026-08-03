import json

from media_utils import run_command
from stages.stage_10_captions import _chunk_words, _dialogue_line, _style_header
from translation.providers import configured_provider


def _ass_filter_path(path) -> str:
    return str(path).replace("\\", "/").replace(":", r"\:")


def _write_status(context, status: dict) -> None:
    (context["output_dir"] / "translations.json").write_text(
        json.dumps(status, indent=2),
        encoding="utf-8",
    )


def run(context):
    languages = context["settings"].get("translationLanguages", [])
    if not languages:
        _write_status(context, {
            "enabled": False,
            "skipped": True,
            "reason": "no translation languages selected",
            "languages": [],
            "clips": [],
        })
        return

    provider = configured_provider(context["settings"])
    if provider is None or not provider.is_available():
        message = "Translation service is unavailable. Skipping translation."
        print(message, flush=True)
        _write_status(context, {
            "enabled": True,
            "skipped": True,
            "reason": message,
            "provider": provider.name if provider else None,
            "languages": languages,
            "clips": [],
        })
        return

    style = context["settings"].get("captionStyle", "word-highlight")
    transcript = json.loads(
        (context["temp_dir"] / "transcript.json").read_text(encoding="utf-8")
    )
    clips = json.loads(
        (context["output_dir"] / "clips.json").read_text(encoding="utf-8")
    )["clips"]
    words = transcript.get("words", [])

    translated_outputs = []
    for language in languages:
        language_dir = context["output_dir"] / "translations" / language
        language_caption_dir = context["output_dir"] / "translated_captions" / language
        language_dir.mkdir(parents=True, exist_ok=True)
        language_caption_dir.mkdir(parents=True, exist_ok=True)

        for clip in clips:
            clip_start = float(clip["start"])
            clip_end = float(clip["end"])
            clip_words = [
                {
                    **word,
                    "start": float(word["start"]) - clip_start,
                    "end": float(word["end"]) - clip_start,
                }
                for word in words
                if float(word["end"]) > clip_start and float(word["start"]) < clip_end
            ]
            if not clip_words:
                raise RuntimeError(f"No transcript words found for translation: {clip['id']}")

            ass_path = language_caption_dir / f"{clip['id']}.ass"
            ass_text = _style_header(style)
            for chunk in _chunk_words(clip_words):
                source_text = " ".join(str(word["word"]).strip() for word in chunk)
                translated_text = provider.translate(source_text, language)
                start = float(chunk[0]["start"])
                end = max(float(chunk[-1]["end"]), start + 0.4)
                ass_text += _dialogue_line(start, end, translated_text)
            ass_path.write_text(ass_text, encoding="utf-8")

            source = context["temp_dir"] / "raw_clips" / f"{clip['id']}.mp4"
            if not source.exists():
                raise FileNotFoundError(f"Raw clip not found for translation: {source}")

            target = language_dir / f"{clip['id']}.mp4"
            run_command([
                "ffmpeg",
                "-y",
                "-i",
                str(source),
                "-vf",
                f"ass='{_ass_filter_path(ass_path)}'",
                "-c:v",
                "libx264",
                "-preset",
                "veryfast",
                "-crf",
                "23",
                "-c:a",
                "copy",
                "-movflags",
                "+faststart",
                str(target),
            ])
            translated_outputs.append({
                "clipId": clip["id"],
                "language": language,
                "path": str(target),
                "captionPath": str(ass_path),
            })

    _write_status(context, {
        "enabled": True,
        "skipped": False,
        "provider": provider.name,
        "languages": languages,
        "clips": translated_outputs,
    })
