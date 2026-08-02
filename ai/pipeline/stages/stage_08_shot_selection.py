"""Editorial Shot Selection.

Determines the editorial composition of each scene within each highlight clip,
then derives a shot type from that composition.

This stage is responsible ONLY for the editorial decision.
It does NOT produce crop coordinates, camera paths, renderer modes, or transition curves.

Composition Categories:
  - single_speaker: One editorially important person dominates the frame.
  - conversation:   Two or more editorially important people are present.
  - content_only:   No editorially important person is visible (slides, text, logos, etc.).

Shot Types (derived from composition):
  - close:  Tight portrait framing on a single speaker.
  - wide:   Preserve all conversation participants.
  - medium: Comfortable content framing without aggressive zoom.
"""

import json

# --- Editorial importance thresholds ---

# A track must be present in at least this fraction of sampled frames within
# the scene to be considered sustained (rejects transient walk-throughs).
MIN_PRESENCE_RATIO = 0.35

# Median bounding box area must be at least this fraction of total frame area
# to be considered a meaningful participant (rejects tiny background people).
MIN_AREA_RATIO = 0.025

# Bounding box center must be within this horizontal range of the frame
# to avoid counting edge-clipped partial detections.
# 0.10 rejects persons whose center is in the outer 10% of the frame —
# these are typically blurred foreground/edge elements in podcast shots.
EDGE_MARGIN = 0.10

# Minimum average confidence for a track to be editorially important.
MIN_CONFIDENCE = 0.40

# Minimum duration (seconds) for a sub-segment when splitting a long scene.
MIN_SUB_SEGMENT_DURATION = 2.5

# Scenes shorter than this inherit their neighbor's shot type to prevent flicker.
SHORT_SCENE_THRESHOLD = 1.5

# A long scene may be split if the composition changes for at least this many seconds.
LONG_SCENE_SPLIT_THRESHOLD = 10.0
COMPOSITION_CHANGE_MIN_SECONDS = 3.0


def _tracks_in_scene(tracks: list[dict], start: float, end: float) -> list[dict]:
    """Return all tracks that have at least one detection within [start, end]."""
    result = []
    for track in tracks:
        detections = [
            d for d in track.get("detections", [])
            if start <= float(d["time"]) <= end
        ]
        if detections:
            result.append({
                **track,
                "_scene_detections": detections,
            })
    return result


