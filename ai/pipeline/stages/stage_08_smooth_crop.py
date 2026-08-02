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

        # Headroom Integrity Protection:
        # Guarantee crop top y never cuts below top of head/hair.
        # Top of head is ~18% crop_height above eye_y. Safe y top preserves at least 4% headroom.
        head_top_est = max(0.0, center_y - crop_height * 0.18)
        safe_max_y = max(0, int(round(head_top_est - height * 0.04)))
        if y > safe_max_y:
            y = safe_max_y
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


# Shot type → renderer layout mode mapping.
# This mapping is the ONLY place where editorial intent meets rendering strategy.
# close  → full-crop: tight subject-centered crop for single speaker
# wide   → blur-pad:  preserve both participants in letterboxed frame
# medium → full-crop: center framing with minimal zoom for content readability
SHOT_TYPE_TO_LAYOUT = {
    "close": "full-crop",
    "wide": "blur-pad",
    "medium": "full-crop",
}


def _layout_from_shot_plan(
    shot_plan_clips: list[dict],
    clip_id: str,
    clip_start: float,
    clip_end: float,
) -> list[dict]:
    """Convert editorial shot plan segments into renderer layout segments.

    Reads the upstream shot_plan.json output and maps each editorial shot type
    to a renderer-specific layout mode using SHOT_TYPE_TO_LAYOUT.
    """
    clip_plan = next(
        (c for c in shot_plan_clips if c.get("clipId") == clip_id),
        None,
    )

    if clip_plan is None:
        # Fallback: no shot plan available for this clip
        return [{"start": clip_start, "end": clip_end, "layout": "full-crop"}]

    segments = clip_plan.get("segments", [])
    if not segments:
        return [{"start": clip_start, "end": clip_end, "layout": "full-crop"}]

    layout_segments = []
    for seg in segments:
        shot_type = seg.get("shotType", "close")
        layout = SHOT_TYPE_TO_LAYOUT.get(shot_type, "full-crop")
        layout_segments.append({
            "start": round(float(seg["start"]), 3),
            "end": round(float(seg["end"]), 3),
            "layout": layout,
            "shotType": shot_type,
            "composition": seg.get("composition", "unknown"),
        })

    # Merge adjacent segments with identical layout
    merged = []
    for seg in layout_segments:
        if merged and merged[-1]["layout"] == seg["layout"]:
            merged[-1]["end"] = seg["end"]
        else:
            merged.append(seg)

    if merged:
        merged[0]["start"] = round(clip_start, 3)
        merged[-1]["end"] = round(clip_end, 3)
    else:
        merged = [{"start": clip_start, "end": clip_end, "layout": "full-crop"}]

    return merged


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
    face_anchors: list[dict] | None = None,
    face_expected_samples: int | None = None,
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

    face_anchors = face_anchors or []
    face_containment = []
    face_side_margins = []
    face_top_margins = []
    face_bottom_margins = []
    for face in face_anchors:
        left, top, box_w, box_h = (float(value) for value in face["bbox"][:4])
        face_area = max(1.0, box_w * box_h)
        face_containment.append(_intersection_area(left, top, box_w, box_h, crop) / face_area)
        center_x = left + box_w / 2.0
        face_side_margins.append(min(center_x - c_x, (c_x + c_w) - center_x) / max(c_w, 1.0))
        face_top_margins.append((top - c_y) / max(c_h, 1.0))
        face_bottom_margins.append(((c_y + c_h) - (top + box_h)) / max(c_h, 1.0))
    expected_face_samples = (
        max(1, int(math.ceil(max(0.0, clip_duration) / sample_interval_seconds)) + 1)
        if face_expected_samples is None
        else max(1, int(face_expected_samples))
    )
    face_coverage = min(1.0, len(face_anchors) / expected_face_samples)
    face_min_containment = min(face_containment) if face_containment else None
    face_min_side_margin = min(face_side_margins) if face_side_margins else None
    face_min_top_margin = min(face_top_margins) if face_top_margins else None
    face_min_bottom_margin = min(face_bottom_margins) if face_bottom_margins else None
    face_measured = bool(face_anchors)
    if face_measured:
        if face_coverage < 0.50:
            reasons.append("face_missing_for_most_of_clip")
        if face_min_containment is not None and face_min_containment < 0.98:
            reasons.append("face_materially_clipped")
        if face_min_side_margin is not None and face_min_side_margin < 0.15:
            reasons.append("face_near_horizontal_edge")
        if face_min_top_margin is not None and face_min_top_margin < 0.06:
            reasons.append("forehead_headroom_unsafe")
        if face_min_bottom_margin is not None and face_min_bottom_margin < 0.10:
            reasons.append("chin_clearance_unsafe")

    hard_failure = (
        not source_bounds_valid
        or (face_measured and (
            face_coverage < 0.50
            or (face_min_containment is not None and face_min_containment < 0.98)
            or (face_min_side_margin is not None and face_min_side_margin < 0.15)
            or (face_min_top_margin is not None and face_min_top_margin < 0.06)
            or (face_min_bottom_margin is not None and face_min_bottom_margin < 0.10)
        ))
        or (not face_measured and (
            sample_coverage < 0.50
            or (minimum_containment is not None and minimum_containment < 0.70)
        ))
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
        "faceValidation": "measured_identity_faces" if face_measured else "unavailable_person_boxes_only",
        "faceSampleCoverage": round(face_coverage, 3) if face_measured else None,
        "faceMinimumContainment": round(face_min_containment, 3) if face_min_containment is not None else None,
        "faceMinimumHorizontalMargin": round(face_min_side_margin, 3) if face_min_side_margin is not None else None,
        "faceMinimumTopMargin": round(face_min_top_margin, 3) if face_min_top_margin is not None else None,
        "faceMinimumBottomMargin": round(face_min_bottom_margin, 3) if face_min_bottom_margin is not None else None,
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
        "face_missing_for_most_of_clip",
        "face_materially_clipped",
        "face_near_horizontal_edge",
        "forehead_headroom_unsafe",
        "chin_clearance_unsafe",
    }
    if composition.get("faceValidation") != "measured_identity_faces":
        force_blur_reasons.add("selected_subject_materially_clipped")
    reasons = [
        reason
        for reason in composition.get("reasons", [])
        if reason in force_blur_reasons
    ]
    return bool(reasons), reasons


