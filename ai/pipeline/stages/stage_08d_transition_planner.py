"""Stage 08D - Transition Planner.

Inserts Hermite-smooth, velocity-continuous transition curves at every
identified boundary in the per-frame camera curve produced by stage_08c.

Boundary types handled:
  - Scene cuts within a clip
  - Shot-type changes at segment boundaries (close/medium/wide)
  - Layout mode switches (full-crop <-> blur-pad)

The spring-damper output is preserved everywhere except at transition
windows, where it is replaced with cubic Hermite curves that match
position AND velocity at both endpoints (C1 continuity).
"""

import json
import math

# --------------------------------------------------------------------------
# Transition duration table (seconds) — tuned for Shorts / Reels / TikTok
# --------------------------------------------------------------------------
TRANSITION_DURATIONS = {
    "cut_same_shot":    0.25,
    "cut_shot_change":  0.55,
    "subject_switch":   0.45,
    "close_to_close":   0.30,
    "close_to_medium":  0.55,
    "medium_to_close":  0.45,
    "close_to_wide":    0.75,
    "wide_to_close":    0.75,
    "medium_to_wide":   0.65,
    "wide_to_medium":   0.60,
    "wide_to_wide":     0.40,
    "medium_to_medium": 0.30,
    "layout_switch":    0.45,
    "default":          0.35,
}

TARGET_RATIO = 9.0 / 16.0
MIN_ZOOM = 1.0
MAX_ZOOM = 2.50


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


def _hermite(t, p0, p1, m0, m1):
    """Cubic Hermite interpolation at normalized t in [0, 1].

    p0, p1: start/end positions.
    m0, m1: start/end tangents scaled by duration (velocity * total_duration).
    Guarantees C1 continuity when m0/m1 match the entry/exit velocities.
    """
    t2 = t * t
    t3 = t2 * t
    h00 = 2 * t3 - 3 * t2 + 1
    h10 = t3 - 2 * t2 + t
    h01 = -2 * t3 + 3 * t2
    h11 = t3 - t2
    return h00 * p0 + h10 * m0 + h01 * p1 + h11 * m1


def _velocity_at(frames, idx, axis, window=4):
    """Estimate velocity at frames[idx] via central finite differences."""
    lo = max(0, idx - window)
    hi = min(len(frames) - 1, idx + window)
    if hi <= lo:
        return 0.0
    dt = float(frames[hi]["time"]) - float(frames[lo]["time"])
    if abs(dt) < 1e-6:
        return 0.0
    va = frames[lo].get(axis)
    vb = frames[hi].get(axis)
    if va is None or vb is None:
        return 0.0
    return (float(vb) - float(va)) / dt


def _identify_events(clip_start, frames, layout_segments, clip_scene_cuts):
    """Return sorted list of transition event dicts for a clip."""
    if not frames:
        return []
    t_min = float(frames[0]["time"])
    t_max = float(frames[-1]["time"])
    events = []

    # --- 1. Scene cuts ---
    for cut_t in clip_scene_cuts:
        if t_min < cut_t < t_max:
            events.append({
                "time": cut_t,
                "type": "cut_same_shot",
                "duration": TRANSITION_DURATIONS["cut_same_shot"],
            })

    # --- 2. Layout/shot segment boundaries ---
    for i in range(len(layout_segments) - 1):
        seg_a = layout_segments[i]
        seg_b = layout_segments[i + 1]
        t_boundary = float(seg_b["start"])
        if not (t_min <= t_boundary <= t_max):
            continue
        layout_a = seg_a.get("layout", "full-crop")
        layout_b = seg_b.get("layout", "full-crop")
        shot_a = seg_a.get("shotType", "close")
        shot_b = seg_b.get("shotType", "close")
        if layout_a != layout_b:
            ttype = "layout_switch"
            dur = TRANSITION_DURATIONS["layout_switch"]
        else:
            ttype = f"{shot_a}_to_{shot_b}"
            dur = TRANSITION_DURATIONS.get(ttype, TRANSITION_DURATIONS["default"])
        # This boundary supersedes any plain cut event within 0.25 s
        events = [e for e in events if abs(e["time"] - t_boundary) > 0.25]
        events.append({
            "time": t_boundary,
            "type": ttype,
            "duration": dur,
            "layout_a": layout_a,
            "layout_b": layout_b,
        })

    events.sort(key=lambda e: e["time"])
    return events


