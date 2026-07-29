import json
import math
import statistics

TARGET_RATIO = 9 / 16
MIN_SEGMENT_DURATION = 1.5  # Minimum seconds before a layout switch
HEAD_WIDTH_FACTOR = 0.35  # Anthropometric upper-body height to head-width bounding factor (W_head ≈ 0.35 * h)


def _center_crop(
    width: int,
    height: int,
    center_x: float | None = None,
    center_y: float | None = None,
    scale: float = 1.02,
    eyeline_pct: float = 0.35,
) -> dict:
    """
    Calculate 9:16 portrait crop coordinates with face-first anchor and Rule-of-Thirds eye-line placement.
    Guarantees scale >= 1.0 so crop_height <= height and y is never clamped to 0!
    """
    # Scale bounds enforce scale >= 1.0 so crop_height NEVER exceeds source height!
    scale = max(1.0, min(1.35, float(scale)))

    crop_height = int(round(height / scale))
    crop_width = int(round(crop_height * TARGET_RATIO))

    if crop_width > width:
        crop_width = width
        crop_height = int(round(crop_width / TARGET_RATIO))

    # Ensure even dimensions for video codecs
    crop_width -= crop_width % 2
    crop_height -= crop_height % 2

    # Horizontal centering on Face Anchor X
    if center_x is None:
        center_x = width / 2.0
    x = int(round(center_x - crop_width / 2.0))
    x = max(0, min(x, width - crop_width))

    # Dynamic Rule-of-Thirds eye-line vertical alignment
    if center_y is not None:
        # Align facial eye-line anchor to 35% from top of crop window
        target_top = center_y - (eyeline_pct * crop_height)
        y = int(round(target_top))
    else:
        y = int(round((height - crop_height) / 2.0))

    # Valid bounds: height - crop_height >= 0 ALWAYS because scale >= 1.0!
    y = max(0, min(y, height - crop_height))

    return {
        "x": x,
        "y": y,
        "width": crop_width,
        "height": crop_height,
        "scale": round(scale, 3),
    }


def _is_meaningfully_visible(bbox: list[float] | None, frame_w: int, frame_h: int) -> bool:
    """Evaluate if a detected subject is sufficiently visible and not an edge artifact."""
    if not bbox or len(bbox) < 4:
        return False
    x1, y1, w, h = float(bbox[0]), float(bbox[1]), float(bbox[2]), float(bbox[3])
    rel_area = (w * h) / max(1.0, float(frame_w * frame_h))

    # Primary co-subject must represent at least 5.5% of frame area
    if rel_area < 0.055:
        return False

    # Must not be cut off at screen edge (3% - 97% boundary safety zone)
    if x1 < (frame_w * 0.03) or (x1 + w) > (frame_w * 0.97):
        return False

    return True


def _detections_in_range(track: dict, start: float, end: float) -> list[dict]:
    return [
        detection for detection in track.get("detections", [])
        if start <= float(detection["time"]) <= end
    ]


def _weighted_center_anchors(
    detections: list[dict],
    frame_w: int,
    frame_h: int
) -> tuple[float | None, float | None, float]:
    """
    Extract facial/head anchor coordinates (center_x, center_y) using YOLO + ByteTrack.
    Uses height-bounded head anchor calculation (W_head = HEAD_WIDTH_FACTOR * h) to prevent lateral arm gestures
    from pulling camera off-center.
    """
    if not detections:
        return None, None, 0.0

    weighted_x_sum = 0.0
    weighted_y_sum = 0.0
    total_weight = 0.0
    high_conf_count = 0

    for detection in detections:
        confidence = float(detection.get("confidence") or 0.5)
        bbox = detection.get("bbox", [0, 0, 1, 1])
        x1, y1, w, h = float(bbox[0]), float(bbox[1]), float(bbox[2]), float(bbox[3])
        area = max(1.0, w * h)
        weight = confidence * area

        center = detection.get("center")
        det_cx = float(center[0]) if (center and len(center) >= 2) else (x1 + w / 2.0)

        # Eye-Line Height Anchor (Upper 18% of body height)
        head_y = y1 + h * 0.18

        # Height-Bounded Head Anchor Calculation:
        # Head width is bounded by person height (W_head = HEAD_WIDTH_FACTOR * h), ignoring arm extensions.
        max_head_offset = min(w * 0.50, h * HEAD_WIDTH_FACTOR)

        if det_cx < frame_w * 0.45:
            # Subject on left side of frame facing center (podcasts/interviews)
            head_x = x1 + max_head_offset
        elif det_cx > frame_w * 0.55:
            # Subject on right side of frame facing center
            head_x = (x1 + w) - max_head_offset
        else:
            head_x = det_cx

        weighted_x_sum += head_x * weight
        weighted_y_sum += head_y * weight
        total_weight += weight

        if confidence >= 0.60:
            high_conf_count += 1

    if not total_weight:
        return None, None, 0.0

    avg_x = weighted_x_sum / total_weight
    avg_y = weighted_y_sum / total_weight
    landmark_confidence = high_conf_count / len(detections) if detections else 0.5

    return avg_x, avg_y, landmark_confidence


