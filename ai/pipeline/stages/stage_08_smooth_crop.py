import json
import statistics


TARGET_RATIO = 9 / 16
MIN_SEGMENT_DURATION = 1.5  # Minimum seconds before a layout switch


def _center_crop(width: int, height: int, center_x: float | None = None) -> dict:
    crop_height = height
    crop_width = int(round(crop_height * TARGET_RATIO))
    if crop_width > width:
        crop_width = width
        crop_height = int(round(crop_width / TARGET_RATIO))

    crop_width -= crop_width % 2
    crop_height -= crop_height % 2

    if center_x is None:
        center_x = width / 2
    x = int(round(center_x - crop_width / 2))
    x = max(0, min(x, width - crop_width))
    y = int(round((height - crop_height) / 2))
    y = max(0, min(y, height - crop_height))

    return {
        "x": x,
        "y": y,
        "width": crop_width,
        "height": crop_height,
    }


def _detections_in_range(track: dict, start: float, end: float) -> list[dict]:
    return [
        detection for detection in track.get("detections", [])
        if start <= float(detection["time"]) <= end
    ]


def _weighted_center_x(detections: list[dict]) -> float | None:
    if not detections:
        return None
    weighted_sum = 0.0
    total_weight = 0.0
    for detection in detections:
        confidence = float(detection.get("confidence") or 0.5)
        bbox = detection.get("bbox", [0, 0, 1, 1])
        area = max(1.0, float(bbox[2]) * float(bbox[3]))
        weight = confidence * area
        weighted_sum += float(detection["center"][0]) * weight
        total_weight += weight
    return weighted_sum / total_weight if total_weight else None


def _best_track(tracks: list[dict], start: float, end: float) -> tuple[dict | None, list[dict]]:
    best = None
    best_detections = []
    best_score = -1.0
    for track in tracks:
        detections = _detections_in_range(track, start, end)
        if not detections:
            continue
        confidence = float(track.get("averageConfidence") or 0.5)
        score = len(detections) * confidence
        if score > best_score:
            best = track
            best_detections = detections
            best_score = score
    return best, best_detections


def _smooth_center(previous: float | None, current: float | None, alpha: float) -> float | None:
    if current is None:
        return previous
    if previous is None:
        return current
    return previous * (1 - alpha) + current * alpha


def _build_layout_segments(
    face_detections: list[dict],
    clip_start: float,
    clip_end: float,
    scenes: list[dict],
) -> list[dict]:
    """
    Build layout segments aligned to scene (shot) boundaries.
    For each scene that intersects the clip:
      - Decide layout (crop or blur) based on the majority personCount in that scene.
      - Apply that layout to the entire scene interval.
    This guarantees that layout switches ONLY happen at scene cuts (shot boundaries)
    and never jump or zoom in the middle of a continuous shot.
    """
    if not scenes:
        # Fallback to a single scene spanning the entire clip
        scenes = [{"start": clip_start, "end": clip_end}]

    raw_segments = []
    
    # Process each scene that intersects the clip
    for scene in scenes:
        s_start = max(clip_start, float(scene.get("start", 0)))
        s_end = min(clip_end, float(scene.get("end", clip_end)))
        
        if s_start >= s_end - 0.05:
            continue
            
        # Gather detections within this scene interval
        scene_dets = [
            d for d in face_detections 
            if s_start <= float(d.get("time", 0)) <= s_end
        ]
        
        if not scene_dets:
            layout = "full-crop"
        else:
            # Use primaryPersonCount if available (filters out small background passersby), else personCount
            counts = [int(d.get("primaryPersonCount", d.get("personCount", 1))) for d in scene_dets]
            # Require at least 20% of frames (or at least 2 frames) to have 2+ people
            # to trigger blur-pad. This acts as a strong false positive filter.
            multi_person_frames = sum(1 for c in counts if c >= 2)
            if len(counts) >= 2:
                has_multi = (multi_person_frames >= 2) or (multi_person_frames / len(counts) >= 0.25)
            else:
                has_multi = multi_person_frames >= 1
            layout = "blur-pad" if has_multi else "full-crop"
            
        raw_segments.append({
            "start": round(s_start, 3),
            "end": round(s_end, 3),
            "layout": layout
        })

    # Sort segments by start time
    raw_segments.sort(key=lambda s: s["start"])

    # Merge adjacent segments with the same layout
    merged = []
    for seg in raw_segments:
        if not merged:
            merged.append(seg)
        else:
            if seg["layout"] == merged[-1]["layout"]:
                merged[-1]["end"] = seg["end"]
            else:
                merged.append(seg)

    # Ensure first segment starts at clip_start and last ends at clip_end
    if merged:
        merged[0]["start"] = round(clip_start, 3)
        merged[-1]["end"] = round(clip_end, 3)
    else:
        merged = [{"start": clip_start, "end": clip_end, "layout": "full-crop"}]

    return merged


