"""Modular Render Engine.

Centralized module for FFmpeg filtergraph construction, visual layout composition,
crop filter generation, smart vertical blur, and clean shot-boundary transitions.

Supported Aspect Ratios:
  - 9:16 (1080x1920) — Default Shorts / Reels / TikTok
  - 1:1  (1080x1080) — Square
  - 16:9 (1920x1080) — Landscape

Supported Layout Modes:
  - full-crop: Subject-tracked vertical crop
  - blur-pad: Smart vertical blur padding
  - auto-dynamic: Dynamic overlay layout switching at shot cuts
"""

import json
from pathlib import Path
from media_utils import run_command

DEFAULT_WIDTH = 1080
DEFAULT_HEIGHT = 1920
SHORTS_WIDTH = 1080
SHORTS_HEIGHT = 1920


def resolve_dimensions(aspect_ratio: str = "9:16") -> tuple[int, int]:
    """Resolve target width and height for a given aspect ratio string."""
    if aspect_ratio == "1:1":
        return 1080, 1080
    elif aspect_ratio == "16:9":
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
):
    """Encode clip using dynamic filtergraph with clean layout switching at shot boundaries."""
    c_filter = crop_filter(plan, target_w, target_h)
    b_filter = blur_pad_filter(target_w, target_h, blur_strength)

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