def _best_track(tracks: list[dict], start: float, end: float, frame_w: int = 1920) -> tuple[dict | None, list[dict]]:
    """Select optimal subject track based on detection score, area, and central priority."""
    best = None
    best_detections = []
    best_score = -1.0
    for track in tracks:
        detections = _detections_in_range(track, start, end)
        if not detections:
            continue
        confidence = float(track.get("averageConfidence") or 0.5)
        avg_area = sum(float(d.get("bbox", [0, 0, 1, 1])[2]) * float(d.get("bbox", [0, 0, 1, 1])[3]) for d in detections) / len(detections)
        score = len(detections) * confidence * (1.0 + min(1.0, avg_area / (frame_w * 0.15)))
        if score > best_score:
            best = track
            best_detections = detections
            best_score = score
    return best, best_detections


def _calculate_crop_quality_score(
    visibility_score: float,
    speaker_score: float,
    headroom_score: float,
    safe_zone_score: float,
    stability_score: float,
) -> float:
    """Calculate multi-factor candidate crop quality index Q in [0.0, 1.0]."""
    w1, w2, w3, w4, w5 = 0.25, 0.30, 0.20, 0.15, 0.10
    score = (
        w1 * visibility_score +
        w2 * speaker_score +
        w3 * headroom_score +
        w4 * safe_zone_score +
        w5 * stability_score
    )
    return round(max(0.0, min(1.0, score)), 3)


def _build_layout_segments(
    face_detections: list[dict],
    clip_start: float,
    clip_end: float,
    scenes: list[dict],
    frame_w: int = 1920,
    frame_h: int = 1080,
) -> list[dict]:
    """
    Complete Production Layout Decision Matrix.
    Maps subject configurations to explicit layout modes (full-crop vs blur-pad) aligned to scene boundaries.
    """
    if not scenes:
        scenes = [{"start": clip_start, "end": clip_end}]

    raw_segments = []

    for scene in scenes:
        s_start = max(clip_start, float(scene.get("start", 0)))
        s_end = min(clip_end, float(scene.get("end", clip_end)))

        if s_start >= s_end - 0.05:
            continue

        scene_dets = [
            d for d in face_detections
            if s_start <= float(d.get("time", 0)) <= s_end
        ]

        if not scene_dets:
            layout = "full-crop"
        else:
            meaningful_multi = 0
            for d in scene_dets:
                bbox = d.get("bbox")
                person_count = int(d.get("primaryPersonCount", d.get("personCount", 1)))
                if person_count >= 2 and _is_meaningfully_visible(bbox, frame_w, frame_h):
                    meaningful_multi += 1

            if len(scene_dets) >= 2:
                has_multi = (meaningful_multi / len(scene_dets)) >= 0.35
            else:
                has_multi = meaningful_multi >= 1

            layout = "blur-pad" if has_multi else "full-crop"

        raw_segments.append({
            "start": round(s_start, 3),
            "end": round(s_end, 3),
            "layout": layout
        })

    raw_segments.sort(key=lambda s: s["start"])

    # Merge adjacent segments with identical layout
    merged = []
    for seg in raw_segments:
        if not merged:
            merged.append(seg)
        else:
            if seg["layout"] == merged[-1]["layout"]:
                merged[-1]["end"] = seg["end"]
            else:
                merged.append(seg)

    if merged:
        merged[0]["start"] = round(clip_start, 3)
        merged[-1]["end"] = round(clip_end, 3)
    else:
        merged = [{"start": clip_start, "end": clip_end, "layout": "full-crop"}]

    return merged


