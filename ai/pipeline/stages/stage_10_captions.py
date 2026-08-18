import json
import re
from typing import Any

from media_utils import run_command
from hook_renderer import render_hook_overlay_png, resolve_hook_text, resolve_hook_enabled


# ═══════════════════════════════════════════════════════════════════════════════
#  14 Professional Caption Style Presets
# ═══════════════════════════════════════════════════════════════════════════════

STYLE_DEFINITIONS = {
    "classic-white": {
        "font": "Arial",
        "font_size": 72,
        "primary": "&H00FFFFFF",
        "outline": "&H00000000",
        "back": "&H80000000",
        "bold": 1,
        "outline_size": 4,
        "shadow": 2,
        "alignment": 2,
        "margin_v": 170,
        "border_style": 1,
    },
    "green-highlight": {
        "font": "Arial",
        "font_size": 72,
        "primary": "&H00FFFFFF",
        "outline": "&H00000000",
        "back": "&H80000000",
        "bold": 1,
        "outline_size": 4,
        "shadow": 2,
        "alignment": 2,
        "margin_v": 170,
        "border_style": 1,
    },
    "yellow-highlight": {
        "font": "Arial",
        "font_size": 72,
        "primary": "&H00FFFFFF",
        "outline": "&H00000000",
        "back": "&H80000000",
        "bold": 1,
        "outline_size": 4,
        "shadow": 2,
        "alignment": 2,
        "margin_v": 170,
        "border_style": 1,
    },
    "blue-highlight": {
        "font": "Arial",
        "font_size": 72,
        "primary": "&H00FFFFFF",
        "outline": "&H00000000",
        "back": "&H80000000",
        "bold": 1,
        "outline_size": 4,
        "shadow": 2,
        "alignment": 2,
        "margin_v": 170,
        "border_style": 1,
    },
    "red-highlight": {
        "font": "Arial",
        "font_size": 72,
        "primary": "&H00FFFFFF",
        "outline": "&H00000000",
        "back": "&H80000000",
        "bold": 1,
        "outline_size": 4,
        "shadow": 2,
        "alignment": 2,
        "margin_v": 170,
        "border_style": 1,
    },
    "boxed": {
        "font": "Arial",
        "font_size": 68,
        "primary": "&H00FFFFFF",
        "outline": "&H00000000",
        "back": "&HA0000000",
        "bold": 1,
        "outline_size": 2,
        "shadow": 0,
        "alignment": 2,
        "margin_v": 180,
        "border_style": 3,
    },
    "outline": {
        "font": "Arial",
        "font_size": 78,
        "primary": "&H00FFFFFF",
        "outline": "&H00000000",
        "back": "&H80000000",
        "bold": 1,
        "outline_size": 7,
        "shadow": 4,
        "alignment": 2,
        "margin_v": 170,
        "border_style": 1,
    },
    "bold-pop": {
        "font": "Arial Black",
        "font_size": 92,
        "primary": "&H00FFFFFF",
        "outline": "&H00000000",
        "back": "&H80000000",
        "bold": 1,
        "outline_size": 6,
        "shadow": 2,
        "alignment": 2,
        "margin_v": 210,
        "border_style": 1,
    },
    "karaoke-bounce": {
        "font": "Arial",
        "font_size": 86,
        "primary": "&H00FFFFFF",
        "outline": "&H00202020",
        "back": "&H80000000",
        "bold": 1,
        "outline_size": 5,
        "shadow": 3,
        "alignment": 5,
        "margin_v": 0,
        "border_style": 1,
    },
    "minimal": {
        "font": "Arial",
        "font_size": 60,
        "primary": "&H00FFFFFF",
        "outline": "&H00000000",
        "back": "&H00000000",
        "bold": 0,
        "outline_size": 2,
        "shadow": 0,
        "alignment": 2,
        "margin_v": 160,
        "border_style": 1,
    },
    "creator": {
        "font": "Arial Black",
        "font_size": 80,
        "primary": "&H00FFFFFF",
        "outline": "&H00000000",
        "back": "&H80000000",
        "bold": 1,
        "outline_size": 5,
        "shadow": 3,
        "alignment": 2,
        "margin_v": 200,
        "border_style": 1,
    },
    "viral-shorts": {
        "font": "Arial Black",
        "font_size": 88,
        "primary": "&H00FFFFFF",
        "outline": "&H00141414",
        "back": "&HA0000000",
        "bold": 1,
        "outline_size": 6,
        "shadow": 4,
        "alignment": 2,
        "margin_v": 190,
        "border_style": 1,
    },
    "tiktok": {
        "font": "Arial",
        "font_size": 74,
        "primary": "&H00FFFFFF",
        "outline": "&H00000000",
        "back": "&HB0000000",
        "bold": 1,
        "outline_size": 3,
        "shadow": 1,
        "alignment": 2,
        "margin_v": 170,
        "border_style": 3,
    },
    "podcast": {
        "font": "Arial",
        "font_size": 66,
        "primary": "&H00FFFFFF",
        "outline": "&H00000000",
        "back": "&H90000000",
        "bold": 1,
        "outline_size": 3,
        "shadow": 1,
        "alignment": 2,
        "margin_v": 160,
        "border_style": 3,
    },
}

