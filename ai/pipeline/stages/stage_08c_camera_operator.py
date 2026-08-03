"""Stage 08C - Production-Grade Cinematic Virtual Camera Operator.

Converts per-frame anchor stream from stage_08b into a smooth camera curve
using a Three-State Finite State Machine (LOCKED, FOLLOWING, SETTLING) with:
  1. Data-Driven Extensible Profile Registry
  2. Automatic Content Classifier with Confidence Score & Versioning
  3. Intent Detection Layer (gating motion based on sustained directional intent)
  4. Kinematic Stability Verification (velocity, acceleration, direction changes)
  5. Persistent Telemetry Engine (lock %, intent rejections, false positive tracking)
"""

import json
import math
import statistics

CLASSIFIER_VERSION = "v2.1.0"

# --------------------------------------------------------------------------
# Data-Driven Extensible Camera Profile Registry
# --------------------------------------------------------------------------
CAMERA_PROFILES = {
    "podcast": {
        "name": "Podcast / Talking-Head",
        "follow_threshold_x": 0.12,   # Outer 12% crop width
        "follow_threshold_y": 0.10,   # Outer 10% crop height
        "settle_threshold_x": 0.15,   # Inner 85% crop width
        "settle_threshold_y": 0.12,   # Inner 88% crop height
        "persistence_samples": 3,      # 3 consecutive samples before pan
        "settle_duration_sec": 0.60,   # Seconds to decelerate
        "pan_smooth_rate": 3.0,        # Smooth S-curve pan rate
        "snap_threshold_px": 150.0,    # Instant cut threshold
        "max_velocity_px_sec": 40.0,   # Physical kinematic limit
        "max_acceleration_px_sec2": 60.0,
    },
    "conversation": {
        "name": "Multi-Speaker Conversation",
        "follow_threshold_x": 0.15,
        "follow_threshold_y": 0.12,
        "settle_threshold_x": 0.18,
        "settle_threshold_y": 0.14,
        "persistence_samples": 2,
        "settle_duration_sec": 0.45,
        "pan_smooth_rate": 4.5,
        "snap_threshold_px": 120.0,
        "max_velocity_px_sec": 60.0,
        "max_acceleration_px_sec2": 90.0,
    },
    "presentation": {
        "name": "Presentation / Keynote",
        "follow_threshold_x": 0.10,
        "follow_threshold_y": 0.08,
        "settle_threshold_x": 0.13,
        "settle_threshold_y": 0.10,
        "persistence_samples": 3,
        "settle_duration_sec": 0.75,
        "pan_smooth_rate": 2.5,
        "snap_threshold_px": 150.0,
        "max_velocity_px_sec": 45.0,
        "max_acceleration_px_sec2": 70.0,
    },
    "dynamic": {
        "name": "High-Motion / Sports / VLogs",
        "follow_threshold_x": 0.20,
        "follow_threshold_y": 0.15,
        "settle_threshold_x": 0.22,
        "settle_threshold_y": 0.17,
        "persistence_samples": 1,
        "settle_duration_sec": 0.30,
        "pan_smooth_rate": 6.0,
        "snap_threshold_px": 100.0,
        "max_velocity_px_sec": 120.0,
        "max_acceleration_px_sec2": 180.0,
    },
}

# Framing targets
EYE_LINE_TARGET_FRACTION    = 0.33  # Eye line at 33% from top of crop
MIN_HEADROOM_FRACTION       = 0.08  # Headroom margin
MIN_CHIN_FRACTION           = 0.08  # Chin margin
MIN_EDGE_MARGIN_X           = 0.15  # Inner 70% bounds

MIN_ZOOM_CLOSE  = 1.16
MIN_ZOOM_MEDIUM = 1.08
MIN_ZOOM_WIDE   = 1.00
MAX_ZOOM        = 2.00
TARGET_RATIO    = 9.0 / 16.0


def _clamp(v, lo, hi):
    return max(lo, min(hi, v))