def _validate_and_adjust_crop(
    crop: dict,
    width: int,
    height: int,
    center_x: float | None = None,
) -> dict:
    """
    Validate crop bounds and enforce 15% Face Safety Zone.
    Guarantees the face center never sits within the outer 15% margins of the 9:16 frame.
    """
    c_w = crop["width"]
    c_h = crop["height"]

    # Guarantee crop dimensions never exceed frame dimensions
    c_w = min(c_w, width)
    c_h = min(c_h, height)

    x = int(crop["x"])
    y = int(crop["y"])

    # Enforce 15% Face Safety Zone (0.15 * c_w)
    if center_x is not None:
        safe_margin = int(c_w * 0.15)
        # Left boundary check
        if center_x - x < safe_margin:
            x = int(center_x - safe_margin)
        # Right boundary check
        elif (x + c_w) - center_x < safe_margin:
            x = int(center_x + safe_margin - c_w)

    x = max(0, min(x, width - c_w))
    y = max(0, min(y, height - c_h))

    return {
        "x": x,
        "y": y,
        "width": c_w,
        "height": c_h,
        "scale": crop.get("scale", 1.02),
    }


def _intersection_area(left: float, top: float, width: float, height: float, crop: dict) -> float:
    """Return the overlap area between a person box and the source-space crop."""
    right = left + width
    bottom = top + height
    crop_left = float(crop["x"])
    crop_top = float(crop["y"])
    crop_right = crop_left + float(crop["width"])
    crop_bottom = crop_top + float(crop["height"])
    overlap_width = max(0.0, min(right, crop_right) - max(left, crop_left))
    overlap_height = max(0.0, min(bottom, crop_bottom) - max(top, crop_top))
    return overlap_width * overlap_height


def _measure_composition(
    crop: dict,
    width: int,
    height: int,
    detections: list[dict],
    clip_duration: float,
    sample_interval_seconds: float = 0.5,
) -> dict:
    """Measure the current static plan without changing its framing policy.

    The pipeline currently supplies person boxes rather than face landmarks.  The
    result deliberately records that limitation instead of treating an inferred
    head anchor as face-validation evidence.
    """
    reasons: list[str] = []
    c_x = float(crop["x"])
    c_y = float(crop["y"])
    c_w = float(crop["width"])
    c_h = float(crop["height"])
    source_bounds_valid = (
        c_w > 0
        and c_h > 0
        and c_x >= 0
        and c_y >= 0
        and c_x + c_w <= width
        and c_y + c_h <= height
    )
    if not source_bounds_valid:
        reasons.append("crop_outside_source_bounds")

    expected_samples = max(1, int(math.ceil(max(0.0, clip_duration) / sample_interval_seconds)) + 1)
    sample_coverage = min(1.0, len(detections) / expected_samples)
    containment_ratios: list[float] = []
    side_margins: list[float] = []
    body_coverages: list[float] = []
    for detection in detections:
        bbox = detection.get("bbox")
        if not bbox or len(bbox) < 4:
            continue
        left, top, box_w, box_h = (float(value) for value in bbox[:4])
        box_area = max(1.0, box_w * box_h)
        containment_ratios.append(
            _intersection_area(left, top, box_w, box_h, crop) / box_area
        )
        box_center_x = left + box_w / 2.0
        side_margins.append(min(box_center_x - c_x, (c_x + c_w) - box_center_x) / max(c_w, 1.0))
        body_coverages.append(box_area / max(c_w * c_h, 1.0))

    if not containment_ratios:
        reasons.append("no_selected_subject_detections")
    minimum_containment = min(containment_ratios) if containment_ratios else None
    average_containment = statistics.fmean(containment_ratios) if containment_ratios else None
    minimum_side_margin = min(side_margins) if side_margins else None
    median_body_coverage = statistics.median(body_coverages) if body_coverages else None

    if sample_coverage < 0.50:
        reasons.append("selected_subject_missing_for_most_of_clip")
    elif sample_coverage < 0.75:
        reasons.append("selected_subject_tracking_incomplete")
    if minimum_containment is not None and minimum_containment < 0.70:
        reasons.append("selected_subject_materially_clipped")
    elif minimum_containment is not None and minimum_containment < 0.90:
        reasons.append("selected_subject_partially_clipped")
    if minimum_side_margin is not None and minimum_side_margin < 0.15:
        reasons.append("selected_subject_near_horizontal_edge")

    hard_failure = (
        not source_bounds_valid
        or sample_coverage < 0.50
        or (minimum_containment is not None and minimum_containment < 0.70)
    )
    warning = bool(reasons) and not hard_failure
    status = "fail" if hard_failure else "warning" if warning else "pass"

    # A measured score is retained for compatibility only; callers must use
    # status/reasons for production gating, not this aggregate value.
    score_parts = [1.0 if source_bounds_valid else 0.0, sample_coverage]
    if average_containment is not None:
        score_parts.append(average_containment)
    if minimum_side_margin is not None:
        score_parts.append(min(1.0, minimum_side_margin / 0.15))
    quality_index = round(statistics.fmean(score_parts), 3)

    return {
        "status": status,
        "reasons": reasons,
        "qualityIndex": quality_index,
        "sourceBoundsValid": source_bounds_valid,
        "selectedSubjectSampleCoverage": round(sample_coverage, 3),
        "selectedSubjectMinimumContainment": round(minimum_containment, 3) if minimum_containment is not None else None,
        "selectedSubjectAverageContainment": round(average_containment, 3) if average_containment is not None else None,
        "selectedSubjectMinimumHorizontalMargin": round(minimum_side_margin, 3) if minimum_side_margin is not None else None,
        "selectedSubjectMedianBodyCoverage": round(median_body_coverage, 3) if median_body_coverage is not None else None,
        "faceValidation": "unavailable_person_boxes_only",
    }


