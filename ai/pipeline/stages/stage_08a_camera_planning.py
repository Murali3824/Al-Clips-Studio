"""Virtual-camera planning only; no renderer consumes this artifact yet."""

import json
import math
import statistics


MAX_HORIZONTAL_VELOCITY = 45.0  # source pixels / second
MAX_VERTICAL_VELOCITY = 35.0
MAX_ZOOM_VELOCITY = 0.015       # zoom units / second
MIN_MEANINGFUL_PAN = 12.0       # source pixels
MIN_MEANINGFUL_ZOOM = 0.004
MAX_ENGAGEMENT_ZOOM = 1.012
MIN_ENGAGEMENT_SEGMENT_SECONDS = 8.0
HORIZONTAL_PAN_DEAD_ZONE = 5.0
VERTICAL_PAN_DEAD_ZONE = 4.0
MICRO_PAN_DAMPING = 0.70
EASING_CUBIC = "cubic_ease_in_out"
EASING_SINE = "sine_ease_in_out"
FACE_ANCHOR_WINDOW_SECONDS = 1.5
PORTRAIT_FACE_OCCUPANCY_TARGET = 0.36
MAX_PORTRAIT_FILL_ZOOM = 1.10
MIN_PORTRAIT_FILL_SECONDS = 6.0


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _scene_segments(plan: dict, scenes: list[dict]) -> list[dict]:
    """Split composition layouts at cuts without changing their layout decisions."""
    result = []
    for scene in scenes or [{"start": plan["start"], "end": plan["end"]}]:
        start = max(float(plan["start"]), float(scene.get("start", plan["start"])))
        end = min(float(plan["end"]), float(scene.get("end", plan["end"])))
        if end <= start + 0.05:
            continue
        midpoint = (start + end) / 2.0
        layout = next((item["layout"] for item in plan.get("layoutSegments", []) if float(item["start"]) <= midpoint <= float(item["end"])), "blur-pad")
        result.append({"start": round(start, 3), "end": round(end, 3), "layout": layout, "sceneIndex": scene.get("index")})
    return result


def _approved_faces(identity_data: dict, plan: dict, start: float, end: float) -> list[dict]:
    approved = []
    for selection in plan.get("identitySubjectSelections", []):
        selection_start = max(start, float(selection["start"]))
        selection_end = min(end, float(selection["end"]))
        if selection_end < selection_start:
            continue
        scene = next((item for item in identity_data.get("scenes", []) if item.get("sceneIndex") == selection.get("sceneIndex")), None)
        if scene is None:
            continue
        identity = next((item for item in scene.get("identities", []) if item.get("subjectId") == selection.get("subjectId")), None)
        if identity is None:
            continue
        approved.extend(
            {**detection, "subjectId": selection["subjectId"]}
            for detection in identity.get("detections", [])
            if selection_start <= float(detection["time"]) <= selection_end
        )
    return approved


def _weighted_median(values: list[float], weights: list[float]) -> float:
    ordered = sorted(zip(values, weights), key=lambda item: item[0])
    threshold = sum(weights) / 2.0
    cumulative = 0.0
    for value, weight in ordered:
        cumulative += weight
        if cumulative >= threshold:
            return value
    return ordered[-1][0]


def _stable_face_anchor(faces: list[dict], toward_start: bool) -> dict | None:
    """Use a local, confidence-weighted identity-face anchor instead of one sample.

    The planner remains a two-keyframe camera plan.  This only makes each
    existing target representative of a short, approved-identity interval so a
    single face-box fluctuation cannot pull the composition off the speaker.
    """
    if not faces:
        return None
    ordered = sorted(faces, key=lambda face: float(face["time"]))
    edge_time = float(ordered[0 if toward_start else -1]["time"])
    window = [
        face for face in ordered
        if (float(face["time"]) - edge_time <= FACE_ANCHOR_WINDOW_SECONDS if toward_start else edge_time - float(face["time"]) <= FACE_ANCHOR_WINDOW_SECONDS)
    ]
    if len(window) < 2:
        return ordered[0 if toward_start else -1]
    boxes = [face["bbox"] for face in window]
    weights = [max(0.01, float(face.get("confidence") or 0.0) * float(box[2]) * float(box[3])) for face, box in zip(window, boxes)]
    return {
        **(window[0] if toward_start else window[-1]),
        "bbox": [_weighted_median([float(box[index]) for box in boxes], weights) for index in range(4)],
        "confidence": sum(float(face.get("confidence") or 0.0) for face in window) / len(window),
    }


