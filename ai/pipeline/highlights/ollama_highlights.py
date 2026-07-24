import json
import re
import warnings
from typing import Any

warnings.filterwarnings(
    "ignore",
    message=r"urllib3 .* doesn't match a supported version!",
)

import requests


class OllamaUnavailable(Exception):
    pass


# ---------------------------------------------------------------------------
# JSON helpers
# ---------------------------------------------------------------------------

def _clean_json(text: str) -> str:
    fenced = re.search(r"```(?:json)?\s*(.*?)```", text, flags=re.DOTALL)
    if fenced:
        text = fenced.group(1)
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1:
        raise ValueError("Ollama did not return a JSON object")
    return text[start:end + 1]


def _segment_text(segments: list[dict[str, Any]]) -> str:
    lines = []
    for segment in segments:
        start = float(segment["start"])
        end = float(segment["end"])
        text = str(segment.get("text", "")).strip()
        if text:
            lines.append(f"[{start:.2f}-{end:.2f}] {text}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------

def _validate_highlight(h: dict[str, Any]) -> dict[str, Any]:
    """Normalize and clamp all fields so downstream code never crashes."""
    try:
        h["score"] = max(1, min(100, int(float(h.get("score", 50)))))
    except (TypeError, ValueError):
        h["score"] = 50

    h["hook"] = str(h.get("hook", ""))[:120].strip() or "Highlight moment"
    h["reason"] = str(h.get("reason", ""))[:300].strip() or "Selected highlight"

    valid_types = {
        "story_hook", "shocking_stat", "emotional_peak", "advice_bomb",
        "controversy", "question_hook", "transformation", "behind_the_scenes",
    }
    if h.get("type") not in valid_types:
        h["type"] = "story_hook"

    return h


def _validate_timestamps(
    highlights: list[dict[str, Any]],
    video_duration: float,
) -> list[dict[str, Any]]:
    """Drop any highlight whose timestamps are outside the video or inverted."""
    valid = []
    for h in highlights:
        try:
            start = float(h["start"])
            end = float(h["end"])
        except (KeyError, TypeError, ValueError):
            continue
        if start < 0 or end > video_duration + 1.0 or start >= end:
            continue
        # Clamp end to actual duration
        h["start"] = round(start, 3)
        h["end"] = round(min(end, video_duration), 3)
        valid.append(h)
    return valid


def _overlaps(start: float, end: float, ranges: list[tuple[float, float]]) -> bool:
    return any(
        not (end <= used_start or start >= used_end)
        for used_start, used_end in ranges
    )


def _used_ranges(highlights: list[dict[str, Any]]) -> list[tuple[float, float]]:
    ranges = []
    for h in highlights:
        try:
            ranges.append((float(h["start"]), float(h["end"])))
        except (KeyError, TypeError, ValueError):
            continue
    return ranges


# ---------------------------------------------------------------------------
# Coverage check
# ---------------------------------------------------------------------------

def _check_coverage(highlights: list[dict[str, Any]], video_duration: float) -> bool:
    """Return True if highlights span at least 60% of the video."""
    if not highlights or video_duration == 0:
        return False
    earliest = min(h["start"] for h in highlights)
    latest = max(h["end"] for h in highlights)
    return (latest - earliest) / video_duration >= 0.6


# ---------------------------------------------------------------------------
# Deduplication / merge
# ---------------------------------------------------------------------------

def _deduplicate(
    highlights: list[dict[str, Any]],
    clip_count: int,
) -> list[dict[str, Any]]:
    """
    Merge two lists of highlights (original + retry).
    Keep highest-scoring non-overlapping highlights up to clip_count.
    """
    sorted_all = sorted(highlights, key=lambda x: x.get("score", 0), reverse=True)
    used: list[tuple[float, float]] = []
    selected: list[dict[str, Any]] = []

    for h in sorted_all:
        try:
            start = float(h["start"])
            end = float(h["end"])
        except (KeyError, TypeError, ValueError):
            continue
        if not _overlaps(start, end, used):
            selected.append(h)
            used.append((start, end))
        if len(selected) >= clip_count:
            break

    return selected


# ---------------------------------------------------------------------------
# Fallback highlight selector (transcript-based)
# ---------------------------------------------------------------------------

def _fallback_highlights(
    segments: list[dict[str, Any]],
    needed: int,
    existing: list[dict[str, Any]],
    min_duration: float,
    max_duration: float,
) -> list[dict[str, Any]]:
    used_ranges = _used_ranges(existing)
    candidates: list[dict[str, Any]] = []

    for i, segment in enumerate(segments):
        try:
            start = float(segment["start"])
            end = float(segment["end"])
        except (KeyError, TypeError, ValueError):
            continue

        if _overlaps(start, end, used_ranges):
            continue

        # Expand window forward until min_duration is satisfied
        j = i
        while end - start < min_duration and j + 1 < len(segments):
            j += 1
            try:
                end = float(segments[j]["end"])
            except (KeyError, TypeError, ValueError):
                break

        end = min(end, start + max_duration)

        if end - start < min_duration:
            continue
        if _overlaps(start, end, used_ranges):
            continue

        text = str(segment.get("text", "")).strip()
        candidates.append({
            "start": round(start, 3),
            "end": round(end, 3),
            "score": 50,
            "hook": text[:80] or "Additional highlight",
            "reason": "Selected by transcript fallback to satisfy requested clip count.",
            "type": "story_hook",
            "source": "fallback",
        })

    # Spread across video — sort by start time, pick evenly spaced
    candidates.sort(key=lambda x: x["start"])
    selected: list[dict[str, Any]] = []
    for candidate in candidates:
        if _overlaps(candidate["start"], candidate["end"], used_ranges):
            continue
        selected.append(candidate)
        used_ranges.append((candidate["start"], candidate["end"]))
        if len(selected) >= needed:
            break

    return selected


# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------

def _prompt(
    segments: list[dict[str, Any]],
    max_clips: int,
    min_duration: float,
    max_duration: float,
    coverage_mode: str,
    preferred_duration: str,
    video_duration: float,
) -> str:
    rules = [
        f"- CLIP COUNT: Find UP TO {max_clips} genuinely strong highlights. It is better to return fewer (e.g. 5 or 6) high-quality moments than to return low-quality or boring moments just to fill the count. Never return more than {max_clips} highlights.",
        f"- DURATION: Preferred duration is '{preferred_duration}'. Aim for segments between {min_duration:.0f} and {max_duration:.0f} seconds long.",
        "- QUALITY: Prioritize complete standalone conversations, key value-bombs, secrets, shocking details, or complete explanations. Clips must not end mid-thought.",
    ]
    if coverage_mode == "entire" and video_duration > 0:
        interval = 300.0 if video_duration >= 600.0 else 120.0
        zones = []
        start = 0.0
        while start < video_duration:
            end = min(start + interval, video_duration)
            zones.append(f"[{start:.1f}s - {end:.1f}s]")
            start += interval
        zones_str = ", ".join(zones)
        rules.append(
            f"- TIMELINE COVERAGE: The video is divided into the following zones: {zones_str}. "
            "You MUST try to select at least one highlight from each time zone so that the entire timeline is covered and later parts of the video are not ignored. Only skip a zone if it genuinely has zero engaging speech."
        )
    else:
        rules.append("- TIMELINE COVERAGE: Select the absolute best moments regardless of where they appear on the timeline.")

    rules_str = "\n".join(rules)

    return (
        "You are selecting viral short-form video moments from a transcript.\n"
        "Return only valid JSON with this exact shape:\n"
        '{"highlights":[{"start":0.0,"end":12.0,"score":85,'
        '"hook":"short hook sentence","reason":"why this moment is strong",'
        '"type":"story_hook"}]}\n\n'
        "STRICT RULES:\n"
        f"{rules_str}\n"
        "- Timestamps must come exactly from the transcript segments\n"
        "- Score is 1-100 (integer only)\n"
        "- Avoid overlap between highlights\n"
        "- type must be one of: story_hook, shocking_stat, emotional_peak, "
        "advice_bomb, controversy, question_hook, transformation, behind_the_scenes\n\n"
        "Transcript:\n"
        f"{_segment_text(segments)}"
    )


def _strict_prompt(
    segments: list[dict[str, Any]],
    max_clips: int,
    min_duration: float,
    max_duration: float,
    coverage_mode: str,
    preferred_duration: str,
    video_duration: float,
    existing: list[dict[str, Any]],
) -> str:
    already = []
    for h in existing:
        try:
            already.append(f"{float(h['start']):.2f}-{float(h['end']):.2f}")
        except (KeyError, TypeError, ValueError):
            continue
    already_str = ", ".join(already) if already else "none"

    rules = [
        f"- CLIP COUNT: Find UP TO {max_clips} highlights total. You currently have {len(existing)} highlights. Generate additional distinct highlights up to a total of {max_clips}.",
        f"- AVOID OVERLAP: Do NOT overlap with already selected ranges: {already_str}.",
        f"- DURATION: Preferred duration is '{preferred_duration}'. Aim for segments between {min_duration:.0f} and {max_duration:.0f} seconds long.",
        "- QUALITY: Pick genuinely strong standalone clips with complete thoughts.",
    ]
    if coverage_mode == "entire" and video_duration > 0:
        rules.append("- TIMELINE COVERAGE: Focus on selecting from time zones that do not have any highlights selected yet to ensure full video timeline coverage.")
    
    rules_str = "\n".join(rules)

    return (
        "You are selecting viral short-form video moments from a transcript.\n"
        "Return only valid JSON with this exact shape:\n"
        '{"highlights":[{"start":0.0,"end":12.0,"score":85,'
        '"hook":"short hook sentence","reason":"why this moment is strong",'
        '"type":"story_hook"}]}\n\n'
        "STRICT RULES:\n"
        f"{rules_str}\n"
        "- Timestamps must come exactly from the transcript segments\n"
        "- type must be one of: story_hook, shocking_stat, emotional_peak, "
        "advice_bomb, controversy, question_hook, transformation, behind_the_scenes\n\n"
        "Transcript:\n"
        f"{_segment_text(segments)}"
    )


# ---------------------------------------------------------------------------
# Ollama communication
# ---------------------------------------------------------------------------

def _is_available(base_url: str) -> bool:
    try:
        response = requests.get(f"{base_url.rstrip('/')}/api/tags", timeout=2)
        return response.ok
    except requests.RequestException:
        return False


def _parse_highlights(raw_text: str) -> list[dict[str, Any]]:
    parsed = json.loads(_clean_json(raw_text))
    highlights = parsed.get("highlights", [])
    if not isinstance(highlights, list):
        raise ValueError("Ollama response did not include a highlights array")
    return [_validate_highlight(h) for h in highlights]


def _request_highlights(
    base_url: str,
    model: str,
    prompt: str,
    temperature: float,
) -> list[dict[str, Any]]:
    response = requests.post(
        f"{base_url.rstrip('/')}/api/generate",
        json={
            "model": model,
            "prompt": prompt,
            "stream": False,
            "format": "json",
            "options": {
                "temperature": temperature,
                "num_ctx": 8192,
            },
        },
        timeout=120,
    )
    response.raise_for_status()
    raw_text = response.json().get("response", "")
    highlights = _parse_highlights(raw_text)
    for h in highlights:
        if "source" not in h:
            h["source"] = "ollama"
    return highlights


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get_highlights(
    transcript: dict[str, Any],
    max_clips: int,
    min_duration: float,
    max_duration: float,
    base_url: str,
    model: str,
    coverage_mode: str = "best",
    preferred_duration: str = "auto",
    video_duration: float = 0.0,
) -> list[dict[str, Any]]:
    """
    Return up to max_clips non-overlapping highlights from the transcript.
    """
    if not _is_available(base_url):
        raise OllamaUnavailable(
            "Ollama is not available. Falling back to transcript scoring."
        )

    segments = transcript.get("segments", [])

    # ── Step 1: First attempt ───────────────────────────────────────────────
    highlights = _request_highlights(
        base_url,
        model,
        _prompt(segments, max_clips, min_duration, max_duration, coverage_mode, preferred_duration, video_duration),
        temperature=0.2,
    )

    # ── Step 2: Retry + MERGE if too few ───────────────────────────────────
    if len(highlights) < max_clips:
        try:
            retry = _request_highlights(
                base_url,
                model,
                _strict_prompt(segments, max_clips, min_duration, max_duration, coverage_mode, preferred_duration, video_duration, highlights),
                temperature=0.4,
            )
            for h in retry:
                h["source"] = "ollama_retry"
            combined = highlights + retry
            highlights = _deduplicate(combined, max_clips)
        except Exception:
            pass

    # ── Step 3: Fallback fill if still too few ───────────────────────────────
    if len(highlights) < 1:
        fallback = _fallback_highlights(
            segments,
            1,
            highlights,
            min_duration,
            max_duration,
        )
        highlights.extend(fallback)

    # ── Step 4: Validate timestamps ─────────────────────────────────────────
    if video_duration > 0:
        highlights = _validate_timestamps(highlights, video_duration)

    # ── Step 5: Sort by score — best clip first ─────────────────────────────
    highlights.sort(key=lambda x: x.get("score", 0), reverse=True)

    # ── Step 6: Coverage check (warn only) ──────────────────────────────────
    if video_duration > 0 and not _check_coverage(highlights, video_duration):
        for h in highlights:
            h["coverage_warning"] = True

    return highlights[:max_clips]