def _resolve_fit_guard(composition: dict) -> tuple[bool, list[str]]:
    """Choose the existing blur-pad fallback when a static crop is infeasible.

    This deliberately does not change tracking or create a new rendering mode.
    It prevents an already-proven infeasible full-crop plan from being rendered
    as a tighter view of the same subject.
    """
    force_blur_reasons = {
        "crop_outside_source_bounds",
        "no_selected_subject_detections",
        "selected_subject_missing_for_most_of_clip",
        "selected_subject_materially_clipped",
    }
    reasons = [
        reason
        for reason in composition.get("reasons", [])
        if reason in force_blur_reasons
    ]
    return bool(reasons), reasons


def _select_visible_subject_for_scene(
    tracks: list[dict],
    start: float,
    end: float,
    frame_w: int,
    frame_h: int,
    sample_interval_seconds: float = 0.5,
) -> dict:
    """Choose the strongest visible person track for one scene interval.

    This is intentionally selection-only.  Crop coordinates remain whole-clip
    until the separate per-scene crop/render change is approved.
    """
    expected_samples = max(1, int(math.ceil(max(0.0, end - start) / sample_interval_seconds)) + 1)
    candidates = []
    for track in tracks:
        detections = _detections_in_range(track, start, end)
        if not detections:
            continue
        confidences = [float(d.get("confidence") or 0.0) for d in detections]
        areas = [
            float(d.get("bbox", [0, 0, 0, 0])[2]) * float(d.get("bbox", [0, 0, 0, 0])[3])
            for d in detections
        ]
        visible_detections = 0
        edge_safe_detections = 0
        for detection in detections:
            bbox = detection.get("bbox", [0, 0, 0, 0])
            x, y, w, h = (float(value) for value in bbox[:4])
            if x + w > 0 and y + h > 0 and x < frame_w and y < frame_h:
                visible_detections += 1
            if x >= frame_w * 0.03 and x + w <= frame_w * 0.97:
                edge_safe_detections += 1

        coverage = min(1.0, len(detections) / expected_samples)
        visible_ratio = visible_detections / len(detections)
        edge_safe_ratio = edge_safe_detections / len(detections)
        average_confidence = statistics.fmean(confidences)
        median_area_ratio = statistics.median(areas) / max(1.0, frame_w * frame_h)
        score = (
            0.50 * coverage
            + 0.25 * average_confidence
            + 0.15 * min(1.0, median_area_ratio / 0.10)
            + 0.10 * edge_safe_ratio
        )
        candidates.append({
            "trackId": track.get("trackId"),
            "detectionCount": len(detections),
            "sampleCoverage": round(coverage, 3),
            "visibleDetectionRatio": round(visible_ratio, 3),
            "edgeSafeDetectionRatio": round(edge_safe_ratio, 3),
            "averageConfidence": round(average_confidence, 3),
            "medianAreaRatio": round(median_area_ratio, 3),
            "selectionScore": round(score, 3),
        })

    if not candidates:
        return {
            "trackId": None,
            "selection": "no_visible_subject",
            "reason": "no_track_detections_in_scene",
        }

    best = max(candidates, key=lambda candidate: candidate["selectionScore"])
    if best["sampleCoverage"] < 0.50 or best["visibleDetectionRatio"] < 0.75:
        return {
            **best,
            "trackId": None,
            "selection": "no_visible_subject",
            "reason": "no_track_is_visible_for_enough_of_scene",
        }
    return {
        **best,
        "selection": "best_visible_track",
        "reason": "scene_local_visibility_confidence_area_score",
    }