# Legacy aliases
LEGACY_STYLE_MAP = {
    "word-highlight": "classic-white",
    "boxed-background": "boxed",
    "outline-shadow": "outline",
}

# Default highlight colors per named style (ASS BGR)
STYLE_DEFAULT_HIGHLIGHT = {
    "classic-white": "&H0000FFFF",    # Yellow
    "green-highlight": "&H0000FF00",  # Green
    "yellow-highlight": "&H0000FFFF", # Yellow
    "blue-highlight": "&H00FF8000",   # Blue
    "red-highlight": "&H000000FF",    # Red
}

# Multi-color palette (ASS BGR format)
MULTI_COLOR_PALETTE = [
    "&H0000FFFF",  # Yellow
    "&H0000FF00",  # Green
    "&H000000FF",  # Red
    "&H00FFFF00",  # Cyan
]

HIGHLIGHT_COLOR_MAP = {
    "yellow": "&H0000FFFF",
    "green": "&H0000FF00",
    "red": "&H000000FF",
    "cyan": "&H00FFFF00",
}

# Position mapping
POSITION_MAP = {
    "bottom": {"alignment": 2, "margin_v": 170},
    "center": {"alignment": 5, "margin_v": 0},
    "top": {"alignment": 8, "margin_v": 170},
}


# ═══════════════════════════════════════════════════════════════════════════════
#  ASS helpers
# ═══════════════════════════════════════════════════════════════════════════════

def _resolve_style(name: str) -> str:
    """Resolve legacy style names to new names."""
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
    """Convert HTML hex color (#RRGGBB) to ASS BGR format (&HAABBGGRR)."""
    if not hex_color:
        return "&H00FFFFFF"
    hex_color = hex_color.lstrip("#")
    if len(hex_color) == 6:
        r, g, b = hex_color[0:2], hex_color[2:4], hex_color[4:6]
        return f"&H00{b}{g}{r}"
    return "&H00FFFFFF"


# ═══════════════════════════════════════════════════════════════════════════════
#  Display mode chunking
# ═══════════════════════════════════════════════════════════════════════════════

def _chunk_words(words: list[dict], display_mode: str = "phrase") -> list[list[dict]]:
    """
    Chunk words based on display mode:
      - "word":     1 word per chunk
      - "phrase":   3–6 words, break on punctuation
      - "sentence": entire sentence (break on . ? !)
    """
    if display_mode == "word":
        return [[w] for w in words]

    if display_mode == "sentence":
        chunks = []
        current = []
        for word in words:
            current.append(word)
            if str(word["word"]).rstrip().endswith((".", "?", "!")):
                chunks.append(current)
                current = []
        if current:
            chunks.append(current)
        return chunks if chunks else [[w] for w in words]

    # Support numeric word count modes: "2-words", "3-words", etc.
    m = re.match(r"(\d+)-words?", display_mode)
    if m:
        max_words = int(m.group(1))
    else:
        max_words = 5  # default phrase mode
    chunks = []
    current = []
    for word in words:
        current.append(word)
        if len(current) >= max_words or str(word["word"]).rstrip().endswith((".", "?", "!")):
            chunks.append(current)
            current = []
    if current:
        chunks.append(current)
    return chunks


