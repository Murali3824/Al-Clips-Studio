"""Modular Render Engine.

Centralized module for FFmpeg filtergraph construction, visual layout composition,
crop filter generation, smart vertical blur, and clean shot-boundary transitions.

Supported Aspect Ratios:
  - 9:16 (1080x1920) — Default Shorts / Reels / TikTok
  - 16:9 (1920x1080) — Landscape

Supported Layout Modes:
  - full-crop: Subject-tracked vertical crop
  - blur-pad: Smart vertical blur padding
  - auto-dynamic: Dynamic overlay layout switching at shot cuts
"""

import json
import os
import tempfile
from pathlib import Path
import math
from media_utils import run_command

DEFAULT_WIDTH = 1080
DEFAULT_HEIGHT = 1920
SHORTS_WIDTH = 1080
SHORTS_HEIGHT = 1920


def resolve_dimensions(aspect_ratio: str = "9:16") -> tuple[int, int]:
    """Resolve target width and height for a given aspect ratio string."""
    if aspect_ratio == "16:9":
        return 1920, 1080
    return 1080, 1920


def crop_filter(plan: dict | None, target_w: int = DEFAULT_WIDTH, target_h: int = DEFAULT_HEIGHT) -> str:
    """Generate FFmpeg crop and scale filter string from crop plan.

    Supports both 'width'/'height' and 'w'/'h' plan key formats.
    """
    if not plan:
        return (
            f"scale={target_w}:{target_h}:force_original_aspect_ratio=increase,"
            f"crop={target_w}:{target_h},setsar=1"
        )
    w = plan.get("w") or plan.get("width")
    h = plan.get("h") or plan.get("height")
    x = plan.get("x", 0)
    y = plan.get("y", 0)
    if not w or not h:
        return (
            f"scale={target_w}:{target_h}:force_original_aspect_ratio=increase,"
            f"crop={target_w}:{target_h},setsar=1"
        )
    return (
        f"crop={int(w)}:{int(h)}:{int(x)}:{int(y)},"
        f"scale={target_w}:{target_h},setsar=1"
    )


def _cubic_ease(value: float) -> float:
    value = max(0.0, min(1.0, float(value)))
    return 3.0 * value * value - 2.0 * value * value * value


def _sine_ease(value: float) -> float:
    value = max(0.0, min(1.0, float(value)))
    return (1.0 - math.cos(math.pi * value)) / 2.0


def _ease(value: float, profile: str | None) -> float:
    """Evaluate a planner-selected, backward-compatible camera easing profile."""
    if profile == "sine_ease_in_out":
        return _sine_ease(value)
    return _cubic_ease(value)


def _position_at(camera_plan: dict, absolute_time: float) -> dict:
    """Evaluate the immutable planner keyframes using its cubic easing contract."""
    composition = camera_plan["sourceComposition"]
    fallback = {key: float(composition[key]) for key in ("x", "y", "width", "height")}
    fallback["zoom"] = 1.0
    segments = camera_plan.get("segments", [])
    for index, segment in enumerate(segments):
        start, end = float(segment["start"]), float(segment["end"])
        if start <= absolute_time < end or (index == len(segments) - 1 and absolute_time <= end):
            first, last = segment["keyframes"]
            duration = max(0.001, end - start)
            eased = _ease((absolute_time - start) / duration, segment.get("easing"))
            return {
                key: float(first["position"][key]) + (float(last["position"][key]) - float(first["position"][key])) * eased
                for key in ("x", "y", "width", "height", "zoom")
            }
    return fallback


def camera_render_trace(camera_plan: dict | None) -> list[dict]:
    """Read-only execution trace at each keyframe and easing midpoint."""
    if not camera_plan:
        return []
    trace = []
    for segment in camera_plan.get("segments", []):
        start, end = float(segment["start"]), float(segment["end"])
        for timestamp in (start, (start + end) / 2.0, end):
            position = _position_at(camera_plan, timestamp)
            trace.append({
                "sceneIndex": segment.get("sceneIndex"),
                "time": round(timestamp, 3),
                "position": {key: round(value, 3) for key, value in position.items()},
                "easing": segment.get("easing"),
            })
    return trace


