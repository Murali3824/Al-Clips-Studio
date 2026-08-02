import argparse
import json
import os
import re
import subprocess
from pathlib import Path
from typing import Any
import cv2
import sys
import time
import shutil

sys.path.append(str(Path(__file__).resolve().parent))
from media_utils import find_input_video, run_command
from music_library import has_audio_stream
from render_engine import encode_clip_with_layout_transitions
from hook_renderer import render_hook_overlay_png, resolve_hook_text, resolve_hook_enabled

SHORTS_W = 1080
SHORTS_H = 1920

STYLE_DEFINITIONS = {
    "classic-white": {
        "font": "Arial Black",
        "font_size": 72,
        "primary": "&H00FFFFFF",
        "outline": "&H00000000",
        "back": "&H80000000",
        "bold": 1,
        "border_style": 1,
        "outline_size": 4,
        "shadow": 2,
    },
    "boxed": {
        "font": "Arial Black",
        "font_size": 72,
        "primary": "&H00FFFFFF",
        "outline": "&H00000000",
        "back": "&H00000000",
        "bold": 1,
        "border_style": 3,
        "outline_size": 12,
        "shadow": 0,
    },
    "outline": {
        "font": "Arial Black",
        "font_size": 76,
        "primary": "&H00FFFFFF",
        "outline": "&H00000000",
        "back": "&H00000000",
        "bold": 1,
        "border_style": 1,
        "outline_size": 6,
        "shadow": 4,
    },
    "bold-pop": {
        "font": "Arial Black",
        "font_size": 84,
        "primary": "&H00FFFFFF",
        "outline": "&H00000000",
        "back": "&H00000000",
        "bold": 1,
        "border_style": 1,
        "outline_size": 7,
        "shadow": 3,
    },
    "karaoke-bounce": {
        "font": "Arial Black",
        "font_size": 78,
        "primary": "&H00FFFFFF",
        "outline": "&H00000000",
        "back": "&H00000000",
        "bold": 1,
        "border_style": 1,
        "outline_size": 5,
        "shadow": 2,
    },
    "minimal": {
        "font": "Helvetica",
        "font_size": 64,
        "primary": "&H00FFFFFF",
        "outline": "&H00000000",
        "back": "&H80000000",
        "bold": 0,
        "border_style": 1,
        "outline_size": 2,
        "shadow": 1,
    },
    "creator": {
        "font": "Impact",
        "font_size": 86,
        "primary": "&H0000FFFF",
        "outline": "&H00000000",
        "back": "&H00000000",
        "bold": 1,
        "border_style": 1,
        "outline_size": 6,
        "shadow": 3,
    },
    "viral-shorts": {
        "font": "Arial Black",
        "font_size": 88,
        "primary": "&H00FFFFFF",
        "outline": "&H00000000",
        "back": "&H00000000",
        "bold": 1,
        "border_style": 1,
        "outline_size": 7,
        "shadow": 4,
    },
    "tiktok": {
        "font": "Arial Black",
        "font_size": 80,
        "primary": "&H00FFFFFF",
        "outline": "&H00000000",
        "back": "&H00000000",
        "bold": 1,
        "border_style": 1,
        "outline_size": 6,
        "shadow": 2,
    },
    "podcast": {
        "font": "Georgia",
        "font_size": 68,
        "primary": "&H00FFFFFF",
        "outline": "&H00000000",
        "back": "&H80000000",
        "bold": 1,
        "border_style": 1,
        "outline_size": 3,
        "shadow": 2,
    },
}

LEGACY_STYLE_MAP = {
    "word-highlight": "classic-white",
    "boxed-background": "boxed",
    "outline-shadow": "outline",
}

MULTI_COLOR_PALETTE = [
    "&H0000FFFF", "&H0000FF00", "&H000000FF", "&H00FFFF00",
]

HIGHLIGHT_COLOR_MAP = {
    "yellow": "&H0000FFFF",
    "green": "&H0000FF00",
    "red": "&H000000FF",
    "cyan": "&H00FFFF00",
}

POSITION_MAP = {
    "bottom": {"alignment": 2, "margin_v": 170},
    "center": {"alignment": 5, "margin_v": 0},
    "top": {"alignment": 8, "margin_v": 170},
}

def _resolve_style(name: str) -> str:
    return LEGACY_STYLE_MAP.get(name, name)

def _ass_time(seconds: float) -> str:
    seconds = max(0.0, seconds)
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    centiseconds = int(round((seconds - int(seconds)) * 100))
    if centiseconds == 100:
        secs += 1
        centiseconds = 0
    return f"{hours}:{minutes:02d}:{secs:02d}.{centiseconds:02d}"

def _escape_ass(text: str) -> str:
    text = re.sub(r"\s+", " ", text).strip()
    return text.replace("\\", "\\\\").replace("{", r"\{").replace("}", r"\}")

def _hex_to_ass(hex_color: str) -> str:
    """Convert HTML hex color (#RRGGBB or #RRGGBBAA) to ASS BGR format (&HAABBGGRR)."""
    if not hex_color:
        return "&H00FFFFFF"
    hex_color = hex_color.lstrip("#")
    if len(hex_color) == 6:
        r, g, b = hex_color[0:2], hex_color[2:4], hex_color[4:6]
        return f"&H00{b}{g}{r}"
    elif len(hex_color) == 8:
        r, g, b, a = hex_color[0:2], hex_color[2:4], hex_color[4:6], hex_color[6:8]
        inv_a = f"{255 - int(a, 16):02X}"
        return f"&H{inv_a}{b}{g}{r}"
    return "&H00FFFFFF"

