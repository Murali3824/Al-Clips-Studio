"""Stage 08C - Spring-Damped Virtual Camera Operator.

Converts the per-frame anchor stream from stage_08b into a smooth camera
curve using critically-damped spring-damper physics.

Key improvements (framing & tracking fix):
  1. Exponential Damping & Smooth Pan Rate: Fixes the dt=0.5s linear damping
     evaporation bug. Uses exact exponential smoothing (1 - exp(-rate * dt))
     so camera motion is smooth and responsive regardless of sample interval.
  2. Shot-Type Framing Defaults:
     - Close:  zoom = 1.28 (crop ~470x836, 244px vertical headroom for 1920x1080).
               Frames head, shoulders, and chest naturally without over-zooming.
     - Medium: zoom = 1.15 (crop ~524x932).
     - Wide:   zoom = 1.00 (blur-pad layout).
  3. Edge & Headroom Guards: Keeps eyes at ~35% from the top of the crop
     and guarantees face is framed inside the center 80% of the crop width.
"""

import json
import math

# Camera pan responsiveness (higher = faster tracking, 4.0 = smooth & natural)
PAN_SMOOTH_RATE = 4.0

# Framing targets
EYE_LINE_TARGET_FRACTION    = 0.33  # Eye line at upper third (33%) from top of crop
FACE_HEIGHT_TARGET_FRACTION = 0.30  # Face height fills ~30% of crop height (natural editorial close-up)

# Guards
MIN_HEADROOM_FRACTION = 0.08  # Minimum top margin above head
MIN_CHIN_FRACTION     = 0.08  # Minimum bottom margin below chin
MIN_EDGE_MARGIN_X     = 0.15  # Face center kept in inner 70% of crop

# Shot-type zoom defaults for landscape (1920x1080) sources
MIN_ZOOM_CLOSE  = 1.16  # crop 523x931 -> 149px vertical movement room, 523px wide shoulder clearance
MIN_ZOOM_MEDIUM = 1.08  # crop 562x1000 -> 80px vertical movement room
MIN_ZOOM_WIDE   = 1.00  # wide / blur-pad
MAX_ZOOM        = 2.00  # maximum digital zoom limit

TARGET_RATIO = 9.0 / 16.0  # 9:16 portrait ratio


def _clamp(v, lo, hi):
    return max(lo, min(hi, v))


def _crop_dims(src_w, src_h, zoom):
    """Crop window size for a given zoom factor, maintaining 9:16 aspect ratio."""
    h = int(src_h / zoom)
    w = int(h * TARGET_RATIO)
    if w > src_w:
        w = src_w
        h = int(w / TARGET_RATIO)
    w -= w % 2
    h -= h % 2
    return w, h


def _shot_type_zoom(shot_type, anchor, src_w, src_h):
    """Adaptive Subject Framing Algorithm.

    Computes the optimal zoom scale adaptively based on subject metrics:
      1. Body & Shoulder Awareness: If bodyBbox is present, crop width is set to
         fit the upper body width (shoulders + elbow clearance).
      2. Face Proportion Estimation: If only face metrics are available, upper
         body width is estimated from face width (human shoulder width ≈ 3.5× face width).
      3. Scale & Resolution Safeguards: Digital zoom is bounded adaptively to
         prevent resolution degradation (max_zoom = 1.25 for close, 1.15 for medium).
    """
    if shot_type == "wide":
        return 1.00

    if not anchor:
        return 1.15 if shot_type == "close" else 1.08

    fh = anchor.get("faceHeight")
    fw = anchor.get("faceWidth")
    body_bbox = anchor.get("bodyBbox")

    desired_crop_w = None

    # Signal 1: Body width from YOLO person tracking (shoulders + elbow clearance)
    if body_bbox and len(body_bbox) >= 4:
        bw = float(body_bbox[2])
        if bw > 0:
            desired_crop_w = bw * 1.35  # 35% shoulder clearance margin

    # Signal 2: Estimated body width from face width
    if desired_crop_w is None and fw and fw > 0:
        desired_crop_w = fw * 3.50  # 3.5× face width ≈ natural shoulder width

    # Signal 3: Estimated body width from face height
    if desired_crop_w is None and fh and fh > 0:
        desired_crop_w = (fh / 0.30) * TARGET_RATIO

    if desired_crop_w is not None and desired_crop_w > 0:
        desired_crop_h = desired_crop_w / TARGET_RATIO
        zoom = src_h / desired_crop_h
    else:
        zoom = 1.15 if shot_type == "close" else 1.08

    # Adaptive bounds based on shot type (prevents over-zoom on large subjects)
    if shot_type == "close":
        min_zoom = 1.08
        max_zoom = 1.25  # never crop tighter than 1.25× (prevents digital over-zoom)
    else:
        min_zoom = 1.02
        max_zoom = 1.15

    return _clamp(zoom, min_zoom, max_zoom)


