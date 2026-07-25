import json

from media_utils import extract_video_metadata, find_input_video, run_command


def run(context):
    input_video = find_input_video(context["upload_dir"])
    metadata = extract_video_metadata(input_video)
    audio_path = context["temp_dir"] / "audio.wav"

    run_command([
        "ffmpeg",
        "-y",
        "-i",
        str(input_video),
        "-vn",
        "-acodec",
        "pcm_s16le",
        "-ar",
        "16000",
        "-ac",
        "1",
        str(audio_path),
    ])

    (context["temp_dir"] / "video_metadata.json").write_text(
        json.dumps(metadata, indent=2),
        encoding="utf-8",
    )
    (context["temp_dir"] / "audio.json").write_text(
        json.dumps({"audioPath": str(audio_path)}, indent=2),
        encoding="utf-8",
    )