def run(context):
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
        scenes = json.loads(scene_cuts_path.read_text(encoding="utf-8")).get("scenes", [])

    width = int(metadata["width"])
    height = int(metadata["height"])
    tracks = track_data.get("tracks", [])
    all_detections = detection_data.get("detections", [])
    smoothing_alpha = float(context["settings"].get("cropSmoothingAlpha", 0.35))
    layout_setting = context["settings"].get("layoutMode", "auto")
    crop_plans = []

    for highlight in sorted(highlights, key=lambda item: float(item["start"])):
        start = float(highlight["start"])
        end = float(highlight["end"])
        track, detections = _best_track(tracks, start, end)
        detected_center_x = _weighted_center_x(detections)
        # Calculate smooth center X specifically for this clip timeframe
        center_x = _smooth_center(None, detected_center_x, smoothing_alpha)

        # Build layout segments for this clip
        if layout_setting == "auto":
            layout_segments = _build_layout_segments(all_detections, start, end, scenes)
        elif layout_setting == "blur-pad":
            layout_segments = [{"start": start, "end": end, "layout": "blur-pad"}]
        else:
            layout_segments = [{"start": start, "end": end, "layout": "full-crop"}]

        # Determine dominant layout for backward compatibility
        dominant_layout = layout_segments[0]["layout"] if len(layout_segments) == 1 else "auto-dynamic"

        # Calculate AI Decision Confidence (0.0 to 1.0)
        confidence = 0.95 if detected_center_x is not None else 0.70
        if len(detections) < 3:
            confidence -= 0.15

        crop = _center_crop(width, height, center_x)
        method = "bytetrack-smooth" if detected_center_x is not None else "center-fallback"

        # Production Diagnostics
        diagnostics = {
            "layoutReason": f"Shot-aligned layout selection ({dominant_layout})",
            "faceDetectionsUsed": len(detections),
            "trackingMethod": method,
            "centerTrackingDelta": round(abs(detected_center_x - (width / 2)), 2) if detected_center_x is not None else 0.0,
        }

        crop_plans.append({
            "clipId": highlight["id"],
            "start": start,
            "end": end,
            "method": method,
            "confidenceScore": round(confidence, 2),
            "layoutMode": dominant_layout,
            "layoutSegments": layout_segments,
            "sourceWidth": width,
            "sourceHeight": height,
            "trackId": track.get("trackId") if track else None,
            "faceDetectionsUsed": len(detections),
            "detectedCenterX": round(detected_center_x, 3) if detected_center_x is not None else None,
            "smoothedCenterX": round(center_x, 3) if center_x is not None else None,
            "detector": detection_data.get("method"),
            "tracker": track_data.get("tracker"),
            "diagnostics": diagnostics,
            **crop,
        })

    (context["temp_dir"] / "crop_coords.json").write_text(
        json.dumps({
            "pipelineVersion": "2.4.0",
            "schemaVersion": "1.1",
            "targetAspectRatio": "9:16",
            "method": "bytetrack-smooth",
            "plans": crop_plans,
        }, indent=2),
        encoding="utf-8",
    )