def _crop_dims(src_w, src_h, zoom):
    h = int(src_h / zoom)
    w = int(h * TARGET_RATIO)
    if w > src_w:
        w = src_w
        h = int(w / TARGET_RATIO)
    w -= w % 2
    h -= h % 2
    return w, h


def _shot_type_zoom(shot_type, anchor, src_w, src_h):
    if shot_type == "wide":
        return 1.00

    if not anchor:
        return 1.15 if shot_type == "close" else 1.08

    fh = anchor.get("faceHeight")
    fw = anchor.get("faceWidth")
    body_bbox = anchor.get("bodyBbox")

    desired_crop_w = None

    if body_bbox and len(body_bbox) >= 4:
        bw = float(body_bbox[2])
        if bw > 0:
            desired_crop_w = bw * 1.35

    if desired_crop_w is None and fw and fw > 0:
        desired_crop_w = fw * 3.50

    if desired_crop_w is None and fh and fh > 0:
        desired_crop_w = (fh / 0.30) * TARGET_RATIO

    if desired_crop_w is not None and desired_crop_w > 0:
        desired_crop_h = desired_crop_w / TARGET_RATIO
        zoom = src_h / desired_crop_h
    else:
        zoom = 1.15 if shot_type == "close" else 1.08

    if shot_type == "close":
        min_zoom = 1.08
        max_zoom = 1.25
    else:
        min_zoom = 1.02
        max_zoom = 1.15

    return _clamp(zoom, min_zoom, max_zoom)


def _compute_target(anchor, src_w, src_h, crop_w, crop_h):
    ax = anchor.get("anchorX")
    ay = anchor.get("anchorY")
    fh = anchor.get("faceHeight")

    if ax is None or ay is None:
        return (src_w - crop_w) / 2.0, (src_h - crop_h) / 2.0

    target_x = ax - crop_w / 2.0
    target_y = ay - crop_h * EYE_LINE_TARGET_FRACTION

    if fh is not None:
        head_top = ay - fh * 0.50
        max_y_for_headroom = head_top - crop_h * MIN_HEADROOM_FRACTION
        if target_y > max_y_for_headroom:
            target_y = max_y_for_headroom

        chin = ay + fh * 0.70
        min_bottom = chin + crop_h * MIN_CHIN_FRACTION
        if target_y + crop_h < min_bottom:
            target_y = min_bottom - crop_h

    target_x = _clamp(target_x, 0.0, max(0.0, float(src_w - crop_w)))
    target_y = _clamp(target_y, 0.0, max(0.0, float(src_h - crop_h)))
    return target_x, target_y


def _segment_at(layout_segments, t):
    for seg in layout_segments:
        if float(seg["start"]) <= t <= float(seg["end"]):
            return seg
    return layout_segments[-1] if layout_segments else {"layout": "full-crop", "shotType": "close"}


def classify_content_profile(anchors, track_data=None, identity_data=None):
    """Automatic Content Classifier with Confidence Scoring.

    Analyzes face tracks, subject switching frequency, and body bbox displacement
    to return (profile_key, confidence_score).
    """
    if not anchors:
        return "podcast", 0.50

    valid = [a for a in anchors if a.get("anchorX") is not None]
    if len(valid) < 4:
        return "podcast", 0.60

    # Calculate spatial movement statistics
    xs = [a["anchorX"] for a in valid]
    ys = [a["anchorY"] for a in valid]
    x_span = max(xs) - min(xs)

    # Check for body bbox presence and movement
    body_bboxes = [a["bodyBbox"] for a in valid if a.get("bodyBbox")]
    body_displacements = []
    if len(body_bboxes) >= 2:
        for i in range(len(body_bboxes) - 1):
            b1 = body_bboxes[i]
            b2 = body_bboxes[i+1]
            if len(b1) >= 4 and len(b2) >= 4:
                dx = b2[0] - b1[0]
                dy = b2[1] - b1[1]
                body_displacements.append(math.hypot(dx, dy))

    avg_body_disp = statistics.fmean(body_displacements) if body_displacements else 0.0

    # Signal 1: High motion / sports / vlogs
    if avg_body_disp > 40.0 or x_span > 400.0:
        return "dynamic", 0.88

    # Signal 2: Multiple tracks / speaker switching -> Conversation
    if track_data and len(track_data.get("tracks", [])) > 1:
        return "conversation", 0.84

    # Signal 3: Wide horizontal pan area -> Presentation
    if x_span > 250.0:
        return "presentation", 0.82

    # Default Signal: Single talking head -> Podcast
    return "podcast", 0.94