# ═══════════════════════════════════════════════════════════════════════════════
#  ASS file generation
# ═══════════════════════════════════════════════════════════════════════════════

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

    # Single unified Auto Hook styling
    hook_font = _get_hook_setting("Font", clip_metadata, settings, "Arial Black")
    hook_size = int(_get_hook_setting("FontSize", clip_metadata, settings, 120))
    hook_color = _hex_to_ass(str(_get_hook_setting("Color", clip_metadata, settings, "#ffffff")))
    hook_bg = _hex_to_ass(str(_get_hook_setting("BgColor", clip_metadata, settings, "#000000")))
    hook_padding = int(_get_hook_setting("Padding", clip_metadata, settings, 12))

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


def _chunk_text(chunk: list[dict], uppercase: bool = False) -> str:
    cleaned_words = []
    for w in chunk:
        w_text = str(w.get("word", "")).strip().lstrip(",.?!:; -")
        if w_text:
            cleaned_words.append(w_text.upper() if uppercase else w_text)
    text = " ".join(cleaned_words)
    return _escape_ass(text)


# ═══════════════════════════════════════════════════════════════════════════════
#  Highlight color resolution
# ═══════════════════════════════════════════════════════════════════════════════

def _resolve_highlight_color(
    chunk_index: int = 0,
    highlight_color_mode: str = "single",
    highlight_color: str = "yellow",
) -> str:
    if highlight_color_mode == "multi":
        return MULTI_COLOR_PALETTE[chunk_index % len(MULTI_COLOR_PALETTE)]
    return HIGHLIGHT_COLOR_MAP.get(highlight_color, "&H0000FFFF")


# ═══════════════════════════════════════════════════════════════════════════════
#  Two-layer word highlight (works for ALL styles)
# ═══════════════════════════════════════════════════════════════════════════════

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


def _hex_to_ass_alpha(hex_color: str, alpha: float) -> str:
    """Convert HTML hex color and alpha multiplier (0.0 to 1.0) to ASS format (&HAABBGGRR)."""
    hex_color = hex_color.lstrip("#")
    r, g, b = "FF", "FF", "FF"
    if len(hex_color) >= 6:
        r, g, b = hex_color[0:2], hex_color[2:4], hex_color[4:6]
    
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

# ═══════════════════════════════════════════════════════════════════════════════
#  Caption line generation (unified for all styles)
# ═══════════════════════════════════════════════════════════════════════════════

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


# ═══════════════════════════════════════════════════════════════════════════════
#  Auto Hook overlay
# ═══════════════════════════════════════════════════════════════════════════════

def _wrap_text(text: str, max_chars: int = 22) -> str:
    """Wrap text to prevent overflows outside the video frame boundaries."""
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


# ═══════════════════════════════════════════════════════════════════════════════
#  Main pipeline entry
# ═══════════════════════════════════════════════════════════════════════════════