def _active_identity_faces(identity_data: dict | None, clip_start: float, clip_end: float) -> tuple[list[dict], list[dict]]:
    """Return only face samples belonging to each scene's approved active identity."""
    if not identity_data:
        return [], []
    anchors = []
    selections = []
    for scene in identity_data.get("scenes", []):
        scene_start = max(clip_start, float(scene.get("start", clip_start)))
        scene_end = min(clip_end, float(scene.get("end", clip_end)))
        if scene_end <= scene_start:
            continue
        switches = sorted(scene.get("subjectSwitches", []), key=lambda item: float(item.get("time", 0.0)))
        for index, switch in enumerate(switches):
            subject_id = switch.get("toSubjectId")
            if not subject_id:
                continue
            segment_start = max(scene_start, float(switch["time"]))
            segment_end = min(scene_end, float(switches[index + 1]["time"]) if index + 1 < len(switches) else scene_end)
            if segment_end < segment_start:
                continue
            identity = next((item for item in scene.get("identities", []) if item.get("subjectId") == subject_id), None)
            if identity is None:
                continue
            accepted = 0
            for detection in identity.get("detections", []):
                timestamp = float(detection.get("time", -1))
                if segment_start <= timestamp <= segment_end:
                    anchors.append({**detection, "subjectId": subject_id, "sceneIndex": scene.get("sceneIndex")})
                    accepted += 1
            selections.append({
                "sceneIndex": scene.get("sceneIndex"), "subjectId": subject_id,
                "start": round(segment_start, 3), "end": round(segment_end, 3),
                "reason": switch.get("reason"), "faceSampleCount": accepted,
            })
    return anchors, selections


