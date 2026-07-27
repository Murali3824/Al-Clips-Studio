"""Centralized Configuration Manager.

Single source of truth for pipeline versioning, AI model defaults, thresholds,
rendering constants, and channel branding defaults.
"""

import json
from pathlib import Path
from typing import Any

CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "ai_config.json"

DEFAULT_CONFIG: dict[str, Any] = {
    "pipelineVersion": "2.4.0",
    "schemaVersion": "1.1",
    "crop": {
        "smoothingAlpha": 0.35,
        "targetRatio": "9:16",
        "shortsWidth": 1080,
        "shortsHeight": 1920,
        "primaryPersonAreaRatio": 0.03,
        "multiPersonRatioThreshold": 0.25,
        "faceConfidenceThreshold": 0.40,
    },
    "render": {
        "preset": "veryfast",
        "crf": 23,
        "audioCodec": "aac",
        "videoCodec": "libx264",
        "blurStrength": 25,
        "musicVolumeDefault": 20,
    },
    "branding": {
        "channelName": "ClipForge World",
        "brandHashtags": ["#clipforgeworld", "#clipforge"],
        "maxHashtags": 16,
    },
    "ollama": {
        "baseUrl": "http://localhost:11434",
        "model": "llama3:8b",
        "temperature": 0.7,
        "timeoutSeconds": 5.0,
    },
}


def load_config() -> dict[str, Any]:
    """Load configuration from ai_config.json merged with default constants."""
    if not CONFIG_PATH.exists():
        return DEFAULT_CONFIG

    try:
        raw = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        merged = {**DEFAULT_CONFIG}
        for key, value in raw.items():
            if isinstance(value, dict) and key in merged and isinstance(merged[key], dict):
                merged[key] = {**merged[key], **value}
            else:
                merged[key] = value
        return merged
    except Exception:
        return DEFAULT_CONFIG


def get_pipeline_version() -> str:
    """Get current pipeline version string."""
    return load_config().get("pipelineVersion", "2.4.0")