def _camera_target(crop: dict, face: dict | None, minimum_zoom: float = 1.0) -> dict:
    """Return a future camera rectangle entirely inside the approved composition crop."""
    base_x, base_y = float(crop["x"]), float(crop["y"])
    base_w, base_h = float(crop["width"]), float(crop["height"])
    if face is None:
        return {"x": base_x, "y": base_y, "zoom": 1.0, "width": base_w, "height": base_h}
    fx, fy, fw, fh = (float(value) for value in face["bbox"][:4])
    # Gentle zoom responds only to a face occupying more than 22% of the approved height.
    zoom = _clamp(max(minimum_zoom, 1.0 + max(0.0, fh / base_h - 0.22) * 0.18), 1.0, MAX_PORTRAIT_FILL_ZOOM)
    width, height = base_w / zoom, base_h / zoom
    center_x, eye_y = fx + fw / 2.0, fy + fh * 0.42
    x = _clamp(center_x - width / 2.0, base_x, base_x + base_w - width)
    y = eye_y - height * 0.35
    # Headroom Protection: crop top y must never cut into top of hair (fy - 0.35 * fh)
    head_top_y = fy - fh * 0.35
    safe_y_top = max(base_y, head_top_y - base_h * 0.03)
    y = min(y, safe_y_top)
    y = _clamp(y, base_y, base_y + base_h - height)
    return {"x": x, "y": y, "zoom": zoom, "width": width, "height": height}


def _portrait_fill_zoom(plan: dict, segment: dict, faces: list[dict], duration: float) -> tuple[float, str]:
    """Select the safest tighter target for a sustained single-speaker portrait."""
    if segment["layout"] != "full-crop" or duration < MIN_PORTRAIT_FILL_SECONDS:
        return 1.0, "not_a_sustained_full_crop_scene"
    subject_ids = {face.get("subjectId") for face in faces if face.get("subjectId")}
    if len(subject_ids) != 1 or not faces:
        return 1.0, "multiple_or_missing_approved_subjects"
    crop = {key: float(plan[key]) for key in ("x", "y", "width", "height")}
    median_face_height = statistics.median(float(face["bbox"][3]) for face in faces)
    desired_zoom = _clamp(PORTRAIT_FACE_OCCUPANCY_TARGET / max(0.01, median_face_height / crop["height"]), 1.0, MAX_PORTRAIT_FILL_ZOOM)
    for face in faces:
        target = _camera_target(crop, face, desired_zoom)
        left, top, width, height = (float(value) for value in face["bbox"][:4])
        if (
            top - target["y"] < target["height"] * 0.08
            or target["y"] + target["height"] - (top + height) < target["height"] * 0.18
            or left - target["x"] < target["width"] * 0.12
            or target["x"] + target["width"] - (left + width) < target["width"] * 0.12
        ):
            return 1.0, "portrait_fill_rejected_by_face_safety"
    return desired_zoom, "single_speaker_portrait_fill_safe"


