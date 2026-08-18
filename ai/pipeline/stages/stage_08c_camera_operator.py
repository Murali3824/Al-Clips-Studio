"""Stage 08C - Production-Grade Cinematic Virtual Camera Operator.

Converts per-frame anchor stream from stage_08b into a smooth, composition-first
camera curve using Segment-Level Median Anchoring, Composition Quality Scoring,
and Zero-Velocity Default Locks (v = 0).

Key Architectural Principles:
  1. Default State: v_x = 0, v_y = 0. Camera is 100% frozen during continuous speech.
  2. Segment-Level Median Anchoring: Calculates a single static framing (X_static, Y_static)
     derived from the subject's median position over each scene segment.
  3. Composition Quality Score (Q_comp): Evaluates visual headroom, eye-line, and edge safety.
  4. Human Reframe Decision Engine: Ignores head sway, body movement, and speech gestures.
     Reframing is triggered only on sustained safety envelope breaches (Q_comp < 0.40).
"""

import json
import math
import statistics

CLASSIFIER_VERSION = "v3.0.0"

# --------------------------------------------------------------------------
# Data-Driven Extensible Camera Profile Registry
# --------------------------------------------------------------------------
CAMERA_PROFILES = {
    "podcast": {
        "name": "Podcast / Talking-Head",
        "follow_threshold_x": 0.15,   # Outer 15% crop width
        "follow_threshold_y": 0.12,   # Outer 12% crop height
        "settle_threshold_x": 0.18,   # Inner 82% crop width
        "settle_threshold_y": 0.15,   # Inner 85% crop height
        "persistence_samples": 4,      # 4 consecutive samples before pan
        "settle_duration_sec": 0.60,   # Seconds to decelerate
        "pan_smooth_rate": 3.0,        # Smooth S-curve pan rate
        "snap_threshold_px": 250.0,    # Instant cut threshold
        "max_velocity_px_sec": 40.0,   # Physical kinematic limit
        "max_acceleration_px_sec2": 60.0,
    },
    "conversation": {
        "name": "Multi-Speaker Conversation",
        "follow_threshold_x": 0.18,
        "follow_threshold_y": 0.14,
        "settle_threshold_x": 0.20,
        "settle_threshold_y": 0.16,
        "persistence_samples": 3,
        "settle_duration_sec": 0.45,
        "pan_smooth_rate": 4.5,
        "snap_threshold_px": 220.0,
        "max_velocity_px_sec": 60.0,
        "max_acceleration_px_sec2": 90.0,
    },
    "presentation": {
        "name": "Presentation / Keynote",
        "follow_threshold_x": 0.12,
        "follow_threshold_y": 0.10,
        "settle_threshold_x": 0.15,
        "settle_threshold_y": 0.12,
        "persistence_samples": 4,
        "settle_duration_sec": 0.75,
        "pan_smooth_rate": 2.5,
        "snap_threshold_px": 250.0,
        "max_velocity_px_sec": 45.0,
        "max_acceleration_px_sec2": 70.0,
    },
    "dynamic": {
        "name": "High-Motion / Sports / VLogs",
        "follow_threshold_x": 0.22,
        "follow_threshold_y": 0.18,
        "settle_threshold_x": 0.25,
        "settle_threshold_y": 0.20,
        "persistence_samples": 2,
        "settle_duration_sec": 0.30,
        "pan_smooth_rate": 6.0,
        "snap_threshold_px": 180.0,
        "max_velocity_px_sec": 120.0,
        "max_acceleration_px_sec2": 180.0,
    },
}

# Framing targets
EYE_LINE_TARGET_FRACTION    = 0.33  # Eye line at 33% from top of crop
MIN_HEADROOM_FRACTION       = 0.08  # Headroom margin
MIN_CHIN_FRACTION           = 0.08  # Chin margin
MIN_EDGE_MARGIN_X           = 0.10  # Inner 80% bounds

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


def classify_content_profile(anchors, track_data=None, identity_data=None):
    if not anchors:
        return "podcast", 0.50

    valid = [a for a in anchors if a.get("anchorX") is not None]
    if len(valid) < 4:
        return "podcast", 0.60

    xs = [a["anchorX"] for a in valid]
    x_span = max(xs) - min(xs)

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

    if avg_body_disp > 40.0 or x_span > 400.0:
        return "dynamic", 0.88

    if track_data and len(track_data.get("tracks", [])) > 1:
        return "conversation", 0.84

    if x_span > 250.0:
        return "presentation", 0.82

    return "podcast", 0.94