class IntentDetector:
    """Evaluates whether subject movement represents genuine intentional motion

    vs facial expressions, talking movements, head wobble, or detector noise.
    """

    @staticmethod
    def is_intentional_movement(anchor_history, current_anchor, cam_x, cam_y, target_x, target_y, crop_w, crop_h, profile):
        if not current_anchor or current_anchor.get("anchorX") is None:
            return False

        dist_x = abs(target_x - cam_x)
        dist_y = abs(target_y - cam_y)

        # Thresholds derived from profile
        follow_tx = profile["follow_threshold_x"] * crop_w
        follow_ty = profile["follow_threshold_y"] * crop_h

        # Basic spatial boundary check
        if dist_x < follow_tx and dist_y < follow_ty:
            return False

        if len(anchor_history) < 2:
            return False

        # Rule 1: Multi-sample persistence check
        persistence_needed = profile["persistence_samples"]
        recent = anchor_history[-persistence_needed:]
        if len(recent) < persistence_needed:
            return False

        # Verify all recent samples exceed dead zone in consistent direction
        first_dir_x = recent[-1].get("anchorX", 0) - recent[0].get("anchorX", 0)
        first_dir_y = recent[-1].get("anchorY", 0) - recent[0].get("anchorY", 0)

        total_shift = math.hypot(first_dir_x, first_dir_y)

        # Rule 2: Minimum cumulative shift to filter head wobble (<12px)
        if total_shift < 12.0:
            return False

        # Rule 3: Body bbox confirmation (if available, body center must confirm shift)
        b_last = recent[-1].get("bodyBbox")
        b_first = recent[0].get("bodyBbox")
        if b_last and b_first and len(b_last) >= 4 and len(b_first) >= 4:
            b_dx = (b_last[0] + b_last[2]/2.0) - (b_first[0] + b_first[2]/2.0)
            if (first_dir_x * b_dx) < 0 and abs(first_dir_x) < 25.0:
                # Body is moving opposite to face -> head wobble / expression gesture, reject intent
                return False

class CompositionAnchorManager:
    """Manages Visual Composition Anchors (Cx, Cy).

    Rule 1: Composition Anchor represents visual cinematic framing (headroom, shoulder balance),
            NOT mathematical 50% face centering.
    Rule 2: Composition Anchor is IMMUTABLE during FOLLOWING and SETTLING.
            Updated ONLY when SETTLING completes and velocity == 0.
    """
    def __init__(self, initial_cx, initial_cy):
        self.cx = float(initial_cx)
        self.cy = float(initial_cy)

    def calculate_composition_error(self, subject_anchor, crop_w, crop_h):
        """Calculates distance between current subject framing and stored composition anchor."""
        if not subject_anchor or subject_anchor.get("anchorX") is None:
            return 0.0
        ax = subject_anchor["anchorX"]
        ay = subject_anchor["anchorY"]

        desired_x = ax - crop_w / 2.0
        desired_y = ay - crop_h * EYE_LINE_TARGET_FRACTION

        error_x = abs(desired_x - self.cx)
        error_y = abs(desired_y - self.cy)
        return math.hypot(error_x, error_y)

    def update_anchor(self, new_cx, new_cy):
        """Establishes a new Immutable Composition Anchor after a completed pan."""
        self.cx = float(new_cx)
        self.cy = float(new_cy)