def _engagement_zoom_target(crop: dict, face: dict | None, duration: float, base_zoom: float = 1.0) -> dict | None:
    """Return a small, safe zoom-in for a stable, well-composed talking head."""
    if face is None or duration < MIN_ENGAGEMENT_SEGMENT_SECONDS:
        return None
    existing_candidate = _camera_target(crop, face)
    if existing_candidate["zoom"] < 1.0 + MIN_MEANINGFUL_ZOOM:
        return None
    zoom = min(MAX_PORTRAIT_FILL_ZOOM, base_zoom + min(MAX_ENGAGEMENT_ZOOM, existing_candidate["zoom"]) - 1.0)
    base_w, base_h = float(crop["width"]), float(crop["height"])
    width, height = base_w / zoom, base_h / zoom
    fx, fy, fw, fh = (float(value) for value in face["bbox"][:4])
    center_x, eye_y = fx + fw / 2.0, fy + fh * 0.42
    x = _clamp(center_x - width / 2.0, float(crop["x"]), float(crop["x"]) + base_w - width)
    y = _clamp(eye_y - height * 0.35, float(crop["y"]), float(crop["y"]) + base_h - height)
    return {"x": x, "y": y, "zoom": zoom, "width": width, "height": height}


def _limit_target(start: dict, target: dict, duration: float) -> dict:
    duration = max(0.25, duration)
    limits = {"x": MAX_HORIZONTAL_VELOCITY * duration, "y": MAX_VERTICAL_VELOCITY * duration, "zoom": MAX_ZOOM_VELOCITY * duration}
    return {**target, **{axis: start[axis] + _clamp(target[axis] - start[axis], -limits[axis], limits[axis]) for axis in limits}}


def _damp_axis(start: float, target: float, dead_zone: float) -> float:
    delta = target - start
    if abs(delta) <= dead_zone:
        return start
    return start + math.copysign(dead_zone + (abs(delta) - dead_zone) * MICRO_PAN_DAMPING, delta)


def _damped_micro_pan(start: dict, target: dict) -> dict:
    """Suppress noise-scale pan and soften meaningful approved-subject movement."""
    return {
        **target,
        "x": _damp_axis(float(start["x"]), float(target["x"]), HORIZONTAL_PAN_DEAD_ZONE),
        "y": _damp_axis(float(start["y"]), float(target["y"]), VERTICAL_PAN_DEAD_ZONE),
    }


def _pan_distance(start: dict, end: dict) -> float:
    return math.hypot(float(end["x"]) - float(start["x"]), float(end["y"]) - float(start["y"]))


def _motion_metrics(start: dict, end: dict, duration: float, easing: str = EASING_CUBIC) -> tuple[dict, dict, dict, bool]:
    duration = max(0.25, duration)
    delta = {axis: end[axis] - start[axis] for axis in ("x", "y", "zoom")}
    moving = math.hypot(delta["x"], delta["y"]) >= MIN_MEANINGFUL_PAN or abs(delta["zoom"]) >= MIN_MEANINGFUL_ZOOM
    # The sine profile has lower peak acceleration than cubic and reaches zero
    # velocity at both endpoints, producing a more natural settle on deliberate pans.
    factors = (math.pi / 2.0, math.pi * math.pi / 2.0, math.pi ** 3 / 2.0) if easing == EASING_SINE else (1.5, 6.0, 12.0)
    peak_velocity = {axis: round(abs(value) * factors[0] / duration, 4) for axis, value in delta.items()}
    peak_acceleration = {axis: round(abs(value) * factors[1] / (duration * duration), 4) for axis, value in delta.items()}
    peak_jerk = {axis: round(abs(value) * factors[2] / (duration * duration * duration), 5) for axis, value in delta.items()}
    return peak_velocity, peak_acceleration, peak_jerk, moving