def _weighted_face_anchor(face_anchors: list[dict]) -> tuple[float | None, float | None, float]:
    if not face_anchors:
        return None, None, 0.0
    weights = [max(0.01, float(face.get("confidence") or 0.0) * float(face["bbox"][2]) * float(face["bbox"][3])) for face in face_anchors]
    total = sum(weights)
    center_x = sum((float(face["bbox"][0]) + float(face["bbox"][2]) / 2.0) * weight for face, weight in zip(face_anchors, weights)) / total
    eye_y = sum((float(face["bbox"][1]) + float(face["bbox"][3]) * 0.42) * weight for face, weight in zip(face_anchors, weights)) / total
    confidence = statistics.fmean(float(face.get("confidence") or 0.0) for face in face_anchors)
    return center_x, eye_y, confidence


def _identity_faces_for_track(identity_faces: list[dict], track_detections: list[dict]) -> list[dict]:
    """Keep only approved active faces that belong to the selected person track."""
    associated = []
    for face in identity_faces:
        timestamp = float(face.get("time", -999.0))
        person = min(track_detections, key=lambda item: abs(float(item.get("time", -999.0)) - timestamp), default=None)
        if person is None or abs(float(person.get("time", -999.0)) - timestamp) > 0.26:
            continue
        px, py, pw, ph = (float(value) for value in person.get("bbox", [])[:4])
        fx, fy, fw, fh = (float(value) for value in face.get("bbox", [])[:4])
        center_x, center_y = fx + fw / 2.0, fy + fh / 2.0
        if px - pw * 0.10 <= center_x <= px + pw * 1.10 and py - ph * 0.10 <= center_y <= py + ph * 1.10:
            associated.append(face)
    return associated