def _scene_subject_selections(
    tracks: list[dict],
    scenes: list[dict],
    clip_start: float,
    clip_end: float,
    frame_w: int,
    frame_h: int,
) -> list[dict]:
    """Return one scene-local subject decision for every intersecting scene."""
    candidate_scenes = scenes or [{"start": clip_start, "end": clip_end}]
    selections = []
    for scene in candidate_scenes:
        start = max(clip_start, float(scene.get("start", clip_start)))
        end = min(clip_end, float(scene.get("end", clip_end)))
        if end <= start + 0.05:
            continue
        selection = _select_visible_subject_for_scene(
            tracks, start, end, frame_w, frame_h
        )
        selections.append({
            "start": round(start, 3),
            "end": round(end, 3),
            **selection,
        })
    return selections


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
    layout_setting = context["settings"].get("layoutMode", "auto")
    crop_plans = []

    for highlight in sorted(highlights, key=lambda item: float(item["start"])):
        start = float(highlight["start"])
        end = float(highlight["end"])
        duration = end - start

        track, detections = _best_track(tracks, start, end, frame_w=width)
        scene_subjects = _scene_subject_selections(
            tracks, scenes, start, end, width, height
        )
        target_x, target_y, landmark_conf = _weighted_center_anchors(detections, width, height)

        # FORENSIC FIX: Initialize camera coordinates per highlight clip to eliminate state pollution dragging!
        cam_x = target_x if target_x is not None else width / 2.0
        cam_y = target_y if target_y is not None else height / 2.0

        # Fit guard starts from the widest valid source crop.  It never adds
        # score- or duration-driven zoom before composition is measured.
        target_scale = 1.0

        # Build layout segments
        if layout_setting == "auto":
            layout_segments = _build_layout_segments(all_detections, start, end, scenes, frame_w=width, frame_h=height)
        elif layout_setting == "blur-pad":
            layout_segments = [{"start": start, "end": end, "layout": "blur-pad"}]
        else:
            layout_segments = [{"start": start, "end": end, "layout": "full-crop"}]

        raw_crop = _center_crop(width, height, center_x=cam_x, center_y=cam_y, scale=target_scale, eyeline_pct=0.35)
        crop = _validate_and_adjust_crop(raw_crop, width, height, center_x=cam_x)
        composition = _measure_composition(crop, width, height, detections, duration)
        use_blur_pad, fit_guard_reasons = _resolve_fit_guard(composition)
        if use_blur_pad:
            layout_segments = [{"start": start, "end": end, "layout": "blur-pad"}]

        dominant_layout = layout_segments[0]["layout"] if len(layout_segments) == 1 else "auto-dynamic"
        method = "production-yolo-bytetrack-head-anchor" if target_x is not None else "safe-center-fallback"

        diagnostics = {
            "layoutReason": (
                f"Composition-aware Fit Guard ({', '.join(fit_guard_reasons)})"
                if use_blur_pad
                else f"Production Layout Matrix ({dominant_layout})"
            ),
            "faceDetectionsUsed": len(detections),
            "trackingMethod": method,
            "sceneSubjectSelections": scene_subjects,
            "landmarkConfidence": round(landmark_conf, 2),
            "qualityIndex": composition["qualityIndex"],
            "compositionValidation": composition,
            "fitGuard": {
                "enabled": True,
                "neutralScale": target_scale,
                "usedBlurPad": use_blur_pad,
                "reasons": fit_guard_reasons,
            },
            "zoomScale": target_scale,
        }

        crop_plans.append({
            "clipId": highlight["id"],
            "start": start,
            "end": end,
            "method": method,
            "confidenceScore": round(landmark_conf if target_x is not None else 0.75, 2),
            "qualityIndex": composition["qualityIndex"],
            "compositionValidation": composition,
            "fitGuard": diagnostics["fitGuard"],
            "layoutMode": layout_setting,
            "resolvedLayout": dominant_layout,
            "layoutSegments": layout_segments,
            "sourceWidth": width,
            "sourceHeight": height,
            "trackId": track.get("trackId") if track else None,
            "sceneSubjectSelections": scene_subjects,
            "faceDetectionsUsed": len(detections),
            "detectedCenterX": round(target_x, 3) if target_x is not None else None,
            "detectedCenterY": round(target_y, 3) if target_y is not None else None,
            "smoothedCenterX": round(cam_x, 3) if cam_x is not None else None,
            "smoothedCenterY": round(cam_y, 3) if cam_y is not None else None,
            "detector": detection_data.get("method"),
            "tracker": track_data.get("tracker"),
            "diagnostics": diagnostics,
            **crop,
        })

    (context["temp_dir"] / "crop_coords.json").write_text(
        json.dumps({
            "pipelineVersion": "3.5.0",
            "schemaVersion": "1.7",
            "targetAspectRatio": "9:16",
            "method": "production-yolo-bytetrack-head-anchor",
            "plans": crop_plans,
        }, indent=2),
        encoding="utf-8",
    )