def _get_hook_setting(suffix: str, clip_meta: dict, settings: dict, default: Any) -> Any:
    keys = [
        f"autoHook{suffix}",
        f"hook2{suffix}",
        f"auto_hook_{suffix.lower()}",
        f"hook_{suffix.lower()}"
    ]
    for k in keys:
        if k in clip_meta:
            return clip_meta[k]
        if k in settings:
            return settings[k]
    return default

def _chunk_text(chunk: list[dict], uppercase: bool = False) -> str:
    cleaned_words = []
    for w in chunk:
        w_text = str(w.get("word", "")).strip().lstrip(",.?!:; -")
        if w_text:
            cleaned_words.append(w_text.upper() if uppercase else w_text)
    text = " ".join(cleaned_words)
    return _escape_ass(text)

def _resolve_highlight_color(
    chunk_index: int = 0,
    highlight_color_mode: str = "single",
    highlight_color: str = "yellow",
) -> str:
    if highlight_color_mode == "multi":
        return MULTI_COLOR_PALETTE[chunk_index % len(MULTI_COLOR_PALETTE)]
    return HIGHLIGHT_COLOR_MAP.get(highlight_color, "&H0000FFFF")

ANIMATION_PROPERTIES = {
    "bold-pop": {
        "intro_scale": 86,
        "final_scale": 112,
        "scale_dur": 130,
        "fade_in": 45,
        "fade_out": 90,
    },
    "karaoke-bounce": {
        "intro_scale": 92,
        "final_scale": 100,
        "scale_dur": 90,
        "fade_in": 35,
        "fade_out": 70,
    },
    "boxed": {
        "intro_scale": 100,
        "final_scale": 100,
        "scale_dur": 0,
        "fade_in": 60,
        "fade_out": 80,
    },
    "outline": {
        "intro_scale": 100,
        "final_scale": 100,
        "scale_dur": 0,
        "fade_in": 35,
        "fade_out": 65,
    },
    "minimal": {
        "intro_scale": 100,
        "final_scale": 100,
        "scale_dur": 0,
        "fade_in": 80,
        "fade_out": 120,
    },
    "creator": {
        "intro_scale": 90,
        "final_scale": 108,
        "scale_dur": 100,
        "fade_in": 50,
        "fade_out": 80,
    },
    "viral-shorts": {
        "intro_scale": 88,
        "final_scale": 115,
        "scale_dur": 120,
        "fade_in": 40,
        "fade_out": 70,
    },
    "tiktok": {
        "intro_scale": 100,
        "final_scale": 100,
        "scale_dur": 0,
        "fade_in": 50,
        "fade_out": 90,
    },
    "podcast": {
        "intro_scale": 100,
        "final_scale": 100,
        "scale_dur": 0,
        "fade_in": 60,
        "fade_out": 100,
    },
}

def _chunk_words(words: list[dict], display_mode: str = "phrase") -> list[list[dict]]:
    if display_mode == "word":
        return [[w] for w in words]
    if display_mode == "sentence":
        chunks = []
        current = []
        for w in words:
            current.append(w)
            if any(w.get("word", "").endswith(punct) for punct in [".", "!", "?", "\n"]):
                chunks.append(current)
                current = []
        if current:
            chunks.append(current)
        return chunks if chunks else [words]

    m = re.match(r"(\d+)-words?", display_mode)
    if m:
        max_words = int(m.group(1))
    else:
        max_words = 5

    chunks = []
    current = []
    for w in words:
        current.append(w)
        if len(current) >= max_words or any(w.get("word", "").endswith(punct) for punct in [".", "!", "?"]):
            chunks.append(current)
            current = []
    if current:
        chunks.append(current)
    return chunks if chunks else [words]

def _crop_filter(plan: dict | None, target_w: int, target_h: int) -> str:
    if not plan:
        return f"scale={target_w}:{target_h}:force_original_aspect_ratio=increase,crop={target_w}:{target_h}"
    w = plan.get("w") or plan.get("width")
    h = plan.get("h") or plan.get("height")
    x = plan.get("x", 0)
    y = plan.get("y", 0)
    if not w or not h:
        return f"scale={target_w}:{target_h}:force_original_aspect_ratio=increase,crop={target_w}:{target_h}"
    return f"crop={int(w)}:{int(h)}:{int(x)}:{int(y)},scale={target_w}:{target_h}"

def _blur_pad_filter(target_w: int = 1080, target_h: int = 1920, blur_strength: int = 20) -> str:
    strength = max(1, min(60, int(blur_strength)))
    return (
        f"split[main][bg];"
        f"[bg]scale={target_w}:{target_h}:force_original_aspect_ratio=increase,"
        f"crop={target_w}:{target_h},boxblur={strength}:5[blurred];"
        f"[main]scale={target_w}:{target_h}:force_original_aspect_ratio=decrease[scaled];"
        f"[blurred][scaled]overlay=(W-w)/2:(H-h)/2"
    )

