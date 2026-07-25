import json
import math
import re
import warnings

warnings.filterwarnings(
    "ignore",
    message=r"urllib3 .* doesn't match a supported version!",
)

import requests
from highlights.ollama_highlights import OllamaUnavailable, get_highlights


HOOK_WORDS = {
    "best",
    "big",
    "breakthrough",
    "but",
    "change",
    "secret",
    "simple",
    "start",
    "stop",
    "why",
    "how",
    "what",
    "because",
    "never",
    "always",
    "today",
    "mistake",
    "important",
    "remember",
    # Added — stronger viral signal words
    "truth",
    "honest",
    "actually",
    "shocking",
    "nobody",
    "everybody",
    "wrong",
    "finally",
    "reveal",
    "warning",
    "proof",
    "real",
    "failed",
    "success",
}


def _clean_text(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _segment_candidates(
    segments: list[dict],
    min_duration: float,
    max_duration: float,
) -> list[dict]:
    candidates = []
    total_segments = len(segments)

    for start_index in range(total_segments):
        start = float(segments[start_index]["start"])
        text_parts = []
        word_count = 0

        for end_index in range(start_index, total_segments):
            end = float(segments[end_index]["end"])
            duration = end - start
            if duration > max_duration and end_index > start_index:
                break

            segment_text = _clean_text(segments[end_index].get("text", ""))
            text_parts.append(segment_text)
            word_count += (
                len(segments[end_index].get("words", []))
                or len(segment_text.split())
            )

            if duration < min_duration:
                continue

            text = _clean_text(" ".join(text_parts))
            if not text:
                continue

            candidates.append({
                "start": start,
                "end": end,
                "duration": duration,
                "text": text,
                "wordCount": word_count,
            })

    return candidates


def _score_candidate(candidate: dict, video_duration: float) -> float:
    text = candidate["text"]
    words = re.findall(r"[a-zA-Z']+", text.lower())
    hook_hits = sum(1 for word in words if word in HOOK_WORDS)
    speech_density = candidate["wordCount"] / max(candidate["duration"], 1)
    duration_score = 1 - abs(candidate["duration"] - 30) / 30
    early_bonus = 1 - min(candidate["start"] / max(video_duration, 1), 1)
    punctuation_bonus = 0.1 if re.search(r"[?!]", text) else 0

    raw = (
        hook_hits * 8
        + min(speech_density, 4) * 12
        + max(duration_score, 0) * 25
        + early_bonus * 10
        + punctuation_bonus * 100
    )
    return max(1, min(100, round(raw, 2)))


def _overlaps(candidate: dict, selected: list[dict]) -> bool:
    for item in selected:
        overlap = min(candidate["end"], item["end"]) - max(
            candidate["start"], item["start"]
        )
        if overlap > min(candidate["duration"], item["duration"]) * 0.35:
            return True
    return False


def _load_speech_segments(context) -> list[dict]:
    speech_path = context["temp_dir"] / "speech_timestamps.json"
    if not speech_path.exists():
        return []
    return json.loads(speech_path.read_text(encoding="utf-8")).get("segments", [])


def _load_scenes(context) -> list[dict]:
    scenes_path = context["temp_dir"] / "scene_cuts.json"
    if not scenes_path.exists():
        return []
    return json.loads(scenes_path.read_text(encoding="utf-8")).get("scenes", [])


def _snap_to_speech(
    start: float,
    end: float,
    speech_segments: list[dict],
    max_duration: float,
) -> tuple[float, float]:
    if not speech_segments:
        return start, end

    overlapping = [
        segment
        for segment in speech_segments
        if float(segment["end"]) > start and float(segment["start"]) < end
    ]
    if not overlapping:
        nearest = min(
            speech_segments,
            key=lambda segment: min(
                abs(float(segment["start"]) - start),
                abs(float(segment["end"]) - end),
            ),
        )
        snapped_start = float(nearest["start"])
        snapped_end = min(float(nearest["end"]), snapped_start + max_duration)
        return snapped_start, snapped_end

    snapped_start = min(float(segment["start"]) for segment in overlapping)
    snapped_end = max(float(segment["end"]) for segment in overlapping)
    snapped_start = max(snapped_start, start - 0.25)
    snapped_end = min(snapped_end, end + 0.25)
    if snapped_end - snapped_start > max_duration:
        snapped_end = snapped_start + max_duration
    return snapped_start, snapped_end


def _snap_to_scene(
    start: float,
    end: float,
    scenes: list[dict],
    max_duration: float,
) -> tuple[float, float]:
    if not scenes:
        return start, end

    matching = [
        scene
        for scene in scenes
        if float(scene["end"]) > start and float(scene["start"]) < end
    ]
    if not matching:
        return start, end

    scene_start = min(float(scene["start"]) for scene in matching)
    scene_end = max(float(scene["end"]) for scene in matching)

    snapped_start = start
    snapped_end = end
    if abs(start - scene_start) <= 1.25:
        snapped_start = scene_start
    if abs(end - scene_end) <= 1.25:
        snapped_end = scene_end

    if snapped_end - snapped_start > max_duration:
        snapped_end = snapped_start + max_duration
    if snapped_end <= snapped_start:
        return start, end
    return snapped_start, snapped_end


def _fallback_from_words(
    words: list[dict],
    clip_count: int,
    max_duration: float,
) -> list[dict]:
    if not words:
        return []

    video_end = float(words[-1]["end"])
    window = min(max_duration, max(video_end / clip_count, 5))
    highlights = []
    for index in range(clip_count):
        start = index * window
        if start >= video_end:
            break
        end = min(start + window, video_end)
        window_words = [
            word["word"]
            for word in words
            if float(word["start"]) >= start and float(word["end"]) <= end
        ]
        text = _clean_text(" ".join(window_words))
        highlights.append({
            "start": round(start, 3),
            "end": round(end, 3),
            "duration": round(end - start, 3),
            "text": text,
            "score": max(1, 60 - index),
            "source": "fallback",
        })
    return highlights


def _expand_to_min_duration(
    item: dict,
    segments: list[dict],
    words: list[dict],
    min_duration: float,
    max_duration: float,
    video_duration: float,
) -> dict:
    target_duration = min(min_duration, max_duration, video_duration)
    start = float(item["start"])
    end = float(item["end"])
    if end - start >= target_duration:
        return item

    overlapping_indexes = [
        index
        for index, segment in enumerate(segments)
        if float(segment["end"]) > start and float(segment["start"]) < end
    ]
    if not overlapping_indexes and segments:
        nearest_index = min(
            range(len(segments)),
            key=lambda index: min(
                abs(float(segments[index]["start"]) - start),
                abs(float(segments[index]["end"]) - end),
            ),
        )
        overlapping_indexes = [nearest_index]

    if overlapping_indexes:
        left = min(overlapping_indexes)
        right = max(overlapping_indexes)
        start = min(start, float(segments[left]["start"]))
        end = max(end, float(segments[right]["end"]))

        while end - start < target_duration and (
            left > 0 or right < len(segments) - 1
        ):
            left_gap = (
                start - float(segments[left - 1]["end"]) if left > 0 else float("inf")
            )
            right_gap = (
                float(segments[right + 1]["start"]) - end
                if right < len(segments) - 1
                else float("inf")
            )
            if left_gap <= right_gap and left > 0:
                left -= 1
                start = float(segments[left]["start"])
            elif right < len(segments) - 1:
                right += 1
                end = float(segments[right]["end"])
            else:
                break

    if end - start < target_duration:
        missing = target_duration - (end - start)
        start = max(0.0, start - missing / 2)
        end = min(video_duration, end + missing / 2)
        if end - start < target_duration:
            if start <= 0:
                end = min(video_duration, target_duration)
            elif end >= video_duration:
                start = max(0.0, video_duration - target_duration)

    if end - start > max_duration:
        end = start + max_duration

    expanded = {**item, "start": start, "end": end, "duration": end - start}
    expanded_text = _text_between(words, start, end)
    if expanded_text:
        expanded["text"] = expanded_text
    return expanded


def _text_between(words: list[dict], start: float, end: float) -> str:
    return _clean_text(
        " ".join(
            str(word["word"]).strip()
            for word in words
            if float(word["end"]) > start and float(word["start"]) < end
        )
    )


def _from_ollama(
    transcript: dict,
    words: list[dict],
    clip_count: int,
    min_duration: float,
    max_duration: float,
    settings: dict,
    coverage_mode: str = "best",
    preferred_duration: str = "auto",
) -> tuple[list[dict], str]:
    base_url = settings.get("ollamaUrl", "http://localhost:11434")
    model = settings.get("ollamaModel", "llama3:8b")

    # ── Pass video_duration so ollama_highlights can validate timestamps ──
    video_duration = float(transcript.get("duration") or 0)

    raw_highlights = get_highlights(
        transcript=transcript,
        max_clips=clip_count,
        min_duration=min_duration,
        max_duration=max_duration,
        base_url=base_url,
        model=model,
        coverage_mode=coverage_mode,
        preferred_duration=preferred_duration,
        video_duration=video_duration,
    )

    transcript_duration = float(transcript.get("duration") or 0)
    selected = []

    for item in raw_highlights:
        start = max(0.0, float(item["start"]))
        end = min(transcript_duration, float(item["end"])) if transcript_duration else float(item["end"])
        if end <= start:
            continue
        if end - start > max_duration:
            end = start + max_duration

        text = _text_between(words, start, end)
        if not text:
            text = _clean_text(str(item.get("hook", "")))

        selected.append({
            "start": start,
            "end": end,
            "duration": end - start,
            "text": text,
            "score": max(1, min(100, int(item.get("score", 70)))),
            "hook": _clean_text(str(item.get("hook", text[:120]))),
            "reason": _clean_text(
                str(item.get("reason", "Selected by local Ollama analysis."))
            ),
            "type": item.get("type", "story_hook"),
            "source": item.get("source", "ollama"),
            "coverage_warning": item.get("coverage_warning", False),
            "model": model,
        })
        if len(selected) >= clip_count:
            break

    if not selected:
        raise ValueError("Ollama returned no usable highlights")
    return selected, model


def _deterministic_highlights(
    segments: list[dict],
    words: list[dict],
    clip_count: int,
    min_duration: float,
    max_duration: float,
    video_duration: float,
    coverage_mode: str = "best",
) -> list[dict]:
    candidates = _segment_candidates(segments, min_duration, max_duration)
    for candidate in candidates:
        candidate["score"] = _score_candidate(candidate, video_duration)
        candidate["reason"] = (
            "Selected by transcript density, hook words, duration fit, and position."
        )
        candidate["source"] = "deterministic"
        candidate["type"] = "story_hook"

    if coverage_mode == "entire" and video_duration > 0:
        interval = 300.0 if video_duration >= 600.0 else 120.0
        zones_candidates = {}
        
        for candidate in candidates:
            zone_idx = int(candidate["start"] // interval)
            if zone_idx not in zones_candidates:
                zones_candidates[zone_idx] = []
            zones_candidates[zone_idx].append(candidate)
            
        selected = []
        for z in zones_candidates:
            zones_candidates[z] = sorted(zones_candidates[z], key=lambda c: c["score"], reverse=True)
            
        zone_keys = sorted(list(zones_candidates.keys()))
        
        # Pass 1: Select top candidate from each zone
        for z in zone_keys:
            for candidate in zones_candidates[z]:
                if not _overlaps(candidate, selected):
                    selected.append(candidate)
                    break
            if len(selected) >= clip_count:
                break
                
        # Pass 2: Fill up remaining clip_count using ranked list of all candidates
        if len(selected) < clip_count:
            ranked_all = sorted(candidates, key=lambda c: c["score"], reverse=True)
            for candidate in ranked_all:
                if not _overlaps(candidate, selected):
                    selected.append(candidate)
                if len(selected) >= clip_count:
                    break
    else:
        ranked = sorted(candidates, key=lambda item: item["score"], reverse=True)
        selected = []
        for candidate in ranked:
            if not _overlaps(candidate, selected):
                selected.append(candidate)
            if len(selected) >= clip_count:
                break

    if len(selected) < clip_count:
        needed = clip_count - len(selected)
        selected.extend(
            _fallback_from_words(words, needed, max_duration)
        )
    return selected


def _generate_viral_hook(clip_text: str, clip_index: int, settings: dict) -> str:
    """
    Generate a single, highly engaging, scroll-stopping title hook using local Ollama.
    Falls back to a curated list of generic curiosity-inducing viral hooks if offline or errors.
    """
    base_url = settings.get("ollamaUrl", "http://localhost:11434").rstrip("/")
    model = settings.get("ollamaModel", "llama3:8b")
    
    fallback_hooks = [
        "This Changed Everything...",
        "The Secret Most People Miss",
        "Don't Make This Mistake!",
        "Watch What Happens Next...",
        "Nobody Expected This...",
        "The Truth They Hid From You",
        "This One Trick Works...",
        "What They Won't Tell You",
    ]
    fallback = fallback_hooks[clip_index % len(fallback_hooks)]

    if not clip_text or not clip_text.strip():
        return fallback

    try:
        response = requests.get(f"{base_url}/api/tags", timeout=1.5)
        if not response.ok:
            return fallback

        prompt = (
            "You are an expert social media editor.\n"
            "Given the following transcript of a video clip, generate a single, highly engaging, scroll-stopping title hook (3 to 8 words) that creates curiosity and makes people want to watch the video.\n\n"
            "Examples of good hooks:\n"
            "- \"Nobody Expected This...\"\n"
            "- \"The Secret Most People Miss\"\n"
            "- \"This Changed Everything\"\n"
            "- \"Don't Make This Mistake\"\n"
            "- \"Watch What Happens Next\"\n\n"
            "Do not repeat the first spoken sentence of the transcript.\n"
            "Return ONLY the hook text (plain text, no quotes, no explanation, no markdown, 8 words max).\n\n"
            f"Transcript:\n\"{clip_text}\""
        )

        res = requests.post(
            f"{base_url}/api/generate",
            json={
                "model": model,
                "prompt": prompt,
                "stream": False,
                "options": {
                    "temperature": 0.7,
                    "num_predict": 15
                }
            },
            timeout=5.0
        )
        if res.ok:
            hook = res.json().get("response", "").strip()
            hook = re.sub(r'^["\'`\-*]+|["\'`\-*]+$', '', hook).strip()
            if len(hook.split()) <= 10 and len(hook) > 5:
                return hook
    except Exception:
        pass

    return fallback


def _expand_to_boundaries(
    start: float,
    end: float,
    words: list[dict],
    video_dur: float,
) -> tuple[float, float]:
    if not words:
        return start, end

    # Find the index of the word closest to start
    start_idx = 0
    min_start_diff = float("inf")
    for idx, w in enumerate(words):
        diff = abs(w["start"] - start)
        if diff < min_start_diff:
            min_start_diff = diff
            start_idx = idx

    # Search backward for start boundary (max search window of 15 seconds)
    curr_start_idx = start_idx
    expanded_start = start
    while curr_start_idx > 0:
        prev_w = words[curr_start_idx - 1]
        curr_w = words[curr_start_idx]
        word_text = str(prev_w.get("word", "")).strip()
        
        is_boundary = (
            word_text.endswith((".", "?", "!")) 
            or (curr_w["start"] - prev_w["end"] > 1.2)
        )
        if is_boundary:
            expanded_start = curr_w["start"]
            break
        
        if start - prev_w["start"] > 15.0:
            expanded_start = curr_w["start"]
            break
        curr_start_idx -= 1
    else:
        expanded_start = words[0]["start"]

    # Find the index of the word closest to end
    end_idx = len(words) - 1
    min_end_diff = float("inf")
    for idx, w in enumerate(words):
        diff = abs(w["end"] - end)
        if diff < min_end_diff:
            min_end_diff = diff
            end_idx = idx

    # Search forward for end boundary (max search window of 20 seconds)
    curr_end_idx = end_idx
    expanded_end = end
    while curr_end_idx < len(words) - 1:
        curr_w = words[curr_end_idx]
        next_w = words[curr_end_idx + 1]
        word_text = str(curr_w.get("word", "")).strip()
        
        is_boundary = (
            word_text.endswith((".", "?", "!"))
            or (next_w["start"] - curr_w["end"] > 1.2)
        )
        if is_boundary:
            expanded_end = curr_w["end"]
            break
        
        if curr_w["end"] - end > 20.0:
            expanded_end = curr_w["end"]
            break
        curr_end_idx += 1
    else:
        expanded_end = words[-1]["end"]

    expanded_start = max(0.0, expanded_start)
    expanded_end = min(video_dur, expanded_end)
    
    if expanded_end <= expanded_start:
        return start, end
    return expanded_start, expanded_end


def _evaluate_clip_quality(
    start: float,
    end: float,
    words: list[dict],
    min_duration: float,
    max_duration: float,
    base_score: int,
) -> tuple[int, list[str]]:
    reasons = []
    bonus = 0
    
    # 1. Punctuation checks
    start_word = None
    prev_word = None
    for idx, w in enumerate(words):
        if float(w["start"]) >= start:
            start_word = w
            if idx > 0:
                prev_word = words[idx - 1]
            break
            
    if start <= 0.2:
        bonus += 10
        reasons.append("Starts at video beginning")
    elif prev_word and str(prev_word.get("word", "")).strip().endswith((".", "?", "!")):
        bonus += 10
        reasons.append("Starts immediately after a completed sentence")
    elif prev_word and (start - float(prev_word["end"]) > 1.0):
        bonus += 5
        reasons.append("Starts after a natural conversational pause")

    end_word = None
    for w in reversed(words):
        if float(w["end"]) <= end:
            end_word = w
            break
            
    if end_word and str(end_word.get("word", "")).strip().endswith((".", "?", "!")):
        bonus += 15
        reasons.append("Ends cleanly with sentence completion punctuation")
    elif end_word and str(end_word.get("word", "")).strip().endswith(","):
        bonus += 5
        reasons.append("Ends at a natural clause comma pause")
        
    duration = end - start
    if min_duration <= duration <= max_duration:
        bonus += 25
        reasons.append("Duration fits within the preferred timing window")
    else:
        bonus -= 15
        reasons.append("Duration lies outside preferred timing boundaries")

    final_score = min(100, max(1, base_score + bonus))
    return final_score, reasons


def _deduplicate_and_merge_highlights(highlights: list[dict], max_duration: float) -> list[dict]:
    sorted_h = sorted(highlights, key=lambda x: x["start"])
    merged = []
    
    for h in sorted_h:
        if not merged:
            merged.append(h)
            continue
        
        last = merged[-1]
        overlap = min(h["end"], last["end"]) - max(h["start"], last["start"])
        min_dur = min(h["end"] - h["start"], last["end"] - last["start"])
        
        if overlap > min_dur * 0.30:
            combined_start = min(h["start"], last["start"])
            combined_end = max(h["end"], last["end"])
            combined_dur = combined_end - combined_start
            
            if combined_dur <= max_duration:
                last["start"] = combined_start
                last["end"] = combined_end
                last["duration"] = combined_dur
                last["score"] = max(last["score"], h["score"])
                last["reason"] = f"Merged overlapping moments: {last.get('reason', '')} | {h.get('reason', '')}"
                last["text"] = last.get("text", "") + " ... " + h.get("text", "")
            else:
                if h["score"] > last["score"]:
                    merged[-1] = h
        else:
            merged.append(h)
            
    return merged


def run(context):
    settings = context["settings"]
    
    # 1. Resolve configuration parameters
    clip_generation_mode = settings.get("clipGenerationMode", "auto")
    coverage_mode = settings.get("coverageMode", "best")
    preferred_duration = settings.get("preferredDuration", "auto")

    transcript_path = context["temp_dir"] / "transcript.json"
    transcript = json.loads(transcript_path.read_text(encoding="utf-8"))
    segments = transcript.get("segments", [])
    words = transcript.get("words", [])
    video_duration = float(transcript.get("duration") or 0)
    speech_segments = _load_speech_segments(context)
    scenes = _load_scenes(context)

    # Map preferred duration to min/max duration
    if preferred_duration == "short":
        min_duration = 15.0
        max_duration = 30.0
    elif preferred_duration == "medium":
        min_duration = 30.0
        max_duration = 60.0
    elif preferred_duration == "long":
        min_duration = 60.0
        max_duration = 90.0
    else: # auto
        min_duration = 15.0
        max_duration = 90.0

    # Determine maximum clips limit
    if clip_generation_mode == "manual":
        max_clips = max(1, min(20, int(settings.get("clipCount", 5))))
    else: # auto mode: dynamic limit based on duration (approx 1 clip per 3 mins)
        max_clips = max(5, min(15, int(math.ceil(video_duration / 180))))

    # ── PASS 1: Identify Candidate Highlights ──────────────────────────────
    fallback_reason = None
    try:
        selected, _model = _from_ollama(
            transcript, words, max_clips, min_duration, max_duration, settings,
            coverage_mode=coverage_mode, preferred_duration=preferred_duration
        )
    except (
        OllamaUnavailable,
        requests.RequestException,
        ValueError,
        KeyError,
        TypeError,
        json.JSONDecodeError,
    ) as error:
        selected = _deterministic_highlights(
            segments, words, max_clips, min_duration, max_duration, video_duration,
            coverage_mode=coverage_mode
        )
        fallback_reason = str(error)

    # ── PASS 2: Semantic Thought & Sentence Expansion ─────────────────────
    expanded_candidates = []
    for item in selected:
        start = float(item["start"])
        end = float(item["end"])
        
        start, end = _snap_to_speech(start, end, speech_segments, max_duration)
        start, end = _expand_to_boundaries(start, end, words, video_duration)
        start, end = _snap_to_scene(start, end, scenes, max_duration)
        
        if end - start < min_duration:
            expanded = _expand_to_min_duration(
                {**item, "start": start, "end": end},
                segments,
                words,
                min_duration,
                max_duration,
                video_duration,
            )
            start = float(expanded["start"])
            end = float(expanded["end"])

        text = _text_between(words, start, end)
        if not text:
            text = item.get("text", "")

        expanded_candidates.append({
            "start": start,
            "end": end,
            "duration": end - start,
            "text": text,
            "base_score": int(item.get("score", 70)),
            "reason": item.get("reason", "Selected by transcript analysis."),
            "type": item.get("type", "story_hook"),
            "source": item.get("source", "deterministic"),
            "model": item.get("model"),
        })

    # ── PASS 3: Clip Quality Validation & Deduplication ───────────────────
    validated_candidates = []
    for item in expanded_candidates:
        q_score, q_reasons = _evaluate_clip_quality(
            item["start"],
            item["end"],
            words,
            min_duration,
            max_duration,
            item["base_score"],
        )
        item["score"] = q_score
        item["quality_checklist"] = q_reasons
        
        # Enforce quality threshold: reject if score < 80, unless it's the only clip
        if q_score >= 80 or len(expanded_candidates) == 1:
            validated_candidates.append(item)

    if not validated_candidates and expanded_candidates:
        best_candidate = max(expanded_candidates, key=lambda x: x.get("score", 0))
        validated_candidates.append(best_candidate)

    final_candidates = _deduplicate_and_merge_highlights(validated_candidates, max_duration)

    # ── PASS 4: Finalize and Export Timestamps ────────────────────────────
    highlights = []
    final_candidates = sorted(final_candidates, key=lambda item: item["start"])

    for index, item in enumerate(final_candidates):
        text = _clean_text(item.get("text", ""))
        hook = _generate_viral_hook(text, index, settings)
        
        highlights.append({
            "id": f"clip_{index + 1:02d}",
            "start": round(item["start"], 3),
            "end": round(item["end"], 3),
            "duration": round(item["duration"], 3),
            "score": item["score"],
            "hook": hook,
            "text": text,
            "reason": item["reason"],
            "type": item["type"],
            "source": item["source"],
            "model": item["model"],
            "minDuration": min_duration,
            "quality_checklist": item.get("quality_checklist", []),
        })

    if not highlights:
        raise RuntimeError("No transcript highlights could be generated under quality thresholds.")

    # ── Write highlights.json ─────────────────────────────────────────────
    (context["temp_dir"] / "highlights.json").write_text(
        json.dumps(
            {
                "method": "ollama" if fallback_reason is None else "deterministic-fallback",
                "fallbackReason": fallback_reason,
                "clipCount": len(highlights),
                "highlights": highlights,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