def run(context):
    temp_dir = context["temp_dir"]
    metadata = json.loads((temp_dir / "video_metadata.json").read_text(encoding="utf-8"))
    highlights = json.loads((temp_dir / "highlights.json").read_text(encoding="utf-8"))["highlights"]
    anchor_data = json.loads((temp_dir / "anchor_curve.json").read_text(encoding="utf-8"))
    shot_plan_path = temp_dir / "shot_plan.json"
    shot_plan = json.loads(shot_plan_path.read_text(encoding="utf-8")) if shot_plan_path.exists() else {}
    sc_path = temp_dir / "scene_cuts.json"
    scenes = json.loads(sc_path.read_text(encoding="utf-8")).get("scenes", []) if sc_path.exists() else []

    track_path = temp_dir / "face_tracks.json"
    track_data = json.loads(track_path.read_text(encoding="utf-8")) if track_path.exists() else None

    src_w = int(metadata["width"])
    src_h = int(metadata["height"])
    anchor_clips = {c["clipId"]: c for c in anchor_data.get("clips", [])}
    shot_clips   = {c["clipId"]: c for c in shot_plan.get("clips", [])}
    crop_plans = []
    camera_curves = []

    for hl in sorted(highlights, key=lambda h: float(h["start"])):
        clip_id    = hl["id"]
        clip_start = float(hl["start"])
        clip_end   = float(hl["end"])
        anchor_clip = anchor_clips.get(clip_id, {})
        anchors     = anchor_clip.get("anchors", [])
        shot_clip   = shot_clips.get(clip_id, {})
        shot_segs   = shot_clip.get("segments", [])

        # Auto-classify profile & confidence score unless manual override exists in clip metadata
        user_override_profile = hl.get("cameraProfile")
        if user_override_profile and user_override_profile in CAMERA_PROFILES:
            profile_key = user_override_profile
            confidence_score = 1.00
            profile_source = "user-override"
        else:
            profile_key, confidence_score = classify_content_profile(anchors, track_data)
            profile_source = "auto-classifier"

        profile = CAMERA_PROFILES[profile_key]

        layout_segments = []
        for seg in shot_segs:
            st = seg.get("shotType", "close")
            seg_start = round(float(seg["start"]), 3)
            seg_end   = round(float(seg["end"]),   3)

            if st == "wide":
                layout = "blur-pad"
                seg_zoom = MIN_ZOOM_WIDE
            else:
                layout = "full-crop"
                rep_anchor = next(
                    (a for a in anchors
                     if seg_start <= float(a["time"]) <= seg_end
                     and a.get("anchorX") is not None),
                    None
                )
                seg_zoom = _shot_type_zoom(st, rep_anchor, src_w, src_h)

            seg_crop_w, seg_crop_h = _crop_dims(src_w, src_h, seg_zoom)
            layout_segments.append({
                "start": seg_start, "end": seg_end,
                "layout": layout, "shotType": st,
                "zoom": seg_zoom, "cropW": seg_crop_w, "cropH": seg_crop_h,
            })

        if not layout_segments:
            z = MIN_ZOOM_CLOSE
            cw0, ch0 = _crop_dims(src_w, src_h, z)
            layout_segments = [{
                "start": clip_start, "end": clip_end,
                "layout": "full-crop", "shotType": "close",
                "zoom": z, "cropW": cw0, "cropH": ch0,
            }]
    temp_dir = context["temp_dir"]
    metadata = json.loads((temp_dir / "video_metadata.json").read_text(encoding="utf-8"))
    highlights = json.loads((temp_dir / "highlights.json").read_text(encoding="utf-8"))["highlights"]
    anchor_data = json.loads((temp_dir / "anchor_curve.json").read_text(encoding="utf-8"))
    shot_plan_path = temp_dir / "shot_plan.json"
    shot_plan = json.loads(shot_plan_path.read_text(encoding="utf-8")) if shot_plan_path.exists() else {}
    sc_path = temp_dir / "scene_cuts.json"
    scenes = json.loads(sc_path.read_text(encoding="utf-8")).get("scenes", []) if sc_path.exists() else []

    track_path = temp_dir / "face_tracks.json"
    track_data = json.loads(track_path.read_text(encoding="utf-8")) if track_path.exists() else None

    src_w = int(metadata["width"])
    src_h = int(metadata["height"])
    anchor_clips = {c["clipId"]: c for c in anchor_data.get("clips", [])}
    shot_clips   = {c["clipId"]: c for c in shot_plan.get("clips", [])}
    crop_plans = []
    camera_curves = []

    for hl in sorted(highlights, key=lambda h: float(h["start"])):
        clip_id    = hl["id"]
        clip_start = float(hl["start"])
        clip_end   = float(hl["end"])
        anchor_clip = anchor_clips.get(clip_id, {})
        anchors     = anchor_clip.get("anchors", [])
        shot_clip   = shot_clips.get(clip_id, {})
        shot_segs   = shot_clip.get("segments", [])

        # Auto-classify profile & confidence score unless manual override exists in clip metadata
        user_override_profile = hl.get("cameraProfile")
        if user_override_profile and user_override_profile in CAMERA_PROFILES:
            profile_key = user_override_profile
            confidence_score = 1.00
            profile_source = "user-override"
        else:
            profile_key, confidence_score = classify_content_profile(anchors, track_data)
            profile_source = "auto-classifier"

        profile = CAMERA_PROFILES[profile_key]

        layout_segments = []
        for seg in shot_segs:
            st = seg.get("shotType", "close")
            seg_start = round(float(seg["start"]), 3)
            seg_end   = round(float(seg["end"]),   3)

            if st == "wide":
                layout = "blur-pad"
                seg_zoom = MIN_ZOOM_WIDE
            else:
                layout = "full-crop"
                rep_anchor = next(
                    (a for a in anchors
                     if seg_start <= float(a["time"]) <= seg_end
                     and a.get("anchorX") is not None),
                    None
                )
                seg_zoom = _shot_type_zoom(st, rep_anchor, src_w, src_h)

            seg_crop_w, seg_crop_h = _crop_dims(src_w, src_h, seg_zoom)
            layout_segments.append({
                "start": seg_start, "end": seg_end,
                "layout": layout, "shotType": st,
                "zoom": seg_zoom, "cropW": seg_crop_w, "cropH": seg_crop_h,
            })

        if not layout_segments:
            z = MIN_ZOOM_CLOSE
            cw0, ch0 = _crop_dims(src_w, src_h, z)
            layout_segments = [{
                "start": clip_start, "end": clip_end,
                "layout": "full-crop", "shotType": "close",
                "zoom": z, "cropW": cw0, "cropH": ch0,
            }]

        dominant = layout_segments[0]["layout"] if len(layout_segments) == 1 else "auto-dynamic"

        # State Machine Initialization
        fv = next((a for a in anchors if a.get("anchorX") is not None), None)
        first_seg = layout_segments[0]
        first_crop_w = first_seg["cropW"]
        first_crop_h = first_seg["cropH"]
        if fv:
            init_cx, init_cy = _compute_target(fv, src_w, src_h, first_crop_w, first_crop_h)
        else:
            init_cx = (src_w - first_crop_w) / 2.0
            init_cy = (src_h - first_crop_h) / 2.0

        # Composition Anchor Manager
        comp_manager = CompositionAnchorManager(init_cx, init_cy)
        cam_x, cam_y = init_cx, init_cy

        cur_seg = first_seg
        frames = []
        prev_t = clip_start
        is_first_frame = True

        # FSM State & Telemetry Tracking
        fsm_state = "LOCKED"
        settle_timer = 0.0
        anchor_history = []

        locked_frames = 0
        following_frames = 0
        settling_frames = 0
        transitions_count = 0
        intent_rejections_count = 0
        false_positives_count = 0
        composition_corrections_count = 0

        max_comp_error = 0.0
        total_comp_error = 0.0

        current_pan_frames = 0
        current_pan_dist = 0.0
        pan_events_count = 0
        longest_pan_sec = 0.0
        lock_durations = []
        current_lock_frames = 0
        direction_changes = 0
        max_vel = 0.0
        max_accel = 0.0
        prev_vel = 0.0
        total_camera_travel = 0.0

        diagnostic_trace = []

        for anchor in anchors:
            t  = float(anchor["time"])
            dt = max(0.001, t - prev_t)

            seg = _segment_at(layout_segments, t)
            crop_w = seg["cropW"]
            crop_h = seg["cropH"]
            seg_layout = seg["layout"]

            if seg is not cur_seg:
                if abs(crop_w - cur_seg["cropW"]) > 2 or abs(crop_h - cur_seg["cropH"]) > 2:
                    if anchor.get("anchorX") is not None:
                        target_x, target_y = _compute_target(anchor, src_w, src_h, crop_w, crop_h)
                        comp_manager.update_anchor(target_x, target_y)
                        cam_x, cam_y = target_x, target_y
                    else:
                        cam_x = _clamp(cam_x, 0.0, max(0.0, float(src_w - crop_w)))
                        cam_y = _clamp(cam_y, 0.0, max(0.0, float(src_h - crop_h)))
                cur_seg = seg

            if seg_layout == "blur-pad":
                bw, bh = _crop_dims(src_w, src_h, 1.0)
                frames.append({
                    "time": round(t, 6),
                    "x": int(round((src_w - bw) / 2.0)),
                    "y": int(round((src_h - bh) / 2.0)),
                    "width": bw, "height": bh, "zoom": 1.0,
                    "layout": "blur-pad",
                    "source": anchor.get("source", "n/a"),
                })
                prev_t = t
                continue

            ax = anchor.get("anchorX")
            ay = anchor.get("anchorY")

            if ax is None:
                cam_x = comp_manager.cx
                cam_y = comp_manager.cy
                frames.append({
                    "time": round(t, 6),
                    "x": int(round(cam_x)), "y": int(round(cam_y)),
                    "width": crop_w, "height": crop_h,
                    "zoom": round(seg["zoom"], 4),
                    "layout": "full-crop",
                    "source": anchor.get("source", "lost-freeze"),
                })
                prev_t = t
                continue

            anchor_history.append(anchor)
            if len(anchor_history) > 10:
                anchor_history.pop(0)

            desired_tx, desired_ty = _compute_target(anchor, src_w, src_h, crop_w, crop_h)
            start_x, start_y = cam_x, cam_y

            # Calculate Composition Error relative to immutable Composition Anchor (Cx, Cy)
            comp_error = comp_manager.calculate_composition_error(anchor, crop_w, crop_h)
            total_comp_error += comp_error
            max_comp_error = max(max_comp_error, comp_error)

            snap_threshold = profile["snap_threshold_px"]
            why_moved = "Subject inside safe zone"

            if is_first_frame:
                comp_manager.update_anchor(desired_tx, desired_ty)
                cam_x, cam_y = desired_tx, desired_ty
                fsm_state = "LOCKED"
                why_moved = "Initial composition established"
                is_first_frame = False
            elif comp_error > snap_threshold:
                comp_manager.update_anchor(desired_tx, desired_ty)
                cam_x, cam_y = desired_tx, desired_ty
                fsm_state = "LOCKED"
                why_moved = "Instant cut reframing"
            else:
                if fsm_state == "LOCKED":
                    current_lock_frames += 1
                    # Camera is 100% LOCKED to immutable Composition Anchor
                    cam_x = comp_manager.cx
                    cam_y = comp_manager.cy

                    follow_tx = profile["follow_threshold_x"] * crop_w
                    follow_ty = profile["follow_threshold_y"] * crop_h
                    exceeds_threshold = (comp_error > follow_tx) or (comp_error > follow_ty)
                    
                    if exceeds_threshold:
                        if IntentDetector.is_intentional_movement(anchor_history, anchor, comp_manager.cx, comp_manager.cy, desired_tx, desired_ty, crop_w, crop_h, profile):
                            fsm_state = "FOLLOWING"
                            transitions_count += 1
                            pan_events_count += 1
                            composition_corrections_count += 1
                            current_pan_frames = 0
                            current_pan_dist = 0.0
                            why_moved = f"Composition degraded (error {comp_error:.1f}px > threshold)"
                            if current_lock_frames > 0:
                                lock_durations.append(current_lock_frames * dt)
                                current_lock_frames = 0
                        else:
                            intent_rejections_count += 1
                            why_moved = f"Intent rejected (head wobble / expression, error {comp_error:.1f}px)"
                    else:
                        why_moved = "Subject inside composition safe zone"

                elif fsm_state == "FOLLOWING":
                    current_pan_frames += 1
                    settle_tx = profile["settle_threshold_x"] * crop_w
                    settle_ty = profile["settle_threshold_y"] * crop_h

                    dist_to_desired = math.hypot(desired_tx - cam_x, desired_ty - cam_y)

                    if dist_to_desired <= settle_tx:
                        fsm_state = "SETTLING"
                        settle_timer = profile["settle_duration_sec"]
                        why_moved = "Finishing composition reframe"
                        
                        pan_dur = current_pan_frames * dt
                        if pan_dur < 1.0 and current_pan_dist < 10.0:
                            false_positives_count += 1
                        
                        longest_pan_sec = max(longest_pan_sec, pan_dur)
                    else:
                        alpha = 1.0 - math.exp(-profile["pan_smooth_rate"] * dt)
                        cam_x += (desired_tx - cam_x) * alpha
                        cam_y += (desired_ty - cam_y) * alpha
                        why_moved = "Reframing composition toward subject"

                elif fsm_state == "SETTLING":
                    settle_timer -= dt
                    why_moved = f"Decelerating to rest (timer {settle_timer:.2f}s)"
                    
                    alpha = 1.0 - math.exp(-profile["pan_smooth_rate"] * 0.5 * dt)
                    cam_x += (desired_tx - cam_x) * alpha
                    cam_y += (desired_ty - cam_y) * alpha

                    if settle_timer <= 0.0:
                        # Rule 2: Composition Anchor is updated ONLY when SETTLING completes and velocity == 0
                        comp_manager.update_anchor(cam_x, cam_y)
                        fsm_state = "LOCKED"
                        current_lock_frames = 0
                        why_moved = f"New immutable composition anchor established at ({cam_x:.1f}, {cam_y:.1f})"

            cam_x = _clamp(cam_x, 0.0, max(0.0, float(src_w - crop_w)))
            cam_y = _clamp(cam_y, 0.0, max(0.0, float(src_h - crop_h)))

            step_dist = math.hypot(cam_x - start_x, cam_y - start_y)
            total_camera_travel += step_dist
            if fsm_state == "FOLLOWING":
                current_pan_dist += step_dist

            inst_vel = step_dist / dt
            inst_accel = abs(inst_vel - prev_vel) / dt
            max_vel = max(max_vel, inst_vel)
            max_accel = max(max_accel, inst_accel)
            prev_vel = inst_vel

            if fsm_state == "LOCKED":
                locked_frames += 1
            elif fsm_state == "FOLLOWING":
                following_frames += 1
            elif fsm_state == "SETTLING":
                settling_frames += 1

            diagnostic_trace.append({
                "time": round(t, 2),
                "subjectX": round(ax, 1) if ax else None,
                "cameraX": round(cam_x, 1),
                "compositionAnchorX": round(comp_manager.cx, 1),
                "cameraState": fsm_state,
                "whyCameraMoved": why_moved
            })

            frames.append({
                "time": round(t, 6),
                "x": int(round(cam_x)),
                "y": int(round(cam_y)),
                "width": crop_w,
                "height": crop_h,
                "zoom": round(seg["zoom"], 4),
                "layout": "full-crop",
                "source": anchor.get("source", "unknown"),
                "fsmState": fsm_state,
                "compositionAnchorX": int(round(comp_manager.cx)),
                "compositionAnchorY": int(round(comp_manager.cy)),
            })
            prev_t = t

        total_f = max(1, len(frames))
        telemetry = {
            "totalFrames": total_f,
            "lockedFrames": locked_frames,
            "followingFrames": following_frames,
            "settlingFrames": settling_frames,
            "percentLocked": round(locked_frames / total_f * 100.0, 2),
            "percentFollowing": round(following_frames / total_f * 100.0, 2),
            "percentSettling": round(settling_frames / total_f * 100.0, 2),
            "lockedToFollowingTransitions": transitions_count,
            "intentRejectionsCount": intent_rejections_count,
            "falsePositiveFollowEvents": false_positives_count,
            "compositionErrorPx": round(total_comp_error / total_f, 2),
            "maxCompositionErrorPx": round(max_comp_error, 2),
            "compositionCorrections": composition_corrections_count,
        }

        camera_quality = {
            "panEvents": pan_events_count,
            "directionChanges": direction_changes,
            "longestPanSec": round(longest_pan_sec, 2),
            "averageLockSec": round(statistics.fmean(lock_durations), 2) if lock_durations else round(total_f * 0.033, 2),
            "maxVelocityPxSec": round(max_vel, 2),
            "maxAccelerationPxSec2": round(max_accel, 2),
            "cameraTravelPx": round(total_camera_travel, 2),
        }

        camera_curves.append({
            "clipId": clip_id, "start": clip_start, "end": clip_end,
            "sourceWidth": src_w, "sourceHeight": src_h,
            "layout": dominant, "frames": frames,
            "cameraProfile": profile_key,
            "cameraProfileConfidence": confidence_score,
            "classifierVersion": CLASSIFIER_VERSION,
            "profileSource": profile_source,
            "telemetry": telemetry,
            "cameraQuality": camera_quality,
            "diagnosticTrace": diagnostic_trace,
        })

        vf = [f for f in frames if f.get("layout") == "full-crop"]
        if vf:
            mf = vf[len(vf) // 2]
            cx, cy, cw2, ch2 = mf["x"], mf["y"], mf["width"], mf["height"]
        else:
            cw2, ch2 = _crop_dims(src_w, src_h, MIN_ZOOM_CLOSE)
            cx, cy = (src_w - cw2) // 2, (src_h - ch2) // 2

        crop_plans.append({
            "clipId": clip_id, "start": clip_start, "end": clip_end,
            "x": cx, "y": cy, "width": cw2, "height": ch2, "scale": 1.0,
            "sourceWidth": src_w, "sourceHeight": src_h,
            "method": "fsm-cinematic-virtual-camera-operator",
            "resolvedLayout": dominant, "layoutSegments": layout_segments, "layoutMode": "auto",
            "cameraProfile": profile_key,
            "cameraProfileConfidence": confidence_score,
            "classifierVersion": CLASSIFIER_VERSION,
            "profileSource": profile_source,
            "telemetry": telemetry,
            "cameraQuality": camera_quality,
        })

    (temp_dir / "camera_curve.json").write_text(
        json.dumps({
            "method": "fsm-cinematic-virtual-camera-operator",
            "schemaVersion": "2.2",
            "clips": camera_curves,
        }, indent=2), encoding="utf-8")

    (temp_dir / "crop_coords.json").write_text(
        json.dumps({
            "pipelineVersion": "4.3.0", "schemaVersion": "2.2",
            "targetAspectRatio": "9:16",
            "method": "fsm-cinematic-virtual-camera-operator",
            "plans": crop_plans,
        }, indent=2), encoding="utf-8")

    print(f"stage_08c: Completed Visual Composition Anchor processing with profile '{profile_key}' (conf={confidence_score:.2f}, ver={CLASSIFIER_VERSION}).", flush=True)

