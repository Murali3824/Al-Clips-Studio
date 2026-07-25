import json
from pathlib import Path
import subprocess
import torch

from silero_vad import load_silero_vad, get_speech_timestamps
import numpy as np
import wave

def load_audio_wav(path: str) -> torch.Tensor:
    with wave.open(path, "rb") as wf:
        n_frames = wf.getnframes()
        data = wf.readframes(n_frames)
        audio = np.frombuffer(data, dtype=np.int16)
        # Convert to float32 and normalize
        audio = audio.astype(np.float32) / 32768.0
        return torch.from_numpy(audio)


def _audio_duration(audio_path) -> float:
    completed = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(audio_path),
        ],
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        raise RuntimeError(completed.stderr.strip() or "Could not read audio duration")
    return float(completed.stdout.strip())


def run(context):
    audio_path = context["temp_dir"] / "audio.wav"
    if not audio_path.exists():
        raise FileNotFoundError(f"Audio file not found: {audio_path}")

    duration = _audio_duration(audio_path)

    # 1. Resolve local model files
    models_dir = Path(context["root"]) / "models"
    onnx_path = models_dir / "silero_vad.onnx"
    jit_path = models_dir / "silero_vad.jit"

    # Set threads to 1 for CPU performance
    torch.set_num_threads(1)

    if onnx_path.exists():
        model = load_silero_vad(onnx=True, model_file_path=str(onnx_path))
    elif jit_path.exists():
        model = load_silero_vad(onnx=False, model_file_path=str(jit_path))
    else:
        # Fallback to standard package default model loading
        model = load_silero_vad(onnx=True)

    wav = load_audio_wav(str(audio_path))
    raw_timestamps = get_speech_timestamps(
        wav,
        model,
        sampling_rate=16000,
        return_seconds=True,
    )

    speech = []
    for segment in raw_timestamps:
        start = round(float(segment["start"]), 3)
        end = round(float(segment["end"]), 3)
        speech.append({
            "start": start,
            "end": end,
            "duration": round(end - start, 3),
        })

    if not speech:
        raise RuntimeError("No speech activity detected in extracted audio via Silero VAD")

    # Reconstruct silences list from speech segments
    silences = []
    cursor = 0.0
    for segment in speech:
        seg_start = segment["start"]
        if seg_start - cursor >= 0.1:
            silences.append({
                "start": round(cursor, 3),
                "end": round(seg_start, 3),
            })
        cursor = segment["end"]
    if duration - cursor >= 0.1:
        silences.append({
            "start": round(cursor, 3),
            "end": round(duration, 3),
        })

    (context["temp_dir"] / "speech_timestamps.json").write_text(
        json.dumps(
            {
                "duration": duration,
                "method": "silero-vad",
                "silences": silences,
                "segments": speech,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
