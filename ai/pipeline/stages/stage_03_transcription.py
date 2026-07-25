import contextlib
import io
import json
import os
import warnings
from typing import Any

os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")
os.environ.setdefault("HF_HUB_DOWNLOAD_TIMEOUT", "120")

warnings.filterwarnings(
    "ignore",
    message=r"urllib3 .* doesn't match a supported version!",
)

from faster_whisper import WhisperModel

ALLOWED_MODELS = {"tiny", "medium", "large-v3"}


def _word_to_dict(word: Any) -> dict[str, Any]:
    return {
        "word": word.word.strip(),
        "start": float(word.start),
        "end": float(word.end),
        "probability": float(word.probability),
    }


def _segment_to_dict(segment: Any) -> dict[str, Any]:
    words = [_word_to_dict(word) for word in segment.words or []]
    return {
        "id": segment.id,
        "start": float(segment.start),
        "end": float(segment.end),
        "text": segment.text.strip(),
        "words": words,
    }


def _stable_word_to_dict(word: dict[str, Any]) -> dict[str, Any]:
    probability = word.get("probability", word.get("prob", 0.0))
    return {
        "word": str(word.get("word", "")).strip(),
        "start": float(word["start"]),
        "end": float(word["end"]),
        "probability": float(probability or 0.0),
    }


def _stable_segment_to_dict(index: int, segment: dict[str, Any]) -> dict[str, Any]:
    words = [
        _stable_word_to_dict(word)
        for word in segment.get("words", [])
        if word.get("word") and word.get("start") is not None and word.get("end") is not None
    ]
    return {
        "id": int(segment.get("id", index)),
        "start": float(segment["start"]),
        "end": float(segment["end"]),
        "text": str(segment.get("text", "")).strip(),
        "words": words,
    }


def _transcribe_with_stable_ts(
    audio_path,
    model_name: str,
    compute_type: str,
    language: str | None,
) -> dict[str, Any]:
    import stable_whisper

    model = stable_whisper.load_faster_whisper(
        model_name,
        device="auto",
        compute_type=compute_type,
    )
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        result = model.transcribe(
            str(audio_path),
            beam_size=5,
            language=language,
            vad_filter=False,
            word_timestamps=True,
            verbose=False,
            suppress_silence=True,
            suppress_word_ts=True,
        )
    data = result.to_dict()
    segments = [
        _stable_segment_to_dict(index, segment)
        for index, segment in enumerate(data.get("segments", []))
        if segment.get("start") is not None and segment.get("end") is not None
    ]
    words = [word for segment in segments for word in segment["words"]]
    if not segments or not words:
        raise RuntimeError("stable-ts did not return usable word-level timestamps")

    return {
        "text": str(data.get("text", "")).strip(),
        "language": data.get("language") or language,
        "languageProbability": None,
        "duration": max(float(segment["end"]) for segment in segments),
        "segments": segments,
        "words": words,
        "model": model_name,
        "timingEngine": "stable-ts",
    }


def _transcribe_with_faster_whisper(
    audio_path,
    model_name: str,
    compute_type: str,
    language: str | None,
) -> dict[str, Any]:
    model = WhisperModel(
        model_name,
        device="auto",
        compute_type=compute_type,
    )
    segments_iter, info = model.transcribe(
        str(audio_path),
        beam_size=5,
        language=language,
        vad_filter=False,
        word_timestamps=True,
    )
    segments = [_segment_to_dict(segment) for segment in segments_iter]
    words = [word for segment in segments for word in segment["words"]]
    text = " ".join(segment["text"] for segment in segments).strip()

    return {
        "text": text,
        "language": info.language,
        "languageProbability": info.language_probability,
        "duration": info.duration,
        "segments": segments,
        "words": words,
        "model": model_name,
        "timingEngine": "faster-whisper",
    }


def run(context):
    audio_path = context["temp_dir"] / "audio.wav"
    if not audio_path.exists():
        raise FileNotFoundError(f"Audio file not found: {audio_path}")

    settings = context["settings"]
    model_name = settings.get("whisperModel", "medium")
    compute_type = settings.get("whisperComputeType", "int8")
    language = settings.get("language")

    if model_name not in ALLOWED_MODELS:
        raise ValueError(f"Unsupported Whisper model: {model_name}")

    from pathlib import Path
    local_model_path = Path(context["root"]) / "models" / f"whisper-{model_name}"
    if local_model_path.exists() and local_model_path.is_dir():
        model_name_or_path = str(local_model_path)
    else:
        model_name_or_path = model_name

    try:
        transcript = _transcribe_with_stable_ts(
            audio_path,
            model_name_or_path,
            compute_type,
            language,
        )
    except Exception as error:
        try:
            transcript = _transcribe_with_faster_whisper(
                audio_path,
                model_name_or_path,
                compute_type,
                language,
            )
            transcript["timingFallbackReason"] = str(error)
        except Exception as fallback_error:
            raise RuntimeError(
                f"Whisper model '{model_name}' could not be loaded or run. "
                "If this is the first use, let the model download finish or choose a smaller model. "
                f"stable-ts error: {error}. faster-whisper error: {fallback_error}"
            ) from None

    (context["temp_dir"] / "transcript.json").write_text(
        json.dumps(transcript, indent=2),
        encoding="utf-8",
    )