def _is_editorially_important(
    track: dict,
    scene_sampled_frame_count: int,
    frame_w: int,
    frame_h: int,
) -> bool:
    """Determine whether a track represents an editorially important person.

    An editorially important person is someone a human editor would
    intentionally keep in the shot.
    """
    detections = track.get("_scene_detections", [])
    if not detections:
        return False

    # Sustained presence: detected in enough frames within the scene.
    if scene_sampled_frame_count > 0:
        presence_ratio = len(detections) / scene_sampled_frame_count
        if presence_ratio < MIN_PRESENCE_RATIO:
            return False

    # Minimum confidence.
    avg_conf = sum(float(d.get("confidence", 0)) for d in detections) / len(detections)
    if avg_conf < MIN_CONFIDENCE:
        return False

    # Minimum area (median bounding box area relative to frame).
    frame_area = max(1.0, frame_w * frame_h)
    areas = []
    for d in detections:
        bbox = d.get("bbox", [0, 0, 1, 1])
        areas.append(float(bbox[2]) * float(bbox[3]) / frame_area)
    areas.sort()
    median_area = areas[len(areas) // 2]
    if median_area < MIN_AREA_RATIO:
        return False

    # Edge clipping: median center_x must be within the safe horizontal range.
    centers_x = []
    for d in detections:
        bbox = d.get("bbox", [0, 0, 1, 1])
        cx = (float(bbox[0]) + float(bbox[2]) / 2.0) / max(1.0, frame_w)
        centers_x.append(cx)
    centers_x.sort()
    median_cx = centers_x[len(centers_x) // 2]
    if median_cx < EDGE_MARGIN or median_cx > (1.0 - EDGE_MARGIN):
        return False

    return True


def _classify_composition(important_count: int) -> tuple[str, str]:
    """Classify the editorial composition and derive the shot type.

    Returns (composition, shot_type).
    """
    if important_count == 0:
        return "content_only", "wide"
    elif important_count == 1:
        return "single_speaker", "close"
    else:
        return "conversation", "wide"


def _reason_text(composition: str, important_count: int) -> str:
    """Human-readable reason for the editorial decision."""
    if composition == "content_only":
        return "no_important_person_visible"
    elif composition == "single_speaker":
        return "single_speaker_dominates_frame"
    else:
        return f"{important_count}_conversation_participants"


def _count_sampled_frames_in_range(
    all_detections: list[dict],
    start: float,
    end: float,
) -> int:
    """Count how many sampled frames (from face_detections.json) fall in [start, end]."""
    count = 0
    for d in all_detections:
        t = float(d.get("time", 0))
        if start <= t <= end:
            count += 1
    return count


def _is_truly_content_only(
    all_tracks: list[dict],
    scene_start: float,
    scene_end: float,
) -> bool:
    """High-Confidence Content-Only Detection Algorithm.

    Distinguishes genuine content-only scenes (slides, websites, products, logos,
    graphics) from temporary vision detector dropouts or occlusions on human speakers.

    Rules:
      1. Spanning track check: If a person track is active before scene_start AND
         after scene_end, the speaker is present continuously across a temporary
         detector dip — do NOT switch to content_only.
      2. Presence check: If any person track has >=2 detections inside the scene,
         the scene contains a human subject.
      3. Short scene guard: Brief gaps (< 1.5s) inherit surrounding speaker framing.
    """
    duration = scene_end - scene_start

    # Rule 1: Spanning track check (prevents dropout flipping)
    for track in all_tracks:
        dets = track.get("detections", [])
        has_before = any(float(d["time"]) < scene_start for d in dets)
        has_after = any(float(d["time"]) > scene_end for d in dets)
        has_inside = any(scene_start <= float(d["time"]) <= scene_end for d in dets)

        if (has_before and has_after) or (has_before and has_inside) or (has_inside and has_after):
            return False

    # Rule 2: Substantial presence inside scene
    for track in all_tracks:
        dets = [d for d in track.get("detections", []) if scene_start <= float(d["time"]) <= scene_end]
        if len(dets) >= 2:
            return False

    # Rule 3: Short scene guard — brief gaps (< 1.5s) inherit neighbor framing
    if duration < 1.5:
        return False

    return True


def _classify_scene(
    tracks: list[dict],
    all_detections: list[dict],
    scene_start: float,
    scene_end: float,
    frame_w: int,
    frame_h: int,
    identity_data: dict | None = None,
) -> tuple[str, str, int]:
    """Classify a single scene's editorial composition.

    Returns (composition, shot_type, important_count).
    """
    scene_tracks = _tracks_in_scene(tracks, scene_start, scene_end)
    sampled_frames = _count_sampled_frames_in_range(all_detections, scene_start, scene_end)

    important_tracks = [
        t for t in scene_tracks
        if _is_editorially_important(t, sampled_frames, frame_w, frame_h)
    ]
    important_tracks = _deduplicate_overlapping_tracks(important_tracks, scene_start, scene_end, frame_w)

    important_count = len(important_tracks)
    if important_count == 0:
        if _is_truly_content_only(tracks, scene_start, scene_end):
            composition, shot_type = "content_only", "wide"
        else:
            # Temporary detector dropout: preserve temporal continuity by treating as single speaker
            composition, shot_type = "single_speaker", "close"
            important_count = 1
    else:
        composition, shot_type = _classify_composition(important_count)

    return composition, shot_type, important_count


def _deduplicate_overlapping_tracks(
    tracks: list[dict], start: float, end: float, frame_w: int
) -> list[dict]:
    """Merge spatially overlapping person tracks in the scene.
    
    If two tracks share high horizontal spatial overlap (center_x distance < 18%
    of frame width), they represent tracker re-ID splits or candidate box duplicates
    of the same physical speaker, not two distinct conversation participants.
    """
    if len(tracks) <= 1:
        return tracks

    unique_tracks = []
    for track in tracks:
        dets = [d for d in track.get("detections", []) if start <= float(d.get("time", 0)) <= end]
        if not dets:
            continue
        cx = sum((float(d["bbox"][0]) + float(d["bbox"][2]) / 2.0) for d in dets) / len(dets)
        
        is_duplicate = False
        for existing in unique_tracks:
            ex_dets = [d for d in existing.get("detections", []) if start <= float(d.get("time", 0)) <= end]
            if not ex_dets:
                continue
            ex_cx = sum((float(d["bbox"][0]) + float(d["bbox"][2]) / 2.0) for d in ex_dets) / len(ex_dets)
            if abs(cx - ex_cx) < 0.18 * frame_w:
                is_duplicate = True
                break

        if not is_duplicate:
            unique_tracks.append(track)

    return unique_tracks


def _identity_count_in_scene(identity_data: dict, start: float, end: float) -> int:
    """Count distinct sustained face identities in a time range (supplementary signal)."""
    count = 0
    for scene in identity_data.get("scenes", []):
        scene_start = float(scene.get("start", 0))
        scene_end = float(scene.get("end", 0))
        # Check overlap
        if scene_end < start or scene_start > end:
            continue
        for identity in scene.get("identities", []):
            det_count = identity.get("detectionCount", 0)
            # Require ≥5 detections for an identity to count as sustained.
            # Lower thresholds (e.g., 3) let spurious YuNet splits through.
            if det_count >= 5:
                time_range = identity.get("timeRange", [0, 0])
                if float(time_range[0]) <= end and float(time_range[1]) >= start:
                    count += 1
    return count


def _stabilize_short_scenes(segments: list[dict]) -> list[dict]:
    """Short scenes (< SHORT_SCENE_THRESHOLD) inherit their longest neighbor's shot type."""
    if len(segments) <= 1:
        return segments

    for i, seg in enumerate(segments):
        duration = seg["end"] - seg["start"]
        if duration >= SHORT_SCENE_THRESHOLD:
            continue

        # Find longest adjacent neighbor
        prev_dur = (segments[i - 1]["end"] - segments[i - 1]["start"]) if i > 0 else 0
        next_dur = (segments[i + 1]["end"] - segments[i + 1]["start"]) if i < len(segments) - 1 else 0

        if prev_dur >= next_dur and prev_dur > 0:
            seg["shotType"] = segments[i - 1]["shotType"]
            seg["composition"] = segments[i - 1]["composition"]
            seg["reason"] = f"inherited_from_previous_neighbor (duration={duration:.1f}s)"
        elif next_dur > 0:
            seg["shotType"] = segments[i + 1]["shotType"]
            seg["composition"] = segments[i + 1]["composition"]
            seg["reason"] = f"inherited_from_next_neighbor (duration={duration:.1f}s)"

    return segments


def _merge_adjacent(segments: list[dict]) -> list[dict]:
    """Merge adjacent segments with identical shot types."""
    if not segments:
        return []

    merged = [segments[0].copy()]
    for seg in segments[1:]:
        if seg["shotType"] == merged[-1]["shotType"]:
            merged[-1]["end"] = seg["end"]
            # Keep the higher important person count
            merged[-1]["importantPersonCount"] = max(
                merged[-1]["importantPersonCount"],
                seg["importantPersonCount"],
            )
        else:
            merged.append(seg.copy())

    return merged


def run(context):
    """Produce shot_plan.json with editorial shot type per scene per highlight clip."""

    # Load inputs
    metadata = json.loads(
        (context["temp_dir"] / "video_metadata.json").read_text(encoding="utf-8")
    )
    highlights = json.loads(
        (context["temp_dir"] / "highlights.json").read_text(encoding="utf-8")
    )["highlights"]
    track_data = json.loads(
        (context["temp_dir"] / "face_tracks.json").read_text(encoding="utf-8")
    )
    detection_data = json.loads(
        (context["temp_dir"] / "face_detections.json").read_text(encoding="utf-8")
    )
    scene_cuts_path = context["temp_dir"] / "scene_cuts.json"
    scenes = []
    if scene_cuts_path.exists():
        scenes = json.loads(
            scene_cuts_path.read_text(encoding="utf-8")
        ).get("scenes", [])

    identity_path = context["temp_dir"] / "subject_identities.json"
    identity_data = None
    if identity_path.exists():
        identity_data = json.loads(identity_path.read_text(encoding="utf-8"))

    frame_w = int(metadata["width"])
    frame_h = int(metadata["height"])
    tracks = track_data.get("tracks", [])
    all_detections = detection_data.get("detections", [])

    clip_plans = []

    for highlight in sorted(highlights, key=lambda h: float(h["start"])):
        clip_start = float(highlight["start"])
        clip_end = float(highlight["end"])

        # Gather scenes that overlap with this clip
        clip_scenes = []
        for scene in scenes:
            s_start = max(clip_start, float(scene.get("start", 0)))
            s_end = min(clip_end, float(scene.get("end", clip_end)))
            if s_end - s_start > 0.05:
                clip_scenes.append({
                    "start": s_start,
                    "end": s_end,
                    "index": scene.get("index", 0),
                })

        if not clip_scenes:
            clip_scenes = [{"start": clip_start, "end": clip_end, "index": 0}]

        # Classify each scene
        raw_segments = []
        for scene in clip_scenes:
            composition, shot_type, important_count = _classify_scene(
                tracks, all_detections,
                scene["start"], scene["end"],
                frame_w, frame_h,
                identity_data,
            )
            raw_segments.append({
                "start": round(scene["start"], 3),
                "end": round(scene["end"], 3),
                "shotType": shot_type,
                "composition": composition,
                "importantPersonCount": important_count,
                "reason": _reason_text(composition, important_count),
            })

        # Temporal stability: stabilize short scenes, then merge adjacent
        raw_segments = _stabilize_short_scenes(raw_segments)
        segments = _merge_adjacent(raw_segments)

        # Ensure full clip coverage
        if segments:
            segments[0]["start"] = round(clip_start, 3)
            segments[-1]["end"] = round(clip_end, 3)
        else:
            segments = [{
                "start": round(clip_start, 3),
                "end": round(clip_end, 3),
                "shotType": "wide",
                "composition": "content_only",
                "importantPersonCount": 0,
                "reason": "no_detections_available",
            }]

        clip_plans.append({
            "clipId": highlight.get("id") or highlight.get("clipId") or highlight.get("clip_id", ""),
            "start": round(clip_start, 3),
            "end": round(clip_end, 3),
            "segments": segments,
        })

    (context["temp_dir"] / "shot_plan.json").write_text(
        json.dumps({
            "method": "editorial-shot-selection",
            "schemaVersion": "1.0",
            "editorialPrinciple": (
                "Classify the editorial composition of the scene first, "
                "then derive the shot type. Person count is the primary signal, "
                "but editorial composition takes precedence in edge cases."
            ),
            "clips": clip_plans,
        }, indent=2),
        encoding="utf-8",
    )