class CompositionAnalysisEngine:
    """Evaluates visual framing quality on a normalized scale [0.0, 1.0]."""

    @staticmethod
    def compute_quality_score(anchor, cam_x, cam_y, crop_w, crop_h):
        if not anchor or anchor.get("anchorX") is None:
            return 1.00

        ax = float(anchor["anchorX"])
        ay = float(anchor["anchorY"])
        fh = float(anchor.get("faceHeight") or 180.0)

        # 1. Headroom Score
        head_top = ay - fh * 0.50
        desired_head_top = cam_y + crop_h * MIN_HEADROOM_FRACTION
        headroom_diff = abs(head_top - desired_head_top)
        s_headroom = 1.0 - _clamp(headroom_diff / (0.15 * crop_h), 0.0, 1.0)

        # 2. Eyeline Score
        desired_eyeline = cam_y + crop_h * EYE_LINE_TARGET_FRACTION
        eyeline_diff = abs(ay - desired_eyeline)
        s_eyeline = 1.0 - _clamp(eyeline_diff / (0.20 * crop_h), 0.0, 1.0)

        # 3. Edge Margin Score
        min_margin_x = crop_w * MIN_EDGE_MARGIN_X
        if (cam_x + min_margin_x) <= ax <= (cam_x + crop_w - min_margin_x):
            s_edge = 1.0
        else:
            s_edge = 0.0

        q_comp = 0.40 * s_headroom + 0.30 * s_eyeline + 0.30 * s_edge
        return _clamp(q_comp, 0.0, 1.0)

    @staticmethod
    def is_safety_breach(anchor, cam_x, cam_y, crop_w, crop_h):
        if not anchor or anchor.get("anchorX") is None:
            return False

        ax = float(anchor["anchorX"])
        min_x = cam_x + crop_w * 0.10
        max_x = cam_x + crop_w * 0.90
        return (ax < min_x) or (ax > max_x)


