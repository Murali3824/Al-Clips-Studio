import contextlib
import io
import json
import os
import warnings
from typing import Any

warnings.filterwarnings(
    "ignore",
    message=r"urllib3 .* doesn't match a supported version!",
)
warnings.filterwarnings(
    "ignore",
    message=r".*torchcodec.*",
)


DEFAULT_MODEL = "pyannote/speaker-diarization-3.1"


def _skip(context, reason: str) -> None:
    payload = {
        "enabled": bool(context["settings"].get("speakerDiarization", False)),
        "skipped": True,
        "reason": reason,
        "turns": [],
    }
    (context["temp_dir"] / "speaker_diarization.json").write_text(
        json.dumps(payload, indent=2),
        encoding="utf-8",
    )


def _token(settings: dict[str, Any]) -> str | None:
    return (
        settings.get("huggingFaceToken")
        or os.environ.get("HUGGINGFACE_TOKEN")
        or os.environ.get("HF_TOKEN")
    )


def _load_pipeline(model_name: str, token: str):
    try:
        from pyannote.audio import Pipeline
    except ImportError as error:
        raise RuntimeError("pyannote.audio is not installed") from error

    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        pipeline = Pipeline.from_pretrained(model_name, use_auth_token=token)
    if pipeline is None:
        raise RuntimeError(
            f"Could not load diarization model '{model_name}'. "
            "Accept the model terms on Hugging Face and provide a valid token."
        )
    return pipeline


def _load_audio(audio_path):
    import numpy as np
    import torch
    from scipy.io import wavfile

    sample_rate, samples = wavfile.read(str(audio_path))
    if samples.ndim == 1:
        samples = samples[np.newaxis, :]
    else:
        samples = samples.T

    if np.issubdtype(samples.dtype, np.integer):
        max_value = float(np.iinfo(samples.dtype).max)
        samples = samples.astype(np.float32) / max_value
    else:
        samples = samples.astype(np.float32)

    waveform = torch.from_numpy(samples)
    return {
        "waveform": waveform,
        "sample_rate": int(sample_rate),
    }


def _turns_from_annotation(annotation) -> list[dict[str, Any]]:
    turns = []
    for turn, _, speaker in annotation.itertracks(yield_label=True):
        turns.append({
            "start": round(float(turn.start), 3),
            "end": round(float(turn.end), 3),
            "speaker": str(speaker),
        })
    return sorted(turns, key=lambda item: (item["start"], item["end"]))


def _overlap(left_start: float, left_end: float, right_start: float, right_end: float) -> float:
    return max(0.0, min(left_end, right_end) - max(left_start, right_start))


def _speaker_for_range(start: float, end: float, turns: list[dict[str, Any]]) -> str | None:
    best_speaker = None
    best_overlap = 0.0
    for turn in turns:
        overlap = _overlap(start, end, float(turn["start"]), float(turn["end"]))
        if overlap > best_overlap:
            best_overlap = overlap
            best_speaker = str(turn["speaker"])
    return best_speaker


def _annotate_transcript(context, turns: list[dict[str, Any]]) -> None:
    transcript_path = context["temp_dir"] / "transcript.json"
    transcript = json.loads(transcript_path.read_text(encoding="utf-8"))

    for word in transcript.get("words", []):
        speaker = _speaker_for_range(float(word["start"]), float(word["end"]), turns)
        if speaker:
            word["speaker"] = speaker

    for segment in transcript.get("segments", []):
        speaker = _speaker_for_range(float(segment["start"]), float(segment["end"]), turns)
        if speaker:
            segment["speaker"] = speaker
        for word in segment.get("words", []):
            speaker = _speaker_for_range(float(word["start"]), float(word["end"]), turns)
            if speaker:
                word["speaker"] = speaker

    transcript["speakerDiarization"] = {
        "enabled": True,
        "skipped": False,
        "turns": turns,
    }
    transcript_path.write_text(json.dumps(transcript, indent=2), encoding="utf-8")


def run(context):
    settings = context["settings"]
    if not settings.get("speakerDiarization", False):
        _skip(context, "Speaker diarization is disabled for this job.")
        return

    audio_path = context["temp_dir"] / "audio.wav"
    if not audio_path.exists():
        raise FileNotFoundError(f"Audio file not found for diarization: {audio_path}")

    token = _token(settings)
    if not token:
        _skip(
            context,
            "Speaker diarization requires HUGGINGFACE_TOKEN or HF_TOKEN. Skipping diarization.",
        )
        return

    model_name = settings.get("diarizationModel", DEFAULT_MODEL)
    try:
        pipeline = _load_pipeline(model_name, token)
        audio = _load_audio(audio_path)
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            annotation = pipeline(audio)
    except RuntimeError as error:
        _skip(context, str(error))
        return

    turns = _turns_from_annotation(annotation)
    _annotate_transcript(context, turns)
    (context["temp_dir"] / "speaker_diarization.json").write_text(
        json.dumps({
            "enabled": True,
            "skipped": False,
            "model": model_name,
            "turnCount": len(turns),
            "speakers": sorted({turn["speaker"] for turn in turns}),
            "turns": turns,
        }, indent=2),
        encoding="utf-8",
    )