def _validate_filtergraph(filter_str: str) -> bool:
    try:
        res = subprocess.run(
            ["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "nullsrc=s=1080x1920:d=0.1", "-vf", filter_str, "-f", "null", "-"],
            capture_output=True, text=True, timeout=5
        )
        return res.returncode == 0
    except Exception:
        return True

def safe_unlink(filepath: Path | str) -> None:
    path_obj = Path(filepath)
    if not path_obj.exists():
        return
    for attempt in range(5):
        try:
            path_obj.unlink()
            return
        except OSError:
            time.sleep(0.1 * (2 ** attempt))
    try:
        path_obj.unlink(missing_ok=True)
    except Exception:
        pass

def safe_rename(src: Path | str, dst: Path | str) -> None:
    src_obj = Path(src)
    dst_obj = Path(dst)
    for attempt in range(5):
        try:
            if dst_obj.exists():
                dst_obj.unlink()
            src_obj.rename(dst_obj)
            return
        except OSError:
            time.sleep(0.1 * (2 ** attempt))
    try:
        shutil.move(str(src_obj), str(dst_obj))
    except Exception:
        pass

def _hex_to_ass_alpha(hex_color: str, alpha: float) -> str:
    """Convert HTML hex color and alpha multiplier (0.0 to 1.0) to ASS format (&HAABBGGRR)."""
    hex_color = hex_color.lstrip("#")
    r, g, b = "FF", "FF", "FF"
    if len(hex_color) >= 6:
        r, g, b = hex_color[0:2], hex_color[2:4], hex_color[4:6]
    
    # ASS alpha is inversion: 00 is opaque, FF is transparent
    alpha_val = int(round(255 * (1.0 - alpha)))
    alpha_hex = f"{alpha_val:02X}"
    return f"&H{alpha_hex}{b}{g}{r}"

def _get_animation_tags(anim_type: str) -> str:
    tags = {
        "fade": r"{\fad(150,150)}",
        "pop": r"{\fad(40,80)\fscx85\fscy85\t(0,120,\fscx100\fscy100)}",
        "bounce": r"{\fad(30,70)\fscx90\fscy90\t(0,90,\fscx115\fscy115)\t(90,180,\fscx100\fscy100)}",
        "scale": r"{\fscx50\fscy50\t(0,150,\fscx100\fscy100)}",
        "zoom": r"{\fscx0\fscy0\t(0,180,\fscx100\fscy100)}",
        "elastic": r"{\fscx70\fscy70\t(0,100,\fscx122\fscy122)\t(100,200,\fscx95\fscy95)\t(200,280,\fscx100\fscy100)}",
    }
    return tags.get(anim_type, r"")

def _resolve_highlight_color_bgr(color_setting: str, settings: dict) -> str:
    if color_setting in HIGHLIGHT_COLOR_MAP:
        return HIGHLIGHT_COLOR_MAP[color_setting]
    if color_setting.startswith("#"):
        return _hex_to_ass(color_setting)
    custom = settings.get("captionHighlightColor", "")
    if custom.startswith("#"):
        return _hex_to_ass(custom)
    return "&H0000FFFF" # default yellow

def _generate_hook_events(
    clip_metadata: dict,
    settings: dict,
    hook_text: str,
    target_w: int = 1080,
    target_h: int = 1920
) -> str:
    """Generate a single ASS dialogue event for the auto hook overlay using BorderStyle:3.

    Uses ASS opaque-box mode (BorderStyle:3) so that libass itself measures the
    actual rendered text and draws the background rectangle to fit.  This
    eliminates the character-width estimation errors and ``\\p1`` vector-positioning
    bugs that caused background-text misalignment in the previous two-layer
    approach.
    """
    hook_enabled = clip_metadata.get("autoHook", clip_metadata.get("hook2Enabled",
        settings.get("autoHook", settings.get("hook2Enabled", True))))
    if not hook_enabled or not hook_text or not hook_text.strip():
        return ""

    # Design System Standardization: Fixed internal design constants (12px padding, 8px radius)
    HOOK_PADDING = 12
    hook_dur = float(_get_hook_setting("Duration", clip_metadata, settings, 5.0))
    hook_size = int(_get_hook_setting("FontSize", clip_metadata, settings, 120))
    hook_color = _hex_to_ass(str(_get_hook_setting("Color", clip_metadata, settings, "#ffffff")))
    hook_bg = _hex_to_ass(str(_get_hook_setting("BgColor", clip_metadata, settings, "#000000")))
    fade_in = int(_get_hook_setting("FadeIn", clip_metadata, settings, 300))
    fade_out = int(_get_hook_setting("FadeOut", clip_metadata, settings, 500))

    wrap_hook = _wrap_text(hook_text.strip()[:120], max_chars=22)

    # BorderStyle:3 uses \bord as padding around the text inside the opaque box.
    bord_px = max(1, int(HOOK_PADDING * 2.5))

    hook_event = _dialogue_line(
        0.0, hook_dur,
        f"{{\\fs{hook_size}\\bord{bord_px}\\shad0"
        f"\\1c{hook_color}\\3c{hook_bg}\\4c{hook_bg}"
        f"\\fad({fade_in},{fade_out})\\q2}}{wrap_hook}",
        layer=1, style="Hook"
    )
    return hook_event

def _style_header(target_w: int = 1080, target_h: int = 1920,
                  clip_metadata: dict = None, settings: dict = None) -> str:
    if clip_metadata is None:
        clip_metadata = {}
    if settings is None:
        settings = {}

    # Read modular config values with fallbacks
    font_family = clip_metadata.get("captionFontFamily", settings.get("captionFontFamily", "Arial Black"))
    font_size = int(clip_metadata.get("captionFontSize", settings.get("captionFontSize", 72)))
    font_weight = clip_metadata.get("captionFontWeight", settings.get("captionFontWeight", "bold"))
    bold = 1 if font_weight == "bold" else 0

    text_color = _hex_to_ass(clip_metadata.get("captionTextColor", settings.get("captionTextColor", "#ffffff")))
    outline_color = _hex_to_ass(clip_metadata.get("captionOutlineColor", settings.get("captionOutlineColor", "#000000")))
    shadow_color = _hex_to_ass(clip_metadata.get("captionShadowColor", settings.get("captionShadowColor", "#000000")))
    bg_color = _hex_to_ass(clip_metadata.get("captionBgColor", settings.get("captionBgColor", "#000000")))

    container_type = clip_metadata.get("captionContainerType", settings.get("captionContainerType", "none"))
    outline_size = int(clip_metadata.get("captionOutlineSize", settings.get("captionOutlineSize", 3)))
    shadow_size = int(clip_metadata.get("captionShadowSize", settings.get("captionShadowSize", 2)))
    padding = int(clip_metadata.get("captionPadding", settings.get("captionPadding", 12)))

    border_style = 1
    outline = outline_size
    shadow = shadow_size
    out_col = outline_color
    back_col = shadow_color

    if container_type == "solid":
        border_style = 3
        outline = padding
        shadow = 0
        out_col = bg_color
        back_col = bg_color
    elif container_type == "transparent-box":
        border_style = 3
        outline = padding
        shadow = 0
        out_col = _hex_to_ass_alpha(clip_metadata.get("captionBgColor", settings.get("captionBgColor", "#000000")), 0.6)
        back_col = out_col
    elif container_type == "outline":
        border_style = 1
        outline = max(outline_size, 5)
        shadow = 0
    elif container_type == "shadow":
        border_style = 1
        outline = 0
        shadow = max(shadow_size, 4)
    elif container_type == "glow":
        border_style = 1
        outline = outline_size
        shadow = 0
    elif container_type == "border-only":
        border_style = 1
        outline = outline_size
        shadow = 0
        text_color = "&HFFFFFFFF" # transparent text

    # Position mapping
    pos_mode = clip_metadata.get("captionPosition", settings.get("captionPosition", "bottom"))
    margin_v = 170
    alignment = 2

    if pos_mode == "top":
        alignment = 8
        margin_v = 170
    elif pos_mode == "top-center":
        alignment = 8
        margin_v = 300
    elif pos_mode == "center":
        alignment = 5
        margin_v = 0
    elif pos_mode == "lower-third":
        alignment = 2
        margin_v = 350
    elif pos_mode == "bottom":
        alignment = 2
        margin_v = 170
    elif pos_mode == "custom":
        margin_v = int(clip_metadata.get("captionCustomMarginV", settings.get("captionCustomMarginV", 170)))
        alignment = 2

    # Single unified Auto Hook styling (fixed internal design constants: 12px padding, 8px radius)
    HOOK_PADDING = 12
    hook_font = _get_hook_setting("Font", clip_metadata, settings, "Arial Black")
    hook_size = int(_get_hook_setting("FontSize", clip_metadata, settings, 120))
    hook_color = _hex_to_ass(str(_get_hook_setting("Color", clip_metadata, settings, "#ffffff")))
    hook_bg = _hex_to_ass(str(_get_hook_setting("BgColor", clip_metadata, settings, "#000000")))

    hook_pos = _get_hook_setting("Position", clip_metadata, settings, "top-center")
    if hook_pos == "top":
        hook_align = 8
        hook_margin_v = 150
    elif hook_pos == "middle":
        hook_align = 5
        hook_margin_v = 0
    else:  # top-center (default)
        hook_align = 8
        hook_margin_v = 220

    # ASS Style format
    return (
        "[Script Info]\n"
        "ScriptType: v4.00+\n"
        f"PlayResX: {target_w}\n"
        f"PlayResY: {target_h}\n"
        "ScaledBorderAndShadow: yes\n\n"
        "[V4+ Styles]\n"
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, "
        "OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, "
        "ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, "
        "Alignment, MarginL, MarginR, MarginV, Encoding\n"
        f"Style: Default,{font_family},{font_size},"
        f"{text_color},{text_color},{out_col},{back_col},"
        f"{bold},0,0,0,100,100,0,0,{border_style},"
        f"{outline},{shadow},{alignment},80,80,"
        f"{margin_v},1\n"
        f"Style: Hook,{hook_font},{hook_size},"
        f"{hook_color},{hook_color},{hook_bg},{hook_bg},"
        f"1,0,0,0,100,100,0,0,3,0,0,{hook_align},80,80,{hook_margin_v},1\n\n"
        "[Events]\n"
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
    )

def _dialogue_line(start: float, end: float, text: str, layer: int = 0,
                    style: str = "Default") -> str:
    return f"Dialogue: {layer},{_ass_time(start)},{_ass_time(end)},{style},,0,0,0,,{text}\n"

def _wrap_chunk_words(
    times: list[dict],
    highlight_index: int,
    highlight_color: str,
    highlight_mode: str = "single",
    final_scale: int = 100,
    max_chars: int = 22,
) -> str:
    """Build one wrapped line of text with a single highlighted word."""
    lines = []
    current_line = []
    current_len = 0
    active_scale = int(round(final_scale * 1.15)) if highlight_mode == "creator" else int(round(final_scale * 1.12))
    
    for j, t in enumerate(times):
        word_text = t["word"]
        word_len = len(word_text)
        added_len = word_len + (1 if current_line else 0)
        
        if current_len + added_len > max_chars:
            if current_line:
                lines.append(" ".join(current_line))
            current_line = []
            current_len = 0
            
        if j == highlight_index and highlight_mode != "none":
            color = highlight_color
            if highlight_mode == "multi":
                color = MULTI_COLOR_PALETTE[highlight_index % len(MULTI_COLOR_PALETTE)]
            elif highlight_mode == "random":
                color = MULTI_COLOR_PALETTE[(highlight_index * 7) % len(MULTI_COLOR_PALETTE)]
                
            word_display = word_text.upper() if highlight_mode == "creator" else word_text
            formatted_word = f"{{\\c{color}\\fscx{active_scale}\\fscy{active_scale}}}{word_display}{{\\fscx{final_scale}\\fscy{final_scale}\\c}}"
        else:
            formatted_word = word_text
            
        current_line.append(formatted_word)
        current_len += word_len + (1 if len(current_line) > 1 else 0)
        
    if current_line:
        lines.append(" ".join(current_line))
    return "\\N".join(lines)

def _word_highlight_lines(
    chunk: list[dict],
    highlight_ass_color: str,
    highlight_mode: str = "single",
    next_start: float | None = None,
    uppercase: bool = False,
    final_scale: int = 100,
) -> list[str]:
    """Generate consecutive dialogue events to highlight one word at a time."""
    chunk_start = max(0.0, float(chunk[0]["start"]))
    chunk_end = max(float(chunk[-1]["end"]), chunk_start + 0.4)
    if next_start is not None:
        chunk_end = min(chunk_end, next_start)

    times = []
    for idx, w in enumerate(chunk):
        w_text = str(w.get("word", "")).strip().lstrip(",.?!:; -")
        w_text = _escape_ass(w_text)
        if not w_text:
            continue
        times.append({
            "index": idx,
            "word": w_text.upper() if uppercase else w_text,
            "start": max(0.0, float(w["start"])),
            "end": max(float(w["end"]), float(w["start"]) + 0.05),
        })

    if not times:
        fallback_text = " ".join(str(w["word"]).strip() for w in chunk)
        if uppercase:
            fallback_text = fallback_text.upper()
        fallback_wrapped = _wrap_text(fallback_text, max_chars=22)
        return [_dialogue_line(chunk_start, chunk_end, fallback_wrapped)]

    for i in range(len(times) - 1):
        if times[i]["end"] < times[i + 1]["start"]:
            times[i]["end"] = times[i + 1]["start"]

    lines = []

    # Leading silence
    if chunk_start < times[0]["start"]:
        full_text = " ".join(t["word"] for t in times)
        lines.append(_dialogue_line(chunk_start, times[0]["start"], _wrap_text(full_text, max_chars=22)))

    # One event per highlighted word
    for curr in times:
        wrapped_line = _wrap_chunk_words(
            times,
            curr["index"],
            highlight_ass_color,
            highlight_mode=highlight_mode,
            final_scale=final_scale,
            max_chars=22
        )
        lines.append(_dialogue_line(curr["start"], curr["end"], wrapped_line))

    # Trailing silence
    if times[-1]["end"] < chunk_end:
        full_text = " ".join(t["word"] for t in times)
        lines.append(_dialogue_line(times[-1]["end"], chunk_end, _wrap_text(full_text, max_chars=22)))

    return lines

def _caption_lines(
    chunk: list[dict],
    chunk_index: int = 0,
    highlight_color_mode: str = "single",
    highlight_color: str = "yellow",
    next_start: float | None = None,
    settings: dict = None,
) -> list[str]:
    """Generate caption ASS lines for dynamic modular formatting."""
    if settings is None:
        settings = {}

    anim_type = settings.get("captionAnimationType", "none")
    container_type = settings.get("captionContainerType", "none")
    highlight_mode = settings.get("highlightColorMode", "single")
    final_scale = 100

    font_preset = settings.get("captionFontPreset", "bold")
    uppercase = font_preset in ("bold", "creator")

    resolved_color = _resolve_highlight_color_bgr(highlight_color, settings)

    lines = _word_highlight_lines(
        chunk,
        resolved_color,
        highlight_mode=highlight_mode,
        next_start=next_start,
        uppercase=uppercase,
        final_scale=final_scale
    )
    total = len(lines)
    if total == 0:
        return lines

    anim_tags = _get_animation_tags(anim_type)
    if container_type == "glow":
        if anim_tags.startswith("{") and anim_tags.endswith("}"):
            anim_tags = anim_tags[:-1] + r"\blur6" + "}"
        else:
            anim_tags = r"{\blur6}"

    for idx in range(total):
        line_tags = anim_tags
        if anim_type == "fade":
            if total > 1:
                if idx == 0:
                    line_tags = r"{\fad(150,0)}"
                elif idx == total - 1:
                    line_tags = f"{{\\fad(0,150)}}"
                else:
                    line_tags = r""

        if line_tags:
            parts = lines[idx].rsplit(",,", 1)
            if len(parts) == 2:
                lines[idx] = parts[0] + ",," + line_tags + parts[1]

    return lines


def _wrap_text(text: str, max_chars: int = 22) -> str:
    words = text.split()
    lines = []
    current_line = []
    current_len = 0
    for word in words:
        if current_len + len(word) + (1 if current_line else 0) > max_chars:
            if current_line:
                lines.append(" ".join(current_line))
            current_line = [word]
            current_len = len(word)
        else:
            current_line.append(word)
            current_len += len(word) + (1 if len(current_line) > 1 else 0)
    if current_line:
        lines.append(" ".join(current_line))
    return "\\N".join(_escape_ass(l) for l in lines)

def _get_duration(video_path: Path | str) -> float:
    cmd = [
        "ffprobe", "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        str(video_path)
    ]
    res = subprocess.run(cmd, capture_output=True, text=True)
    try:
        return float(res.stdout.strip())
    except Exception:
        return 5.0

def _prepend_meme(meme_path: Path | str, meme_dur: float, clip_path: Path | str, out_path: Path | str, target_w: int = 1080, target_h: int = 1920) -> None:
    filter_complex = (
        f"[0:v]scale={target_w}:{target_h}:force_original_aspect_ratio=increase,"
        f"crop={target_w}:{target_h},fps=25,setsar=1[v0];"
        f"[1:v]scale={target_w}:{target_h}:force_original_aspect_ratio=increase,"
        f"crop={target_w}:{target_h},fps=25,setsar=1[v1];"
        f"[0:a]aresample=44100,aformat=sample_fmts=fltp:channel_layouts=stereo,atrim=0:{meme_dur:.3f},asetpts=PTS-STARTPTS[a0];"
        f"[1:a]aresample=44100,aformat=sample_fmts=fltp:channel_layouts=stereo[a1];"
        f"[v0][a0][v1][a1]concat=n=2:v=1:a=1[vout][aout]"
    )
    cmd = [
        "ffmpeg", "-y",
        "-i", str(meme_path),
        "-i", str(clip_path),
        "-filter_complex", filter_complex,
        "-map", "[vout]", "-map", "[aout]",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
        "-c:a", "aac", "-movflags", "+faststart",
        str(out_path)
    ]
    run_command(cmd)

def main():
    parser = argparse.ArgumentParser(description="AI Shorts Generator Retrimmer")
    parser.add_argument("--job-id", required=True, help="Job ID")
    parser.add_argument("--clip-id", required=True, help="Clip ID to re-trim")
    args = parser.parse_args()

    root = Path(__file__).resolve().parent.parent.parent
    storage_root = Path(os.environ.get("STORAGE_PATH", root / "storage")).resolve()
    upload_dir = storage_root / "uploads" / args.job_id
    output_dir = storage_root / "outputs" / args.job_id
    temp_dir = storage_root / "temp" / args.job_id
    temp_dir.mkdir(parents=True, exist_ok=True)

    # Verify upload directory exists before proceeding
    if not upload_dir.exists():
        msg = f"Original uploaded video not found. Upload directory missing: {upload_dir}"
        print(json.dumps({"stage": "Error", "error": msg, "progress": 0}), flush=True)
        raise FileNotFoundError(msg)

    input_video = find_input_video(upload_dir)
    clips_json_path = output_dir / "clips.json"

    if not clips_json_path.exists():
        raise FileNotFoundError(f"clips.json not found at {clips_json_path}")

    clips_data = json.loads(clips_json_path.read_text(encoding="utf-8"))
    clip = next((c for c in clips_data.get("clips", []) if c.get("id") == args.clip_id), None)

    if not clip:
        raise ValueError(f"Clip {args.clip_id} not found in clips.json")

    start = float(clip["start"])
    end = float(clip["end"])
    duration = end - start

    # Read project settings (check project.json / temp settings / global config)
    settings = {}
    project_json_path = output_dir / "project.json"
    temp_settings_path = temp_dir / "settings.json"
    upload_project_path = storage_root / "uploads" / args.job_id / "project.json"
    global_settings_path = storage_root / "config" / "settings.json"

    for p in [project_json_path, temp_settings_path, upload_project_path, global_settings_path]:
        if p.exists():
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
                s = data.get("settings", data) if "settings" in data else data
                if s and isinstance(s, dict):
                    settings = s
                    break
            except Exception:
                pass

    # Load per-clip metadata overrides
    metadata_path = output_dir / "metadata" / f"{args.clip_id}.json"
    clip_metadata = {}
    if metadata_path.exists():
        clip_metadata = json.loads(metadata_path.read_text(encoding="utf-8"))

    # Override MULTI_COLOR_PALETTE if custom colors are provided in settings or overrides
    custom_multi = clip_metadata.get("captionMultiColors", settings.get("captionMultiColors", None))
    if custom_multi and isinstance(custom_multi, list):
        global MULTI_COLOR_PALETTE
        MULTI_COLOR_PALETTE = [_hex_to_ass(c) for c in custom_multi if c]

    # Resolve target dimensions from aspect ratio override
    frame_aspect = clip_metadata.get("frameAspect", "9:16")
    if frame_aspect == "16:9":
        SHORTS_W, SHORTS_H = 1920, 1080
    else:
        SHORTS_W, SHORTS_H = 1080, 1920

    # 1. Regenerate subtitles .ass file
    transcript_path = temp_dir / "transcript.json"
    if transcript_path.exists():
        transcript = json.loads(transcript_path.read_text(encoding="utf-8"))
        words = transcript.get("words", [])
        clip_words = [
            {
                **word,
                "start": float(word["start"]) - start,
                "end": float(word["end"]) - start,
            }
            for word in words
            if float(word["end"]) > start and float(word["start"]) < end
        ]

        merged_settings = {**settings, **clip_metadata}
        display_mode = merged_settings.get("captionDisplayMode", "phrase")
        highlight_color_mode = merged_settings.get("highlightColorMode", "single")
        highlight_color = merged_settings.get("captionHighlightColor", merged_settings.get("highlightColor", "yellow"))

        captions_dir = output_dir / "captions"
        captions_dir.mkdir(parents=True, exist_ok=True)
        ass_path = captions_dir / f"{args.clip_id}.ass"

        ass_text = _style_header(SHORTS_W, SHORTS_H, clip_metadata, settings)

        # Subtitle chunks — pass next_start for precise timing
        chunks = _chunk_words(clip_words, display_mode)
        for chunk_index, chunk in enumerate(chunks):
            next_start = float(chunks[chunk_index + 1][0]["start"]) if chunk_index + 1 < len(chunks) else None
            ass_text += "".join(_caption_lines(
                chunk,
                chunk_index=chunk_index,
                highlight_color_mode=highlight_color_mode,
                highlight_color=highlight_color,
                next_start=next_start,
                settings=merged_settings
            ))

        ass_path.write_text(ass_text, encoding="utf-8")
    else:
        ass_path = None

    # 1.5 Render Hook Overlay PNG (independent of transcript file state)
    hook_enabled = resolve_hook_enabled(clip_metadata, settings)
    hook_text = resolve_hook_text(clip_metadata, settings, clip)
    hook_png_path = temp_dir / f"{args.clip_id}_hook.png"
    use_hook_png = False

    if hook_enabled and hook_text:
        font_family = str(_get_hook_setting("Font", clip_metadata, settings, "Arial Black"))
        font_size = int(_get_hook_setting("FontSize", clip_metadata, settings, 76))
        text_color = str(_get_hook_setting("Color", clip_metadata, settings, "#ffffff"))
        bg_color = str(_get_hook_setting("BgColor", clip_metadata, settings, "#16a34a"))
        position = str(_get_hook_setting("Position", clip_metadata, settings, "top-center"))

        render_hook_overlay_png(
            text=hook_text,
            font_family=font_family,
            font_size=font_size,
            text_color=text_color,
            bg_color=bg_color,
            position=position,
            output_path=hook_png_path,
            canvas_w=SHORTS_W,
            canvas_h=SHORTS_H,
        )
        use_hook_png = hook_png_path.exists()
        print(f"[AutoHook] Rendered retrim Hook PNG for {args.clip_id}: text='{hook_text}'", flush=True)

    crop_plan = clip.get("crop")
    camera_plan = clip.get("cameraPlan") or clip.get("camera_plan")
    camera_curve = clip.get("cameraCurve") or clip.get("camera_curve")
    layout_segments = clip.get("layoutSegments", [])

    temp_clip_path = temp_dir / f"{args.clip_id}_trimmed_temp.mp4"
    final_clip_dir = output_dir / "clips"
    final_clip_dir.mkdir(parents=True, exist_ok=True)
    final_clip_path = final_clip_dir / f"{args.clip_id}.mp4"

    # Check if user explicitly set a framing layoutMode in clip_metadata
    layout_override = clip_metadata.get("layoutMode")
    if layout_override and layout_override in ("full-crop", "blur-pad"):
        layout_segments = [{"start": start, "end": end, "layout": layout_override}]
    elif not layout_segments:
        layout_mode = clip.get("layoutMode", "full-crop")
        layout_segments = [{"start": start, "end": end, "layout": layout_mode}]

    # Pipeline Integrity Verification: Fail loudly if dynamic camera movement is required but canonical cameraPlan is missing
    active_layout = layout_override or clip.get("layoutMode", "full-crop")
    if active_layout in ("full-crop", "auto-dynamic") and not camera_plan and not camera_curve:
        err_msg = f"[Pipeline Integrity Error] Clip '{args.clip_id}' requires dynamic camera movement ({active_layout}) but canonical cameraPlan is missing. Check Stage 08C (Camera Operator) or Stage 08D (Transition Planner)."
        print(json.dumps({"stage": "Error", "error": err_msg, "progress": 0}), flush=True)
        raise ValueError(err_msg)

    # Ensure fresh encoding of video layout with latest crop plan & canonical camera movement
    raw_path = temp_dir / f"{args.clip_id}_raw_retrim.mp4"
    safe_unlink(raw_path)
    print(json.dumps({"stage": "Encoding Video Layout...", "progress": 15}))
    sys.stdout.flush()
    encode_clip_with_layout_transitions(
        input_video=str(input_video),
        clip_start=start,
        clip_duration=duration,
        segments=layout_segments,
        plan=crop_plan,
        output_path=str(raw_path),
        target_w=SHORTS_W,
        target_h=SHORTS_H,
        blur_strength=clip_metadata.get("blurStrength", 20),
        camera_plan=camera_plan,
        camera_curve=camera_curve,
    )

    # Apply captions & hooks on top of the raw clip
    print(json.dumps({"stage": "Rendering Captions & Hooks...", "progress": 55}))
    sys.stdout.flush()

    if ass_path or use_hook_png:
        ass_filter_path = str(ass_path).replace("\\", "/").replace(":", r"\:") if ass_path else None
        if use_hook_png:
            dur_mode = str(_get_hook_setting("DurationMode", clip_metadata, settings, "custom"))
            clip_dur = float(duration)
            if dur_mode == "entire":
                hook_dur = clip_dur
            else:
                hook_dur = float(_get_hook_setting("Duration", clip_metadata, settings, 5.0))
            fade_in_s = float(_get_hook_setting("FadeIn", clip_metadata, settings, 300)) / 1000.0
            fade_out_s = float(_get_hook_setting("FadeOut", clip_metadata, settings, 500)) / 1000.0
            st_out = max(0.0, hook_dur - fade_out_s)

            filter_complex = (
                f"[1:v]fade=t=in:st=0:d={fade_in_s:.2f}:alpha=1,"
                f"fade=t=out:st={st_out:.2f}:d={fade_out_s:.2f}:alpha=1[hook_overlay];"
                f"[0:v][hook_overlay]overlay=0:0:enable='between(t,0,{hook_dur:.2f})'"
            )
            if ass_filter_path:
                filter_complex += f",ass='{ass_filter_path}'[vout]"
            else:
                filter_complex += "[vout]"

            cmd = [
                "ffmpeg", "-y",
                "-i", str(raw_path),
                "-loop", "1",
                "-i", str(hook_png_path),
                "-filter_complex", filter_complex,
                "-map", "[vout]", "-map", "0:a?",
                "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
                "-c:a", "copy", "-shortest", "-movflags", "+faststart",
                str(temp_clip_path),
            ]
            print(f"[AutoHook] Executing retrim FFmpeg with -loop 1 PNG overlay:\n  {' '.join(cmd)}", flush=True)
            run_command(cmd)
        else:
            cmd = [
                "ffmpeg", "-y",
                "-i", str(raw_path),
                "-vf", f"ass='{ass_filter_path}'",
                "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
                "-c:a", "copy", "-movflags", "+faststart",
                str(temp_clip_path),
            ]
            print(f"[AutoHook] Executing retrim FFmpeg (no Hook PNG):\n  {' '.join(cmd)}", flush=True)
            run_command(cmd)
    else:
        if raw_path != temp_clip_path:
            shutil.copy(str(raw_path), str(temp_clip_path))

    # 3. Apply background music if exists
    print(json.dumps({"stage": "Mixing Audio...", "progress": 75}))
    sys.stdout.flush()
    bg_music_enabled = clip_metadata.get("backgroundMusic", settings.get("backgroundMusic", bool(clip.get("musicTrack"))))
    music_track = clip_metadata.get("musicTrack", clip.get("musicTrack", settings.get("musicTrack", None)))
    music_volume = clip_metadata.get("musicVolume", clip.get("musicVolume", settings.get("musicVolume", 20)))
    if not bg_music_enabled:
        music_track = None

    if music_track and Path(music_track).exists() and music_volume is not None:
        volume = float(music_volume) / 100
        # Scale fade duration proportionally for short clips
        fade_d = min(1.0, duration * 0.25)
        fade_out_st = max(0, duration - fade_d)

        if duration < 0.5:
            # Extremely short clip — skip fades
            music_filter = (
                f"[1:a]volume={volume:.3f}[music];"
                "[0:a][music]amix=inputs=2:duration=first:dropout_transition=0[aout]"
            )
        else:
            music_filter = (
                f"[1:a]volume={volume:.3f},"
                f"afade=t=in:st=0:d={fade_d:.3f},"
                f"afade=t=out:st={fade_out_st:.3f}:d={fade_d:.3f}[music];"
                "[0:a][music]amix=inputs=2:duration=first:dropout_transition=0[aout]"
            )

        source_has_audio = has_audio_stream(temp_clip_path)

        if source_has_audio:
            run_command([
                "ffmpeg", "-y",
                "-i", str(temp_clip_path),
                "-stream_loop", "-1",
                "-i", str(music_track),
                "-filter_complex", music_filter,
                "-map", "0:v:0", "-map", "[aout]",
                "-c:v", "copy", "-c:a", "aac",
                "-shortest", "-movflags", "+faststart",
                str(final_clip_path),
            ])
        else:
            # Source has no audio — generate silent base and mix with music
            silent_filter = (
                f"[1:a]atrim=0:{duration:.3f},asetpts=PTS-STARTPTS[silent];"
                f"[2:a]volume={volume:.3f},"
                f"afade=t=in:st=0:d={fade_d:.3f},"
                f"afade=t=out:st={fade_out_st:.3f}:d={fade_d:.3f}[music];"
                "[silent][music]amix=inputs=2:duration=first:dropout_transition=0[aout]"
            )
            run_command([
                "ffmpeg", "-y",
                "-i", str(temp_clip_path),
                "-f", "lavfi", "-i", f"anullsrc=channel_layout=stereo:sample_rate=44100",
                "-stream_loop", "-1",
                "-i", str(music_track),
                "-filter_complex", silent_filter,
                "-map", "0:v:0", "-map", "[aout]",
                "-c:v", "copy", "-c:a", "aac",
                "-shortest", "-movflags", "+faststart",
                str(final_clip_path),
            ])
        safe_unlink(temp_clip_path)
    else:
        safe_unlink(final_clip_path)
        shutil.copy(str(temp_clip_path), str(final_clip_path))
        safe_unlink(temp_clip_path)

    # 3.5 Prepend Meme Hook if enabled
    meme_path = clip_metadata.get("memePath")
    if meme_path and Path(meme_path).exists():
        print(json.dumps({"stage": "Prepending Meme Hook...", "progress": 85}))
        sys.stdout.flush()
        meme_duration = _get_duration(meme_path)
        temp_meme_out = temp_dir / f"{args.clip_id}_meme_final.mp4"
        _prepend_meme(meme_path, meme_duration, str(final_clip_path), str(temp_meme_out), SHORTS_W, SHORTS_H)
        safe_unlink(final_clip_path)
        safe_rename(temp_meme_out, final_clip_path)

    # 4. Regenerate thumbnail image using OpenCV
    print(json.dumps({"stage": "Regenerating Thumbnail...", "progress": 95}))
    sys.stdout.flush()
    thumbnails_dir = output_dir / "thumbnails"
    thumbnails_dir.mkdir(parents=True, exist_ok=True)
    thumbnail_path = thumbnails_dir / f"{args.clip_id}.png"

    cap = cv2.VideoCapture(str(final_clip_path))
    ret, frame = cap.read()
    if ret:
        cv2.imwrite(str(thumbnail_path), frame)
    cap.release()

    print(json.dumps({
        "success": True,
        "clipId": args.clip_id,
        "path": str(final_clip_path),
        "thumbnail": str(thumbnail_path)
    }))

if __name__ == "__main__":
    main()