def _plan_segment(plan: dict, segment: dict, identity_data: dict) -> dict:
    duration = float(segment["end"]) - float(segment["start"])
    crop = {key: float(plan[key]) for key in ("x", "y", "width", "height")}
    faces = _approved_faces(identity_data, plan, float(segment["start"]), float(segment["end"]))
    portrait_zoom, portrait_reason = _portrait_fill_zoom(plan, segment, faces, duration)
    first_face = min(faces, key=lambda item: float(item["time"]), default=None)
    last_face = max(faces, key=lambda item: float(item["time"]), default=None)
    stable_first_face = _stable_face_anchor(faces, toward_start=True)
    stable_last_face = _stable_face_anchor(faces, toward_start=False)
    start_camera = _camera_target(crop, stable_first_face, portrait_zoom)
    raw_end_camera = _limit_target(start_camera, _camera_target(crop, stable_last_face, portrait_zoom), duration)
    # Preserve the previously approved decision about whether a subject move is
    # meaningful.  Stabilized anchors refine composition targets; they must not
    # silently turn an approved pan into a different zoom policy.
    raw_start_camera = _camera_target(crop, first_face, portrait_zoom)
    original_end_camera = _limit_target(raw_start_camera, _camera_target(crop, last_face, portrait_zoom), duration)
    raw_velocity, raw_acceleration, raw_jerk, raw_moving = _motion_metrics(raw_start_camera, original_end_camera, duration)
    end_camera = _damped_micro_pan(start_camera, raw_end_camera)
    velocity, acceleration, jerk, moving = _motion_metrics(start_camera, end_camera, duration)
    moving = moving or raw_moving
    raw_pan_distance = _pan_distance(start_camera, raw_end_camera)
    planned_pan_distance = _pan_distance(start_camera, end_camera)
    motion_reason = "approved_subject_motion" if moving else "static_subject_hold"
    if segment["layout"] == "blur-pad":
        start_camera = _camera_target(crop, None)
        end_camera = start_camera
        velocity, acceleration, jerk, moving = _motion_metrics(start_camera, end_camera, duration)
        raw_pan_distance = 0.0
        planned_pan_distance = 0.0
        motion_reason = "blur_pad_fallback"
    elif not moving:
        engagement_target = _engagement_zoom_target(crop, first_face, duration, portrait_zoom)
        if engagement_target is not None:
            start_camera = _camera_target(crop, stable_first_face, portrait_zoom) if portrait_zoom > 1.0 else _camera_target(crop, None)
            raw_end_camera = _limit_target(start_camera, engagement_target, duration)
            raw_pan_distance = _pan_distance(start_camera, raw_end_camera)
            end_camera = _damped_micro_pan(start_camera, raw_end_camera)
            planned_pan_distance = _pan_distance(start_camera, end_camera)
            velocity, acceleration, jerk, moving = _motion_metrics(start_camera, end_camera, duration)
            motion_reason = "gentle_engagement_zoom"
        else:
            start_camera = _camera_target(crop, stable_first_face, portrait_zoom) if portrait_zoom > 1.0 else _camera_target(crop, None)
            end_camera = start_camera
            velocity, acceleration, jerk, moving = _motion_metrics(start_camera, end_camera, duration)
            raw_pan_distance = 0.0
            planned_pan_distance = 0.0
    easing = EASING_SINE if motion_reason == "approved_subject_motion" else EASING_CUBIC
    velocity, acceleration, jerk, _ = _motion_metrics(start_camera, end_camera, duration, easing)
    return {
        **segment,
        "cameraFrozen": not moving,
        "motionReason": motion_reason,
        "portraitFill": {"baseZoom": round(portrait_zoom, 3), "reason": portrait_reason},
        "microPan": {
            "horizontalDeadZone": HORIZONTAL_PAN_DEAD_ZONE,
            "verticalDeadZone": VERTICAL_PAN_DEAD_ZONE,
            "damping": MICRO_PAN_DAMPING,
            "rawPanDistance": round(raw_pan_distance, 3),
            "plannedPanDistance": round(planned_pan_distance, 3),
            "jitterSuppressed": round(max(0.0, raw_pan_distance - planned_pan_distance), 3),
        },
        "approvedFaceSamples": len(faces),
        "easing": easing,
        "resetAtSceneBoundary": True,
        "maxVelocity": velocity,
        "maxAcceleration": acceleration,
        "keyframes": [
            {"time": round(float(segment["start"]), 3), "position": {key: round(value, 3) for key, value in start_camera.items()}, "velocity": {"x": 0.0, "y": 0.0, "zoom": 0.0}},
            {"time": round(float(segment["end"]), 3), "position": {key: round(value, 3) for key, value in end_camera.items()}, "velocity": {"x": 0.0, "y": 0.0, "zoom": 0.0}},
        ],
    }


