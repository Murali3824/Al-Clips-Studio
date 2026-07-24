import json
import subprocess
from pathlib import Path
from typing import Any


def find_input_video(upload_dir: Path) -> Path:
    matches = sorted(upload_dir.glob("input.*"))
    if not matches:
        raise FileNotFoundError(f"No uploaded video found in {upload_dir}")
    return matches[0]


def run_command(args: list[str]) -> None:
    completed = subprocess.run(args, capture_output=True, text=True)
    if completed.returncode != 0:
        raise RuntimeError(completed.stderr.strip() or completed.stdout.strip())


def ffprobe(video_path: Path) -> dict[str, Any]:
    completed = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-print_format",
            "json",
            "-show_format",
            "-show_streams",
            str(video_path),
        ],
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        raise RuntimeError(completed.stderr.strip() or "FFprobe failed")
    return json.loads(completed.stdout)


def extract_video_metadata(video_path: Path) -> dict[str, Any]:
    probe = ffprobe(video_path)
    video_stream = next(
        (stream for stream in probe["streams"] if stream.get("codec_type") == "video"),
        None,
    )
    audio_stream = next(
        (stream for stream in probe["streams"] if stream.get("codec_type") == "audio"),
        None,
    )
    if video_stream is None:
        raise RuntimeError("Uploaded file does not contain a video stream")

    fps_parts = str(video_stream.get("avg_frame_rate", "0/1")).split("/")
    fps = (
        float(fps_parts[0]) / float(fps_parts[1])
        if len(fps_parts) == 2 and float(fps_parts[1]) != 0
        else 0
    )

    return {
        "duration": float(probe.get("format", {}).get("duration", 0)),
        "sizeBytes": int(probe.get("format", {}).get("size", 0)),
        "formatName": probe.get("format", {}).get("format_name"),
        "width": int(video_stream.get("width", 0)),
        "height": int(video_stream.get("height", 0)),
        "fps": round(fps, 3),
        "videoCodec": video_stream.get("codec_name"),
        "audioCodec": audio_stream.get("codec_name") if audio_stream else None,
    }