class SegmentMedianAnchorEngine:
    """Computes static per-segment median framing coordinates (X_static, Y_static)."""

    @staticmethod
    def compute_segment_static_crop(anchors, scene_cuts, clip_start, clip_end, src_w, src_h, crop_w, crop_h):
        valid = [a for a in anchors if a.get("anchorX") is not None and clip_start <= float(a["time"]) <= clip_end]
        if not valid:
            return (src_w - crop_w) / 2.0, (src_h - crop_h) / 2.0

        med_ax = statistics.median(float(a["anchorX"]) for a in valid)
        med_ay = statistics.median(float(a["anchorY"]) for a in valid)

        dummy_anchor = {"anchorX": med_ax, "anchorY": med_ay, "faceHeight": valid[0].get("faceHeight")}
        return _compute_target(dummy_anchor, src_w, src_h, crop_w, crop_h)


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

        # ------------------------------------------------------------------
        # Cinematic Virtual Camera Operator Execution
        # ------------------------------------------------------------------
        frames = []
        clip_scene_cuts = [float(s["start"]) for s in scenes if clip_start < float(s["start"]) < clip_end]
        
        # Partition clip timeline into distinct scene segments
        scene_boundaries = sorted(list(set([clip_start] + clip_scene_cuts + [clip_end])))
        
        # Precompute per-segment static median crop coordinates
        segment_static_crops = {}
        for idx in range(len(scene_boundaries) - 1):
            s_time = scene_boundaries[idx]
            e_time = scene_boundaries[idx + 1]
            seg_anchors = [a for a in anchors if s_time <= float(a["time"]) <= e_time]
            
            # Use current layout segment crop dims
            rep_t = (s_time + e_time) / 2.0
            cur_layout_seg = next((s for s in layout_segments if float(s["start"]) <= rep_t <= float(s["end"])), layout_segments[0])
            c_w = cur_layout_seg["cropW"]
            c_h = cur_layout_seg["cropH"]
            
            x_stat, y_stat = SegmentMedianAnchorEngine.compute_segment_static_crop(
                seg_anchors, clip_scene_cuts, s_time, e_time, src_w, src_h, c_w, c_h
            )
            segment_static_crops[idx] = (x_stat, y_stat)

        # FSM State & Telemetry Tracking
        fsm_state = "PERFECT_LOCK"
        cam_x, cam_y = segment_static_crops[0]
        cur_seg_idx = 0
        sustained_breach_count = 0

        for anchor in anchors:
            t = float(anchor["time"])
            
            # Find current scene segment index
            seg_idx = 0
            for idx in range(len(scene_boundaries) - 1):
                if scene_boundaries[idx] <= t <= scene_boundaries[idx + 1]:
                    seg_idx = idx
                    break

            cur_layout_seg = next((s for s in layout_segments if float(s["start"]) <= t <= float(s["end"])), layout_segments[0])
            crop_w = cur_layout_seg["cropW"]
            crop_h = cur_layout_seg["cropH"]
            seg_layout = cur_layout_seg["layout"]

            if seg_layout == "blur-pad":
                bw, bh = _crop_dims(src_w, src_h, 1.0)
                frames.append({
                    "time": round(t, 6),
                    "x": int(round((src_w - bw) / 2.0)),
                    "y": int(round((src_h - bh) / 2.0)),
                    "width": bw, "height": bh, "zoom": 1.0,
                    "layout": "blur-pad",
                    "source": anchor.get("source", "n/a"),
                    "fsm_state": "BLUR_PAD",
                })
                continue

            ax = anchor.get("anchorX")
            ay = anchor.get("anchorY")

            if ax is None:
                frames.append({
                    "time": round(t, 6),
                    "x": int(round(cam_x)), "y": int(round(cam_y)),
                    "width": crop_w, "height": crop_h,
                    "zoom": round(cur_layout_seg["zoom"], 4),
                    "layout": "full-crop",
                    "source": anchor.get("source", "lost-freeze"),
                    "fsm_state": fsm_state,
                })
                continue

            # Scene Transition Check: Reset camera to new segment static median crop
            if seg_idx != cur_seg_idx:
                cam_x, cam_y = segment_static_crops[seg_idx]
                cur_seg_idx = seg_idx
                fsm_state = "PERFECT_LOCK"
                sustained_breach_count = 0

            # Compute Composition Quality Score
            q_comp = CompositionAnalysisEngine.compute_quality_score(anchor, cam_x, cam_y, crop_w, crop_h)
            is_breach = CompositionAnalysisEngine.is_safety_breach(anchor, cam_x, cam_y, crop_w, crop_h)

            if is_breach or q_comp < 0.40:
                sustained_breach_count += 1
            else:
                sustained_breach_count = max(0, sustained_breach_count - 1)

            # Human Reframe Decision Engine: Reframing allowed ONLY on sustained breach (>= 4 consecutive samples)
            if sustained_breach_count >= profile["persistence_samples"]:
                desired_tx, desired_ty = _compute_target(anchor, src_w, src_h, crop_w, crop_h)
                cam_x, cam_y = desired_tx, desired_ty
                fsm_state = "INTENTIONAL_REFRAME"
                sustained_breach_count = 0
            else:
                # Default State: v_x = 0, v_y = 0 (Camera stays 100% frozen at static segment anchor)
                fsm_state = "PERFECT_LOCK"

            interp_mode = "HERMITE" if fsm_state == "INTENTIONAL_REFRAME" else "HOLD"
            frames.append({
                "time": round(t, 6),
                "x": int(round(cam_x)),
                "y": int(round(cam_y)),
                "width": crop_w,
                "height": crop_h,
                "zoom": round(cur_layout_seg["zoom"], 4),
                "layout": "full-crop",
                "source": anchor.get("source", "face"),
                "fsm_state": fsm_state,
                "interp": interp_mode,
                "q_comp": round(q_comp, 3),
            })

        crop_plans.append({
            "clipId": clip_id,
            "start": clip_start, "end": clip_end,
            "layout": dominant,
            "segments": layout_segments,
            "crop": {
                "w": layout_segments[0]["cropW"],
                "h": layout_segments[0]["cropH"],
                "x": frames[0]["x"] if frames else 0,
                "y": frames[0]["y"] if frames else 0,
            },
        })

        camera_curves.append({
            "clipId": clip_id,
            "start": clip_start, "end": clip_end,
            "sourceWidth": src_w, "sourceHeight": src_h,
            "cameraProfile": profile_key,
            "profileName": profile["name"],
            "profileConfidence": round(confidence_score, 4),
            "profileSource": profile_source,
            "frames": frames,
        })

    # Save outputs
    (temp_dir / "crop_coords.json").write_text(json.dumps({"plans": crop_plans}, indent=2), encoding="utf-8")
    (temp_dir / "camera_curve.json").write_text(json.dumps({"clips": camera_curves}, indent=2), encoding="utf-8")

    # Generate telemetry report
    telemetry = {
        "classifier_version": CLASSIFIER_VERSION,
        "total_clips_processed": len(highlights),
    }
    (temp_dir / "camera_operator_telemetry.json").write_text(json.dumps(telemetry, indent=2), encoding="utf-8")
    print(f"stage_08c (Cinematic Virtual Camera Operator): Processed {len(highlights)} clips with zero-velocity static locks.", flush=True)


if __name__ == "__main__":
    import sys
    from pathlib import Path
    if len(sys.argv) > 1:
        run({"temp_dir": Path(sys.argv[1])})