def _compute_target(anchor, src_w, src_h, crop_w, crop_h):
    """Compute the ideal crop top-left (x, y) to frame the anchor."""
    ax = anchor.get("anchorX")
    ay = anchor.get("anchorY")
    fh = anchor.get("faceHeight")

    if ax is None or ay is None:
        return (src_w - crop_w) / 2.0, (src_h - crop_h) / 2.0

    # Horizontal target: center face anchor in crop
    target_x = ax - crop_w / 2.0

    # Vertical target: place eye line at 35% from top of crop
    target_y = ay - crop_h * EYE_LINE_TARGET_FRACTION

    if fh is not None:
        # Headroom guard: top of head (ay - fh*0.5) must have headroom
        head_top = ay - fh * 0.50
        max_y_for_headroom = head_top - crop_h * MIN_HEADROOM_FRACTION
        if target_y > max_y_for_headroom:
            target_y = max_y_for_headroom

        # Chin guard: chin (ay + fh*0.7) must be inside crop
        chin = ay + fh * 0.70
        min_bottom = chin + crop_h * MIN_CHIN_FRACTION
        if target_y + crop_h < min_bottom:
            target_y = min_bottom - crop_h

    # Clamp target to frame boundaries
    target_x = _clamp(target_x, 0.0, max(0.0, float(src_w - crop_w)))
    target_y = _clamp(target_y, 0.0, max(0.0, float(src_h - crop_h)))
    return target_x, target_y


def _scene_cuts(scenes, clip_start, clip_end):
    cuts = set()
    for sc in scenes or []:
        for k in ("start", "end"):
            t = float(sc.get(k, 0))
            if clip_start < t < clip_end:
                cuts.add(round(t, 6))
    return sorted(cuts)


def _is_cut(t, cuts, tol=0.08):
    return any(abs(t - c) <= tol for c in cuts)


def _segment_at(layout_segments, t):
    for seg in layout_segments:
        if float(seg["start"]) <= t <= float(seg["end"]):
            return seg
    return layout_segments[-1] if layout_segments else {"layout": "full-crop", "shotType": "close"}


