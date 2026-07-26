"""Stage 14 — Background Music Mixing.

Mixes background music tracks into generated video clips using FFmpeg.
Uses the centralized MusicLibrary for track scanning, validation, and selection.

Music directory: storage/music/ (single source of truth)
"""

import json
import shutil
from pathlib import Path

from media_utils import run_command
from music_library import MusicLibrary, has_audio_stream

SUPPORTED_AUDIO = {".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg"}

_PREFIX = "[BackgroundMusic]"


def _write_status(context, status: dict) -> None:
    (context["output_dir"] / "music.json").write_text(
        json.dumps(status, indent=2),
        encoding="utf-8",
    )


def _build_music_filter(volume: float, duration: float) -> str:
    """Build the FFmpeg audio filter for music mixing.

    Scales fade duration proportionally for short clips to prevent
    fade-in and fade-out from overlapping.
    """
    # Scale fade duration: max 1s, but never more than 25% of clip duration
    fade_d = min(1.0, duration * 0.25)

    if duration < 0.5:
        # Extremely short clip — skip fades entirely
        return (
            f"[1:a]volume={volume:.3f}[music];"
            "[0:a][music]amix=inputs=2:duration=first:dropout_transition=0[aout]"
        )

    fade_out_start = max(0, duration - fade_d)
    return (
        f"[1:a]volume={volume:.3f},"
        f"afade=t=in:st=0:d={fade_d:.3f},"
        f"afade=t=out:st={fade_out_start:.3f}:d={fade_d:.3f}[music];"
        "[0:a][music]amix=inputs=2:duration=first:dropout_transition=0[aout]"
    )


def run(context):
    print(f"{_PREFIX} Starting background music processing...", flush=True)
    settings = context["settings"]

    if not settings.get("backgroundMusic", False):
        _write_status(context, {"enabled": False, "mixed": False, "reason": "disabled"})
        print(f"{_PREFIX} Background music is disabled in settings.", flush=True)
        return

    # Initialize music library from single source of truth
    music_dir = Path(context["root"]) / "storage" / "music"
    library = MusicLibrary(music_dir)
    tracks = library.scan()

    if not tracks:
        _write_status(context, {
            "enabled": True,
            "mixed": False,
            "reason": "no valid music files found in storage/music/",
        })
        print(f"{_PREFIX} No valid music tracks available.", flush=True)
        return

    volume = max(0, min(100, int(settings.get("musicVolume", 20)))) / 100
    clips_path = context["output_dir"] / "clips.json"
    clips = json.loads(clips_path.read_text(encoding="utf-8"))["clips"]

    job_id = context.get("job_id", "")
    updated = []
    mixed_count = 0
    skipped_count = 0

    for index, clip in enumerate(clips):
        source = Path(clip["path"])
        if not source.exists():
            raise FileNotFoundError(f"Clip not found for music mix: {source}")

        # Select track with intelligent randomization
        selected = library.select_track(
            clip_index=index,
            total_clips=len(clips),
            content_category=clip.get("source", ""),
            job_id=job_id,
        )

        if not selected:
            print(f"{_PREFIX} Clip {index + 1}: No valid track available, skipping.", flush=True)
            updated.append(clip)
            skipped_count += 1
            continue

        track_path = selected["path"]
        duration = float(clip.get("duration", 0))

        if duration < 0.1:
            print(f"{_PREFIX} Clip {index + 1}: Duration too short ({duration:.1f}s), skipping music.", flush=True)
            updated.append(clip)
            skipped_count += 1
            continue

        # Build FFmpeg command
        filter_str = _build_music_filter(volume, duration)
        temp_output = source.parent / f"_music_temp_{clip['id']}.mp4"

        ffmpeg_cmd = [
            "ffmpeg", "-y",
            "-i", str(source),
            "-stream_loop", "-1",
            "-i", str(track_path),
        ]

        # Handle videos without audio stream
        if not has_audio_stream(source):
            print(f"{_PREFIX} Clip {index + 1}: No audio stream detected, generating silent base.", flush=True)
            ffmpeg_cmd = [
                "ffmpeg", "-y",
                "-i", str(source),
                "-f", "lavfi", "-i", f"anullsrc=channel_layout=stereo:sample_rate=44100",
                "-stream_loop", "-1",
                "-i", str(track_path),
                "-filter_complex",
                (
                    f"[1:a]atrim=0:{duration:.3f},asetpts=PTS-STARTPTS[silent];"
                    f"[2:a]volume={volume:.3f},"
                    f"afade=t=in:st=0:d={min(1.0, duration * 0.25):.3f},"
                    f"afade=t=out:st={max(0, duration - min(1.0, duration * 0.25)):.3f}:"
                    f"d={min(1.0, duration * 0.25):.3f}[music];"
                    "[silent][music]amix=inputs=2:duration=first:dropout_transition=0[aout]"
                ),
                "-map", "0:v:0", "-map", "[aout]",
                "-c:v", "copy", "-c:a", "aac",
                "-shortest", "-movflags", "+faststart",
                str(temp_output),
            ]
        else:
            ffmpeg_cmd += [
                "-filter_complex", filter_str,
                "-map", "0:v:0", "-map", "[aout]",
                "-c:v", "copy", "-c:a", "aac",
                "-shortest", "-movflags", "+faststart",
                str(temp_output),
            ]

        try:
            run_command(ffmpeg_cmd)
        except Exception as exc:
            print(f"{_PREFIX} Clip {index + 1}: Music mixing failed ({exc}), keeping original.", flush=True)
            updated.append(clip)
            skipped_count += 1
            if temp_output.exists():
                temp_output.unlink()
            continue

        # Atomic replace: move temp file over source (no pre-unlink)
        try:
            temp_output.replace(source)
        except OSError:
            # Fallback for cross-device moves
            shutil.move(str(temp_output), str(source))

        mixed_count += 1
        updated.append({
            **clip,
            "musicTrack": str(track_path),
            "musicVolume": int(volume * 100),
        })

    clips_path.write_text(json.dumps({"clips": updated}, indent=2), encoding="utf-8")
    _write_status(context, {
        "enabled": True,
        "mixed": True,
        "trackCount": len(tracks),
        "clipCount": len(updated),
        "mixedCount": mixed_count,
        "skippedCount": skipped_count,
        "volume": int(volume * 100),
    })

    print(
        f"{_PREFIX} Complete: {mixed_count} clips mixed"
        + (f", {skipped_count} skipped" if skipped_count else ""),
        flush=True,
    )