def _apply_hermite_transition(frames, event_time, duration, src_w, src_h):
    """Smooth frames within the transition window using a Hermite curve.

    Matches position and velocity at both window edges for C1 continuity.
    """
    half = duration / 2.0
    win_start = event_time - half
    win_end = event_time + half

    # Clamp window to not extend before the first frame or after the last frame.
    # Without this, t_rel > 0 at frame 0 when win_start < frames[0].time,
    # causing the Hermite spline to shift frame 0 away from its original position.
    if frames:
        win_start = max(win_start, float(frames[0]["time"]))
        win_end = min(win_end, float(frames[-1]["time"]))

    win_idx = [i for i, f in enumerate(frames) if win_start <= float(f["time"]) <= win_end]
    if len(win_idx) < 2:
        return

    # Frames outside the window
    pre_idx_list = [i for i in range(win_idx[0]) if float(frames[i]["time"]) < win_start]
    post_idx_list = [i for i in range(win_idx[-1] + 1, len(frames)) if float(frames[i]["time"]) > win_end]

    # State and velocity at window entry
    if pre_idx_list:
        pi = pre_idx_list[-1]
        state_before = {ax: float(frames[pi].get(ax, 0)) for ax in ("x", "y", "zoom")}
        vel_before = {ax: _velocity_at(frames, pi, ax) for ax in ("x", "y", "zoom")}
    else:
        f0 = frames[win_idx[0]]
        state_before = {ax: float(f0.get(ax, 0)) for ax in ("x", "y", "zoom")}
        vel_before = {"x": 0.0, "y": 0.0, "zoom": 0.0}

    # State and velocity at window exit
    if post_idx_list:
        qi = post_idx_list[0]
        state_after = {ax: float(frames[qi].get(ax, 0)) for ax in ("x", "y", "zoom")}
        vel_after = {ax: _velocity_at(frames, qi, ax) for ax in ("x", "y", "zoom")}
    else:
        fN = frames[win_idx[-1]]
        state_after = {ax: float(fN.get(ax, 0)) for ax in ("x", "y", "zoom")}
        vel_after = {"x": 0.0, "y": 0.0, "zoom": 0.0}

    total_dur = max(0.001, win_end - win_start)

    for i in win_idx:
        f = frames[i]
        t_rel = _clamp((float(f["time"]) - win_start) / total_dur, 0.0, 1.0)
        new_f = dict(f)
        for ax in ("x", "y", "zoom"):
            p0 = state_before[ax]
            p1 = state_after[ax]
            m0 = vel_before[ax] * total_dur
            m1 = vel_after[ax] * total_dur
            val = _hermite(t_rel, p0, p1, m0, m1)
            if ax == "zoom":
                new_f[ax] = round(_clamp(val, MIN_ZOOM, MAX_ZOOM), 4)
            else:
                new_f[ax] = int(round(max(0.0, val)))
        # Update crop dims to match new zoom
        cw, ch = _crop_dims(src_w, src_h, new_f["zoom"])
        new_f["width"] = cw
        new_f["height"] = ch
        new_f["interp"] = "HERMITE"
        frames[i] = new_f


def run(context):
    temp_dir = context["temp_dir"]
    meta_path = temp_dir / "video_metadata.json"
    if not meta_path.exists():
        print("stage_08d: video_metadata.json not found, skipping.", flush=True)
        return
    metadata = json.loads(meta_path.read_text(encoding="utf-8"))
    src_w = int(metadata["width"])
    src_h = int(metadata["height"])

    curve_path = temp_dir / "camera_curve.json"
    if not curve_path.exists():
        print("stage_08d: camera_curve.json not found, skipping.", flush=True)
        return
    camera_curve = json.loads(curve_path.read_text(encoding="utf-8"))

    crop_path = temp_dir / "crop_coords.json"
    crop_coords = json.loads(crop_path.read_text(encoding="utf-8")) if crop_path.exists() else {}
    layout_map = {p["clipId"]: p for p in crop_coords.get("plans", [])}

    sc_path = temp_dir / "scene_cuts.json"
    scenes = json.loads(sc_path.read_text(encoding="utf-8")).get("scenes", []) if sc_path.exists() else []

    total_events = 0
    for clip in camera_curve.get("clips", []):
        clip_id = clip["clipId"]
        clip_start = float(clip["start"])
        clip_end = float(clip["end"])
        frames = clip.get("frames", [])
        if not frames:
            continue

        # Ensure every keyframe defaults to interp="HOLD" if missing
        for f in frames:
            if "interp" not in f:
                f["interp"] = "HERMITE" if f.get("fsm_state") == "INTENTIONAL_REFRAME" else "HOLD"

        # Layout segments from crop_coords
        plan = layout_map.get(clip_id, {})
        layout_segments = plan.get("layoutSegments", [])
        if not layout_segments:
            layout_segments = [{"start": clip_start, "end": clip_end,
                                 "layout": "full-crop", "shotType": "close"}]

        # Scene cut timestamps within this clip
        clip_cuts = set()
        for sc in scenes:
            for key in ("start", "end"):
                t = float(sc.get(key, 0))
                if clip_start < t < clip_end:
                    clip_cuts.add(round(t, 4))
        clip_cuts = sorted(clip_cuts)

        # Insert keyframe at exact scene-cut timestamps
        for cut_t in clip_cuts:
            if not any(abs(float(f["time"]) - cut_t) < 0.001 for f in frames):
                # Find adjacent keyframe right after cut_t
                after_f = next((f for f in frames if float(f["time"]) >= cut_t), frames[-1])
                cut_f = dict(after_f)
                cut_f["time"] = cut_t
                cut_f["interp"] = "HOLD"
                frames.append(cut_f)

        # Keep frames sorted chronologically
        frames.sort(key=lambda f: float(f["time"]))
        clip["frames"] = frames

        events = _identify_events(clip_start, frames, layout_segments, clip_cuts)
        if events:
            for event in events:
                _apply_hermite_transition(frames, event["time"], event["duration"], src_w, src_h)

            total_events += len(events)
            event_summary = ", ".join(
                f"{e['type']}@{e['time']:.2f}s" for e in events
            )
            print(f"  {clip_id}: {len(events)} transitions — {event_summary}", flush=True)

    print(f"stage_08d: {total_events} transition windows applied.", flush=True)
    curve_path.write_text(json.dumps(camera_curve, indent=2), encoding="utf-8")
