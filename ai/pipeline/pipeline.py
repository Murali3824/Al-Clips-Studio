import sys
import io

# Force UTF-8 stream encoding on Windows to prevent charmap codec errors when printing unicode characters like '→'
if hasattr(sys.stdout, 'buffer'):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
if hasattr(sys.stderr, 'buffer'):
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

import argparse
import json
import warnings
from pathlib import Path
from typing import Any

warnings.filterwarnings(
    "ignore",
    message=r"urllib3 .* doesn't match a supported version!",
)
try:
    from requests.exceptions import RequestsDependencyWarning

    warnings.filterwarnings("ignore", category=RequestsDependencyWarning)
except Exception:
    pass

from progress import emit_error, emit_progress
from stages.stage_01_audio import run as run_audio
from stages.stage_02_vad import run as run_vad
from stages.stage_03_transcription import run as run_transcription
from stages.stage_03_speaker_diarization import run as run_speaker_diarization
from stages.stage_04_highlights import run as run_highlights
from stages.stage_05_scene_detection import run as run_scene_detection
from stages.stage_06_face_detection import run as run_face_detection
from stages.stage_07_face_tracking import run as run_face_tracking
from stages.stage_07_subject_identity import run as run_subject_identity
from stages.stage_08_shot_selection import run as run_shot_selection
from stages.stage_08b_anchor_stream import run as run_anchor_stream
from stages.stage_08c_camera_operator import run as run_camera_operator
from stages.stage_08d_transition_planner import run as run_transition_planner
from stages.stage_09_cut_crop import run as run_cut_crop
from stages.stage_10_captions import run as run_captions
from stages.stage_11_metadata import run as run_metadata
from stages.stage_12_export import run as run_export
from stages.stage_13_thumbnails import run as run_thumbnails
from stages.stage_14_music import run as run_music
from stages.stage_15_translation import run as run_translation

Stage = tuple[str, str, Any]

STAGES: list[Stage] = [
    ("stage_01_audio", "Audio extraction", run_audio),
    ("stage_02_vad", "Voice activity detection", run_vad),
    ("stage_03_transcription", "Transcription", run_transcription),
    ("stage_03_speaker_diarization", "Speaker diarization", run_speaker_diarization),
    ("stage_04_highlights", "Highlight detection", run_highlights),
    ("stage_05_scene_detection", "Scene detection", run_scene_detection),
    ("stage_06_face_detection", "Face detection", run_face_detection),
    ("stage_07_face_tracking", "Face tracking", run_face_tracking),
    ("stage_07_subject_identity", "Subject identity continuity", run_subject_identity),
    ("stage_08_shot_selection", "Editorial shot selection", run_shot_selection),
    ("stage_08b_anchor_stream", "Per-frame anchor stream", run_anchor_stream),
    ("stage_08c_camera_operator", "Spring-damped camera operator", run_camera_operator),
    ("stage_08d_transition_planner", "Smooth editorial transitions", run_transition_planner),
    ("stage_09_cut_crop", "Video cut and crop", run_cut_crop),
    ("stage_10_captions", "Caption generation", run_captions),
    ("stage_11_metadata", "Metadata generation", run_metadata),
    ("stage_12_export", "Export preparation", run_export),
    ("stage_15_translation", "Translation", run_translation),
    ("stage_14_music", "Background music", run_music),
    ("stage_13_thumbnails", "Thumbnail generation", run_thumbnails),
]


def project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def run_test() -> None:
    print(json.dumps({
        "ok": True,
        "pipeline": "ai-shorts-generator",
        "message": "Python pipeline core is ready."
    }))


def load_settings(raw_settings: str | None) -> dict[str, Any]:
    if not raw_settings:
        return {}
    return json.loads(raw_settings)


def build_context(job_id: str, settings: dict[str, Any]) -> dict[str, Any]:
    root = project_root()
    job_upload_dir = root / "storage" / "uploads" / job_id
    job_temp_dir = root / "storage" / "temp" / job_id
    job_output_dir = root / "storage" / "outputs" / job_id

    job_temp_dir.mkdir(parents=True, exist_ok=True)
    job_output_dir.mkdir(parents=True, exist_ok=True)

    return {
        "job_id": job_id,
        "settings": settings,
        "root": root,
        "upload_dir": job_upload_dir,
        "temp_dir": job_temp_dir,
        "output_dir": job_output_dir,
        "checkpoint_path": job_temp_dir / "checkpoint.json",
    }


def load_checkpoint(path: Path) -> set[str]:
    if not path.exists():
        return set()

    data = json.loads(path.read_text(encoding="utf-8"))
    return set(data.get("completed", []))


def save_checkpoint(path: Path, completed: set[str]) -> None:
    path.write_text(
        json.dumps({"completed": sorted(completed)}, indent=2),
        encoding="utf-8",
    )


def run_pipeline(job_id: str, settings: dict[str, Any]) -> None:
    context = build_context(job_id, settings)
    completed = load_checkpoint(context["checkpoint_path"])
    total = len(STAGES)

    emit_progress(job_id, "pipeline", "started", 0, "Pipeline started")

    for index, (stage_id, label, runner) in enumerate(STAGES, start=1):
        if stage_id in completed:
            emit_progress(job_id, stage_id, "skipped", int(index / total * 100), label)
            continue

        emit_progress(job_id, stage_id, "running", int((index - 1) / total * 100), label)
        try:
            runner(context)
        except Exception as error:
            emit_progress(job_id, stage_id, "failed", int((index - 1) / total * 100), label)
            emit_error(job_id, stage_id, str(error))
            raise SystemExit(1) from None
        completed.add(stage_id)
        save_checkpoint(context["checkpoint_path"], completed)
        emit_progress(job_id, stage_id, "complete", int(index / total * 100), label)

    print("Pipeline completed successfully.", flush=True)
    emit_progress(job_id, "pipeline", "complete", 100, "Pipeline complete")


def main() -> None:
    parser = argparse.ArgumentParser(description="AI Shorts Generator pipeline")
    parser.add_argument("--test", action="store_true", help="Run foundation check")
    parser.add_argument("--job-id", help="Uploaded job ID to process")
    parser.add_argument("--settings", help="JSON settings payload")
    args = parser.parse_args()

    if args.test:
        run_test()
        return

    if not args.job_id:
        raise SystemExit("--job-id is required")

    run_pipeline(args.job_id, load_settings(args.settings))


if __name__ == "__main__":
    main()