def run(context):
    temp_dir = context["temp_dir"]
    metadata = json.loads((temp_dir / "video_metadata.json").read_text(encoding="utf-8"))
    highlights = json.loads((temp_dir / "highlights.json").read_text(encoding="utf-8"))["highlights"]
    anchor_data = json.loads((temp_dir / "anchor_curve.json").read_text(encoding="utf-8"))
    shot_plan_path = temp_dir / "shot_plan.json"
    shot_plan = json.loads(shot_plan_path.read_text(encoding="utf-8")) if shot_plan_path.exists() else {}
    sc_path = temp_dir / "scene_cuts.json"
    scenes = json.loads(sc_path.read_text(encoding="utf-8")).get("scenes", []) if sc_path.exists() else []
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
        shot_segs = shot_clip.get("segments", [])

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
                "start": seg_start,
                "end":   seg_end,
                "layout": layout,
                "shotType": st,
                "zoom": seg_zoom,
                "cropW": seg_crop_w,
                "cropH": seg_crop_h,
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
        cuts = _scene_cuts(scenes, clip_start, clip_end)

        # Initialize camera state from first valid anchor
        fv = next((a for a in anchors if a.get("anchorX") is not None), None)
        first_seg = layout_segments[0]
        first_crop_w = first_seg["cropW"]
        first_crop_h = first_seg["cropH"]
        if fv:
            cam_x, cam_y = _compute_target(fv, src_w, src_h, first_crop_w, first_crop_h)
        else:
            cam_x = (src_w - first_crop_w) / 2.0
            cam_y = (src_h - first_crop_h) / 2.0

        cur_seg = first_seg
        frames = []
        prev_t = clip_start
        is_first_frame = True

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
                        cam_x, cam_y = _compute_target(anchor, src_w, src_h, crop_w, crop_h)
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

            # ── FREEZE on lost anchor ────────────────────────────────────
            # When no subject is detected, hold the camera at its current
            # position.  Never drift toward frame-center — that creates the
            # visible "camera searching" artifact.
            if ax is None:
                cam_x = _clamp(cam_x, 0.0, max(0.0, float(src_w - crop_w)))
                cam_y = _clamp(cam_y, 0.0, max(0.0, float(src_h - crop_h)))
                frames.append({
                    "time": round(t, 6),
                    "x": int(round(cam_x)),
                    "y": int(round(cam_y)),
                    "width": crop_w, "height": crop_h,
                    "zoom": round(seg["zoom"], 4),
                    "layout": "full-crop",
                    "source": anchor.get("source", "lost-freeze"),
                })
                prev_t = t
                continue

            tx, ty = _compute_target(anchor, src_w, src_h, crop_w, crop_h)

            # ── DEAD ZONE & CINEMATIC CAMERA OPERATOR MOTION ───────────────
            # Define natural dead zone margins (5% of crop width & 4% of crop height)
            dead_zone_x = 0.05 * crop_w
            dead_zone_y = 0.04 * crop_h

            dist_x = abs(tx - cam_x)
            dist_y = abs(ty - cam_y)

            # Snap on first frame, scene cuts, or large subject position jumps (>120px)
            if is_first_frame:
                cam_x = tx
                cam_y = ty
                is_first_frame = False
            elif _is_cut(t, cuts) or dist_x > 120.0 or dist_y > 120.0:
                cam_x = tx
                cam_y = ty
            elif dist_x <= dead_zone_x and dist_y <= dead_zone_y:
                # DEAD ZONE LOCK: Subject is within comfortable framing tolerances.
                # Hold the camera 100% frozen/locked in place like a professional tripod operator.
                # Eliminates software micro-panning and robotic drift.
                pass
            else:
                # Exponential smoothing for smooth, natural camera tracking when subject leaves dead zone
                alpha = 1.0 - math.exp(-PAN_SMOOTH_RATE * dt)
                cam_x += (tx - cam_x) * alpha
                cam_y += (ty - cam_y) * alpha

            # Edge guard: keep face center within inner 70% of crop width
            if ax is not None:
                min_cam_x = ax - crop_w * (1.0 - MIN_EDGE_MARGIN_X)
                max_cam_x = ax - crop_w * MIN_EDGE_MARGIN_X
                cam_x = _clamp(cam_x, min_cam_x, max_cam_x)

            cam_x = _clamp(cam_x, 0.0, max(0.0, float(src_w - crop_w)))
            cam_y = _clamp(cam_y, 0.0, max(0.0, float(src_h - crop_h)))

            frames.append({
                "time": round(t, 6),
                "x": int(round(cam_x)),
                "y": int(round(cam_y)),
                "width": crop_w,
                "height": crop_h,
                "zoom": round(seg["zoom"], 4),
                "layout": "full-crop",
                "source": anchor.get("source", "unknown"),
            })
            prev_t = t

        camera_curves.append({
            "clipId": clip_id, "start": clip_start, "end": clip_end,
            "sourceWidth": src_w, "sourceHeight": src_h,
            "layout": dominant, "frames": frames,
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
            "method": "spring-damped-virtual-camera-operator",
            "resolvedLayout": dominant, "layoutSegments": layout_segments, "layoutMode": "auto",
        })

    (temp_dir / "camera_curve.json").write_text(
        json.dumps({
            "method": "spring-damped-virtual-camera-operator",
            "schemaVersion": "2.0",
            "clips": camera_curves,
        }, indent=2), encoding="utf-8")
    (temp_dir / "crop_coords.json").write_text(
        json.dumps({
            "pipelineVersion": "4.1.0", "schemaVersion": "2.0",
            "targetAspectRatio": "9:16",
            "method": "spring-damped-virtual-camera-operator",
            "plans": crop_plans,
        }, indent=2), encoding="utf-8")