def _diagnostic_svg(camera_plans: list[dict]) -> str:
    height = 90 + 110 * len(camera_plans)
    lines = [f'<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="{height}" viewBox="0 0 1200 {height}">', '<rect width="100%" height="100%" fill="#111827"/>', '<style>text{font-family:Arial;fill:#e5e7eb;font-size:14px}.small{font-size:11px;fill:#9ca3af}</style>', '<text x="24" y="28">Virtual camera plan — keyframe position timeline</text>']
    for row, clip in enumerate(camera_plans):
        y = 65 + row * 110
        start, end = float(clip["start"]), float(clip["end"])
        span = max(0.1, end - start)
        lines.append(f'<text x="24" y="{y}">{clip["clipId"]}</text><line x1="145" y1="{y - 5}" x2="1150" y2="{y - 5}" stroke="#4b5563"/>')
        for segment in clip["segments"]:
            x1 = 145 + 1005 * (float(segment["start"]) - start) / span
            x2 = 145 + 1005 * (float(segment["end"]) - start) / span
            color = "#2563eb" if not segment["cameraFrozen"] else "#4b5563"
            lines.append(f'<line x1="{x1:.1f}" y1="{y - 5}" x2="{x2:.1f}" y2="{y - 5}" stroke="{color}" stroke-width="8"/>')
            for keyframe in segment["keyframes"]:
                key_x = 145 + 1005 * (float(keyframe["time"]) - start) / span
                lines.append(f'<circle cx="{key_x:.1f}" cy="{y - 5}" r="5" fill="#f59e0b"/><text class="small" x="{key_x:.1f}" y="{y + 16}">x={keyframe["position"]["x"]:.0f}, z={keyframe["position"]["zoom"]:.3f}</text>')
        lines.append(f'<text class="small" x="145" y="{y + 38}">blue = eased planned motion; gray = frozen; orange = keyframe</text>')
    return "".join(lines) + "</svg>"


def run(context):
    plans = json.loads((context["temp_dir"] / "crop_coords.json").read_text(encoding="utf-8")).get("plans", [])
    identities = json.loads((context["temp_dir"] / "subject_identities.json").read_text(encoding="utf-8"))
    scenes = json.loads((context["temp_dir"] / "scene_cuts.json").read_text(encoding="utf-8")).get("scenes", [])
    camera_plans = []
    for composition in plans:
        segments = [_plan_segment(composition, segment, identities) for segment in _scene_segments(composition, scenes)]
        camera_plans.append({"clipId": composition["clipId"], "start": composition["start"], "end": composition["end"], "sourceComposition": {key: composition[key] for key in ("x", "y", "width", "height", "resolvedLayout")}, "segments": segments})
    payload = {"method": "identity-aware-virtual-camera-planner", "schemaVersion": "1.0", "rendererConsumed": False, "limits": {"maxHorizontalVelocity": MAX_HORIZONTAL_VELOCITY, "maxVerticalVelocity": MAX_VERTICAL_VELOCITY, "maxZoomVelocity": MAX_ZOOM_VELOCITY}, "plans": camera_plans}
    (context["temp_dir"] / "camera_plan.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    (context["temp_dir"] / "camera_plan_diagnostics.svg").write_text(_diagnostic_svg(camera_plans), encoding="utf-8")