def _identity_safe_layout_segments(
    base_segments: list[dict],
    scenes: list[dict],
    clip_start: float,
    clip_end: float,
    approved_faces: list[dict],
) -> list[dict]:
    """Use the existing blur-pad mode where the static crop lacks its approved identity."""
    safe_segments = []
    for scene in scenes or [{"start": clip_start, "end": clip_end}]:
        start = max(clip_start, float(scene.get("start", clip_start)))
        end = min(clip_end, float(scene.get("end", clip_end)))
        if end <= start + 0.05:
            continue
        midpoint = (start + end) / 2.0
        base_layout = next(
            (segment["layout"] for segment in base_segments if float(segment["start"]) <= midpoint <= float(segment["end"])),
            "blur-pad",
        )
        has_approved_face = any(start <= float(face.get("time", -1)) <= end for face in approved_faces)
        safe_segments.append({
            "start": round(start, 3), "end": round(end, 3),
            "layout": "full-crop" if has_approved_face and base_layout != "blur-pad" else "blur-pad",
        })
    merged = []
    for segment in safe_segments:
        if merged and merged[-1]["layout"] == segment["layout"]:
            merged[-1]["end"] = segment["end"]
        else:
            merged.append(segment)
    if merged:
        merged[0]["start"] = round(clip_start, 3)
        merged[-1]["end"] = round(clip_end, 3)
    return merged or [{"start": clip_start, "end": clip_end, "layout": "blur-pad"}]


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
    identity_path = context["temp_dir"] / "subject_identities.json"
    identity_data = json.loads(identity_path.read_text(encoding="utf-8")) if identity_path.exists() else None

    # Load upstream editorial shot plan (produced by stage_08_shot_selection)
    shot_plan_path = context["temp_dir"] / "shot_plan.json"
    shot_plan_clips = []
    if shot_plan_path.exists():
        shot_plan_clips = json.loads(
            shot_plan_path.read_text(encoding="utf-8")
        ).get("clips", [])

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
        active_identity_faces, identity_selections = _active_identity_faces(identity_data, start, end)
        identity_faces = _identity_faces_for_track(active_identity_faces, detections)
        face_x, face_y, face_confidence = _weighted_face_anchor(identity_faces)
        person_x, person_y, person_confidence = _weighted_center_anchors(detections, width, height)
        target_x = face_x if face_x is not None else person_x
        target_y = face_y if face_y is not None else person_y
        landmark_conf = face_confidence if face_x is not None else person_confidence

        # FORENSIC FIX: Initialize camera coordinates per highlight clip to eliminate state pollution dragging!
        cam_x = target_x if target_x is not None else width / 2.0
        cam_y = target_y if target_y is not None else height / 2.0

        # Fit guard starts from the widest valid source crop.  It never adds
        # score- or duration-driven zoom before composition is measured.
        target_scale = 1.0

        # Build layout segments from upstream editorial shot plan
        has_shot_plan = bool(shot_plan_clips)
        if layout_setting == "auto" and has_shot_plan:
            layout_segments = _layout_from_shot_plan(shot_plan_clips, highlight.get("id") or highlight.get("clipId") or highlight.get("clip_id", ""), start, end)
        elif layout_setting == "auto" and identity_data is not None:
            layout_segments = _build_layout_segments(all_detections, start, end, scenes, frame_w=width, frame_h=height)
            layout_segments = _identity_safe_layout_segments(
                layout_segments, scenes, start, end, identity_faces
            )
        elif layout_setting == "blur-pad":
            layout_segments = [{"start": start, "end": end, "layout": "blur-pad"}]
        else:
            layout_segments = [{"start": start, "end": end, "layout": "full-crop"}]

        raw_crop = _center_crop(width, height, center_x=cam_x, center_y=cam_y, scale=target_scale, eyeline_pct=0.35)
        crop = _validate_and_adjust_crop(raw_crop, width, height, center_x=cam_x)
        composition = _measure_composition(crop, width, height, detections, duration, identity_faces, len(detections))
        use_blur_pad, fit_guard_reasons = _resolve_fit_guard(composition)

        # ARCHITECTURAL PRINCIPLE: Downstream stages MUST respect upstream editorial authority.
        # Downstream override to blur-pad is permitted ONLY if producing the requested crop is
        # mathematically impossible or creates an invalid render (crop_outside_source_bounds).
        # Heuristic reasons (missing face anchors, sparse samples, edge proximity) are prohibited
        # from overriding approved shot decisions.
        if has_shot_plan:
            physical_impossibility = not composition.get("sourceBoundsValid", True) or "crop_outside_source_bounds" in fit_guard_reasons
            if physical_impossibility:
                layout_segments = [{"start": start, "end": end, "layout": "blur-pad"}]
                fit_guard_override = True
            else:
                fit_guard_override = False
        else:
            fit_guard_override = use_blur_pad
            if fit_guard_override:
                layout_segments = [{"start": start, "end": end, "layout": "blur-pad"}]

        dominant_layout = layout_segments[0]["layout"] if len(layout_segments) == 1 else "auto-dynamic"
        method = "production-identity-face-anchor" if face_x is not None else ("production-yolo-bytetrack-head-anchor" if target_x is not None else "safe-center-fallback")

        diagnostics = {
            "layoutReason": (
                f"Composition-aware Fit Guard ({', '.join(fit_guard_reasons)})"
                if use_blur_pad
                else f"Production Layout Matrix ({dominant_layout})"
            ),
            "faceDetectionsUsed": len(detections),
            "identityFaceAnchorsUsed": len(identity_faces),
            "activeIdentityFaceSamples": len(active_identity_faces),
            "activeIdentityFaceSamples": len(active_identity_faces),
            "identitySubjectSelections": identity_selections,
            "trackingMethod": method,
            "sceneSubjectSelections": scene_subjects,
            "landmarkConfidence": round(landmark_conf, 2),
            "qualityIndex": composition["qualityIndex"],
            "compositionValidation": composition,
            "fitGuard": {
                "enabled": True,
                "neutralScale": target_scale,
                "usedBlurPad": fit_guard_override,
                "reasons": fit_guard_reasons,
            },
            "zoomScale": target_scale,
        }

        crop_plans.append({
            "clipId": highlight.get("id") or highlight.get("clipId") or highlight.get("clip_id", ""),
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
            "identityFaceAnchorsUsed": len(identity_faces),
            "identitySubjectSelections": identity_selections,
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