def camera_crop_filter(camera_plan: dict | None, target_w: int = DEFAULT_WIDTH, target_h: int = DEFAULT_HEIGHT) -> str | None:
    """Generate a per-frame FFmpeg crop filter that executes frozen plan keyframes exactly."""
    if not camera_plan or not camera_plan.get("segments"):
        return None
    composition = camera_plan["sourceComposition"]
    fallback = {key: float(composition[key]) for key in ("x", "y", "width", "height")}
    fallback["zoom"] = 1.0

    def expression(axis: str) -> str:
        value = f"{fallback[axis]:.6f}"
        segments = camera_plan["segments"]
        for reverse_index, segment in enumerate(reversed(segments)):
            start, end = float(segment["start"]), float(segment["end"])
            first, last = segment["keyframes"]
            initial = float(first["position"][axis])
            final = float(last["position"][axis])
            relative_start = start - float(camera_plan["start"])
            relative_end = end - float(camera_plan["start"])
            duration = max(0.001, relative_end - relative_start)
            u = f"((t-{relative_start:.6f})/{duration:.6f})"
            easing = segment.get("easing")
            eased = f"((1-cos(PI*{u}))/2)" if easing == "sine_ease_in_out" else f"(3*{u}*{u}-2*{u}*{u}*{u})"
            interpolated = f"({initial:.6f}+({final - initial:.6f})*{eased})"
            is_final_segment = len(segments) - 1 - reverse_index == len(segments) - 1
            condition = (
                f"gte(t\\,{relative_start:.6f})*lte(t\\,{relative_end:.6f})"
                if is_final_segment
                else f"gte(t\\,{relative_start:.6f})*lt(t\\,{relative_end:.6f})"
            )
            value = f"if({condition}\\,{interpolated}\\,{value})"
        return value

    base_width = int(float(composition["width"]))
    base_height = int(float(composition["height"]))
    zoom = expression("zoom")
    x = expression("x")
    y = expression("y")
    return (
        # crop has no per-frame width/height option in all supported FFmpeg builds.
        # Scaling first executes the planned zoom; the fixed crop then represents
        # the same source viewport at the plan's x/y coordinates.
        f"scale=w='iw*({zoom})':h='ih*({zoom})':eval=frame,"
        f"crop=w={base_width}:h={base_height}:x='({x})*({zoom})':y='({y})*({zoom})',"
        f"scale={target_w}:{target_h},setsar=1"
    )


def sendcmd_from_camera_curve(
    camera_curve: dict,
    clip_start: float,
    cmd_path: str,
) -> tuple[int, int]:
    """Write an FFmpeg sendcmd file from a per-frame camera curve.

    Each entry in camera_curve["frames"] produces a crop x/y update at the
    corresponding clip-relative timestamp. Returns the (crop_w, crop_h) of the
    first full-crop frame, which is used as the fixed crop window dimensions.
    """
    frames = camera_curve.get("frames", [])
    if not frames:
        return 0, 0

    # Fixed crop dims are taken from the first valid full-crop frame.
    crop_w = crop_h = 0
    for f in frames:
        if f.get("layout") == "full-crop":
            crop_w = int(f["width"])
            crop_h = int(f["height"])
            break
    if not crop_w:
        f0 = frames[0]
        crop_w, crop_h = int(f0["width"]), int(f0["height"])

    lines = []
    prev_x = prev_y = None
    for frame in frames:
        t = float(frame["time"]) - clip_start
        if t < 0:
            continue
        fx = int(frame["x"])
        fy = int(frame["y"])
        if fx != prev_x or fy != prev_y:
            lines.append(f"{t:.6f} crop x {fx};")
            lines.append(f"{t:.6f} crop y {fy};")
            prev_x, prev_y = fx, fy

    Path(cmd_path).write_text("\n".join(lines) + "\n", encoding="utf-8")
    return crop_w, crop_h