def run(context):
    captions_dir = context["output_dir"] / "captions"
    captioned_dir = context["temp_dir"] / "captioned_clips"
    captions_dir.mkdir(parents=True, exist_ok=True)
    captioned_dir.mkdir(parents=True, exist_ok=True)

    # Read settings
    settings = context["settings"]
    
    # Override MULTI_COLOR_PALETTE if custom colors are provided in settings
    custom_multi = settings.get("captionMultiColors", None)
    if custom_multi and isinstance(custom_multi, list):
        global MULTI_COLOR_PALETTE
        MULTI_COLOR_PALETTE = [_hex_to_ass(c) for c in custom_multi if c]

    display_mode = settings.get("captionDisplayMode", "phrase")
    highlight_color_mode = settings.get("highlightColorMode", "single")
    highlight_color = settings.get("captionHighlightColor", settings.get("highlightColor", "yellow"))
    auto_hook_enabled = settings.get("autoHook", False)
    auto_hook_duration = float(settings.get("autoHookDuration", 3))
    auto_hook_position = settings.get("autoHookPosition", "top-center")

    transcript = json.loads(
        (context["temp_dir"] / "transcript.json").read_text(encoding="utf-8")
    )
    clips = json.loads(
        (context["output_dir"] / "clips.json").read_text(encoding="utf-8")
    )["clips"]
    words = transcript.get("words", [])

    print("Starting caption generation...", flush=True)
    updated_clips = []
    total_clips = len(clips)
    for index, clip in enumerate(clips, start=1):
        print(f"Burning captions for clip {index}/{total_clips}...", flush=True)
        clip_start = float(clip["start"])
        clip_end = float(clip["end"])
        clip_words = [
            {
                **word,
                "start": float(word["start"]) - clip_start,
                "end": float(word["end"]) - clip_start,
            }
            for word in words
            if float(word["end"]) > clip_start and float(word["start"]) < clip_end
        ]
        if not clip_words:
            raise RuntimeError(f"No transcript words found for {clip['id']}")

        metadata_file = context["output_dir"] / "metadata" / f"{clip['id']}.json"
        clip_metadata = json.loads(metadata_file.read_text(encoding="utf-8")) if metadata_file.exists() else {}

        ass_path = captions_dir / f"{clip['id']}.ass"
        ass_text = _style_header(1080, 1920, clip_metadata=clip_metadata, settings=settings)

        # Hook rendering via PIL for pixel-perfect 8px border radius & 12px padding
        hook_enabled = resolve_hook_enabled(clip_metadata, settings)
        hook_text = resolve_hook_text(clip_metadata, settings, clip)
        hook_png_path = context["temp_dir"] / f"hook_{clip['id']}.png"
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
                canvas_w=1080,
                canvas_h=1920,
            )
            use_hook_png = hook_png_path.exists()
            print(f"[AutoHook] Rendered initial Hook PNG for {clip['id']}: text='{hook_text}'", flush=True)

        # Caption chunks for ASS subtitles
        chunks = _chunk_words(clip_words, display_mode)
        for chunk_index, chunk in enumerate(chunks):
            next_start = float(chunks[chunk_index + 1][0]["start"]) if chunk_index + 1 < len(chunks) else None
            ass_text += "".join(_caption_lines(
                chunk,
                chunk_index=chunk_index,
                highlight_color_mode=highlight_color_mode,
                highlight_color=highlight_color,
                next_start=next_start,
                settings=settings
            ))
        ass_path.write_text(ass_text, encoding="utf-8")

        source = context["temp_dir"] / "raw_clips" / f"{clip['id']}.mp4"
        captioned_path = captioned_dir / f"{clip['id']}.mp4"
        ass_filter_path = str(ass_path).replace("\\", "/").replace(":", r"\:")

        if use_hook_png:
            dur_mode = str(_get_hook_setting("DurationMode", clip_metadata, settings, "custom"))
            clip_dur = float(clip.get("duration", 5.0))
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
                f"[0:v][hook_overlay]overlay=0:0:enable='between(t,0,{hook_dur:.2f})',"
                f"ass='{ass_filter_path}'[vout]"
            )
            cmd = [
                "ffmpeg", "-y",
                "-i", str(source),
                "-loop", "1",
                "-i", str(hook_png_path),
                "-filter_complex", filter_complex,
                "-map", "[vout]", "-map", "0:a?",
                "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
                "-c:a", "copy", "-shortest", "-movflags", "+faststart",
                str(captioned_path),
            ]
            print(f"[AutoHook] Executing FFmpeg with -loop 1 PNG overlay:\n  {' '.join(cmd)}", flush=True)
            run_command(cmd)
        else:
            cmd = [
                "ffmpeg", "-y",
                "-i", str(source),
                "-vf", f"ass='{ass_filter_path}'",
                "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
                "-c:a", "copy", "-movflags", "+faststart",
                str(captioned_path),
            ]
            print(f"[AutoHook] Executing FFmpeg (no Hook PNG):\n  {' '.join(cmd)}", flush=True)
            run_command(cmd)

        # Strip editorial text fields from clips.json payload (metadata/{clipId}.json is canonical owner)
        clip_clean = {k: v for k, v in clip.items() if k not in ("title", "hook", "hookText", "userHookText", "autoHookText")}

        updated_clips.append({
            **clip_clean,
            "autoHook": use_hook_png,
            "layoutMode": clip.get("layoutMode", settings.get("layoutMode", "auto")),
            "resolvedLayout": clip.get("resolvedLayout", clip.get("crop", {}).get("resolvedLayout", "full-crop")),
            "captionPath": str(ass_path),
            "captionedPath": str(captioned_path),
            "captionDisplayMode": display_mode,
            "highlightColorMode": highlight_color_mode,
            "highlightColor": highlight_color,
        })

    (context["output_dir"] / "clips.json").write_text(
        json.dumps({"clips": updated_clips}, indent=2),
        encoding="utf-8",
    )