def per_frame_camera_crop_filter(
    camera_curve: dict | None,
    clip_start: float,
    cmd_path: str,
    target_w: int = DEFAULT_WIDTH,
    target_h: int = DEFAULT_HEIGHT,
) -> str | None:
    """Generate an FFmpeg filtergraph that applies per-frame crop from a camera curve.

    Handles mixed crop dimensions across shot segments correctly.

    If all full-crop frames share the same crop dimensions (common case: single shot
    type per clip, or same zoom level throughout), a direct crop=w:h:x:y is used.

    If crop dimensions vary across segments (close + medium within same clip), the
    approach is: scale the source to the largest zoom factor first, so the base crop
    window stays fixed, then apply the per-frame x/y expression.

    x and y expressions are clamped to [0, src_dim - crop_dim] at every keyframe
    to prevent FFmpeg from receiving out-of-range values.
    """
    if not camera_curve:
        return None
    frames = camera_curve.get("frames", [])
    if not frames:
        return None

    valid = [f for f in frames if f.get("layout") == "full-crop" and f.get("x") is not None]
    if not valid:
        return None

    # Collect unique (width, height) pairs across all full-crop frames
    dim_pairs = set((int(f["width"]), int(f["height"])) for f in valid)
    src_w = camera_curve.get("sourceWidth", 1920)
    src_h = camera_curve.get("sourceHeight", 1080)

    if len(dim_pairs) == 1:
        # All full-crop frames share the same crop dimensions — simple case
        crop_w, crop_h = dim_pairs.pop()
        max_x = max(0, src_w - crop_w)
        max_y = max(0, src_h - crop_h)
    else:
        # Mixed crop dims: use the smallest crop window (= highest zoom, tightest shot)
        # and clamp all x/y values to fit within it.
        # The x/y values in each frame were computed for that frame's own crop dims,
        # so we must re-center them for the common (smallest) window.
        crop_w = min(f["width"]  for f in valid)
        crop_h = min(f["height"] for f in valid)
        crop_w -= crop_w % 2
        crop_h -= crop_h % 2
        max_x = max(0, src_w - crop_w)
        max_y = max(0, src_h - crop_h)
        # Re-center x/y for each frame that had larger crop dims
        adjusted = []
        for f in valid:
            fw, fh = int(f["width"]), int(f["height"])
            fx, fy = int(f["x"]), int(f["y"])
            if fw != crop_w or fh != crop_h:
                # The stored x/y centered a larger window; re-center for the smaller one
                # face_center_x ≈ fx + fw/2, face_center_y ≈ fy + fh*0.35
                face_cx = fx + fw / 2.0
                face_cy = fy + fh * 0.35
                fx = int(max(0, min(max_x, face_cx - crop_w / 2.0)))
                fy = int(max(0, min(max_y, face_cy - crop_h * 0.35)))
            adjusted.append({**f, "x": fx, "y": fy, "width": crop_w, "height": crop_h})
        valid = adjusted

    # Limit to at most 90 keyframes
    max_keyframes = 90
    if len(valid) > max_keyframes:
        step = len(valid) / max_keyframes
        valid = [valid[int(i * step)] for i in range(max_keyframes)]

    def build_expr(axis: str, bound: int) -> str:
        """Build a linearly-interpolated FFmpeg expression, clamped to [0, bound]."""
        pts = [(float(f["time"]) - clip_start, float(f[axis])) for f in valid]
        pts.sort(key=lambda p: p[0])

        if len(pts) == 1:
            v = int(max(0, min(bound, round(pts[0][1]))))
            return str(v)

        # Start with the final value (held for t > last keyframe), clamped
        last_v = int(max(0, min(bound, round(pts[-1][1]))))
        expr = str(last_v)

        # Build right-to-left: each segment is a linear ramp
        for i in range(len(pts) - 2, -1, -1):
            t1, v1 = pts[i]
            t2, v2 = pts[i + 1]
            dt = max(0.0001, t2 - t1)
            dv = v2 - v1
            # Clamp endpoint values
            cv1 = int(max(0, min(bound, round(v1))))
            if abs(dv) < 0.5:
                seg_expr = str(cv1)
            else:
                seg_expr = f"({cv1}+{dv:.4f}*(t-{t1:.4f})/{dt:.4f})"
            expr = f"if(lt(t,{t2:.4f}),{seg_expr},{expr})"

        return expr

    x_expr = build_expr("x", max_x)
    y_expr = build_expr("y", max_y)

    return (
        f"crop={crop_w}:{crop_h}:x='{x_expr}':y='{y_expr}',"
        f"scale={target_w}:{target_h},setsar=1"
    )




def blur_pad_filter(
    target_w: int = DEFAULT_WIDTH,
    target_h: int = DEFAULT_HEIGHT,
    blur_strength: int = 25,
) -> str:
    """Smart Vertical Blur: keep original landscape centered, blur-fill top/bottom."""
    strength = max(1, min(60, int(blur_strength)))
    return (
        f"split[bg][fg];"
        f"[bg]scale={target_w}:{target_h}:force_original_aspect_ratio=increase,"
        f"crop={target_w}:{target_h},boxblur={strength}:5[blurred];"
        f"[fg]scale='if(gt(iw/ih,{target_w}/{target_h}),{target_w},-2)':'if(gt(iw/ih,{target_w}/{target_h}),-2,{target_h})'[scaled];"
        f"[blurred][scaled]overlay=(W-w)/2:(H-h)/2,setsar=1"
    )


def validate_filtergraph(filter_complex_str: str) -> bool:
    """Validate that the smart vertical blur filtergraph contains expected components."""
    if "boxblur" in filter_complex_str:
        if "overlay" not in filter_complex_str:
            return False
        if "overlay=(W-w)/2:(H-h)/2" not in filter_complex_str:
            return False
        if "split" not in filter_complex_str:
            return False
    return True


def encode_clip_with_layout_transitions(
    input_video: str,
    clip_start: float,
    clip_duration: float,
    segments: list[dict],
    plan: dict | None,
    output_path: str,
    target_w: int = DEFAULT_WIDTH,
    target_h: int = DEFAULT_HEIGHT,
    blur_strength: int = 25,
    camera_plan: dict | None = None,
    camera_curve: dict | None = None,
):
    """Encode clip using dynamic filtergraph with clean layout switching at shot boundaries.

    camera_curve (stage_08c output): per-frame x/y crop positions — used when available.
    camera_plan  (stage_08a output): two-keyframe polynomial plan — used as fallback.
    """
    b_filter = blur_pad_filter(target_w, target_h, blur_strength)

    # Build crop filter: prefer per-frame camera_curve over two-keyframe camera_plan
    c_filter = None
    if camera_curve and camera_curve.get("frames"):
        cmd_file = output_path + ".sendcmd.txt"
        c_filter = per_frame_camera_crop_filter(camera_curve, clip_start, cmd_file, target_w, target_h)
    if not c_filter:
        c_filter = camera_crop_filter(camera_plan, target_w, target_h) or crop_filter(plan, target_w, target_h)

    blur_segments = [s for s in segments if s.get("layout") == "blur-pad"]
    crop_segments = [s for s in segments if s.get("layout") == "full-crop"]

    # Case 1: Pure full-crop layout
    if not blur_segments:
        run_command([
            "ffmpeg", "-y",
            "-ss", f"{clip_start:.3f}",
            "-i", input_video,
            "-t", f"{clip_duration:.3f}",
            "-avoid_negative_ts", "make_zero",
            "-map", "0:v:0", "-map", "0:a?",
            "-vf", c_filter,
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "23", "-c:a", "aac",
            "-movflags", "+faststart", output_path
        ])
        return

    # Case 2: Pure blur-pad layout
    if not crop_segments:
        filter_str = b_filter + "[vout]"
        if not validate_filtergraph(filter_str):
            b_filter = blur_pad_filter(target_w, target_h, blur_strength)
            filter_str = b_filter + "[vout]"

        run_command([
            "ffmpeg", "-y",
            "-ss", f"{clip_start:.3f}",
            "-i", input_video,
            "-t", f"{clip_duration:.3f}",
            "-avoid_negative_ts", "make_zero",
            "-filter_complex", filter_str,
            "-map", "[vout]", "-map", "0:a?",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "23", "-c:a", "aac",
            "-movflags", "+faststart", output_path
        ])
        return

    # Case 3: Mixed layout segments — overlay blur segments on top of crop base at shot cuts
    filter_parts = []
    filter_parts.append("[0:v]split[v_crop][v_blur]")
    filter_parts.append(f"[v_crop]{c_filter}[cropped_base]")

    num_blur_segs = len(blur_segments)
    if num_blur_segs > 1:
        split_tags = "".join(f"[bb{i}]" for i in range(num_blur_segs))
        filter_parts.append(f"[v_blur]{b_filter}[blurred_base]")
        filter_parts.append(f"[blurred_base]split={num_blur_segs}{split_tags}")
    elif num_blur_segs == 1:
        filter_parts.append(f"[v_blur]{b_filter}[bb0]")
    else:
        filter_parts.append(f"[v_blur]{b_filter}[blurred_base]")

    current_bg = "cropped_base"
    for idx, seg in enumerate(blur_segments):
        rel_start = float(seg["start"]) - clip_start
        rel_end = float(seg["end"]) - clip_start
        next_bg = f"ov{idx}" if idx < len(blur_segments) - 1 else "vout"
        bb_tag = f"bb{idx}" if num_blur_segs >= 1 else "blurred_base"

        filter_parts.append(
            f"[{current_bg}][{bb_tag}]overlay=enable='between(t,{rel_start:.3f},{rel_end:.3f})',setsar=1[{next_bg}]"
        )
        current_bg = next_bg

    filter_complex_str = ";".join(filter_parts)
    if not validate_filtergraph(filter_complex_str):
        b_filter = blur_pad_filter(target_w, target_h, blur_strength)
        filter_parts[2] = f"[v_blur]{b_filter}[blurred_base]"
        filter_complex_str = ";".join(filter_parts)

    run_command([
        "ffmpeg", "-y",
        "-ss", f"{clip_start:.3f}",
        "-i", input_video,
        "-t", f"{clip_duration:.3f}",
        "-avoid_negative_ts", "make_zero",
        "-filter_complex", filter_complex_str,
        "-map", "[vout]", "-map", "0:a?",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "23", "-c:a", "aac",
        "-movflags", "+faststart", output_path
    ])
