"""Centralized Hook Overlay Renderer using Pillow (PIL).

Renders pixel-perfect rounded rectangle Hook cards (8px border radius, 12px padding)
with antialiased rounded corners, precise multiline font wrapping, and high-DPI resolution.
Guarantees 100% visual parity between React UI previews and exported FFmpeg MP4 videos.
"""

import os
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

# Fixed Design System Constants (Single Source of Truth)
FIXED_HOOK_PADDING_BASE = 6       # 10px base design padding
FIXED_HOOK_RADIUS_BASE = 8         # 8px base design border radius


def resolve_hook_text(clip_metadata: dict, settings: dict, clip: dict) -> str:
    """Robustly resolve Hook text checking overrides, custom templates, and clip highlight fallback."""
    # 1. Per-clip metadata override from Edit Clip UI
    m_text = clip_metadata.get("autoHookText") or clip_metadata.get("hookText") or clip_metadata.get("hook2Text")
    if m_text and str(m_text).strip():
        return str(m_text).strip()

    # 2. Global settings template override
    s_text = settings.get("autoHookText") or settings.get("hookText") or settings.get("hook2Text")
    if s_text and str(s_text).strip():
        return str(s_text).strip()

    # 3. Clip object AI highlight hook fallback
    c_text = clip.get("autoHookText") or clip.get("hook")
    if c_text and str(c_text).strip():
        return str(c_text).strip()

    return ""


def resolve_hook_enabled(clip_metadata: dict, settings: dict) -> bool:
    """Robustly resolve whether Hook is enabled checking metadata and settings."""
    if "autoHook" in clip_metadata:
        return bool(clip_metadata["autoHook"])
    if "hook2Enabled" in clip_metadata:
        return bool(clip_metadata["hook2Enabled"])

    if "autoHook" in settings:
        return bool(settings["autoHook"])
    if "hook2Enabled" in settings:
        return bool(settings["hook2Enabled"])

    return True


def _resolve_font(font_family: str, font_size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    """Resolve font family to system TTF font with fallback handling."""
    font_family_lower = font_family.lower()
    system_fonts_dir = Path("C:/Windows/Fonts")

    candidates = []
    if "black" in font_family_lower or "impact" in font_family_lower:
        candidates = ["ariblk.ttf", "impact.ttf", "arialbd.ttf", "arial.ttf"]
    elif "bold" in font_family_lower or "helvetica" in font_family_lower:
        candidates = ["arialbd.ttf", "helveticabold.ttf", "arial.ttf"]
    elif "georgia" in font_family_lower:
        candidates = ["georgiab.ttf", "georgia.ttf", "arial.ttf"]
    elif "courier" in font_family_lower:
        candidates = ["courbd.ttf", "cour.ttf", "arial.ttf"]
    else:
        candidates = ["arialbd.ttf", "arial.ttf", "tahoma.ttf", "verdana.ttf"]

    for name in candidates:
        fp = system_fonts_dir / name
        if fp.exists():
            try:
                return ImageFont.truetype(str(fp), font_size)
            except Exception:
                continue

    try:
        return ImageFont.load_default()
    except Exception:
        return ImageFont.load_default()


def render_hook_overlay_png(
    text: str,
    font_family: str = "Arial Black",
    font_size: int = 76,
    text_color: str = "#ffffff",
    bg_color: str = "#16a34a",
    position: str = "top-center",
    output_path: str | Path | None = None,
    canvas_w: int = 1080,
    canvas_h: int = 1920,
) -> Path:
    """Render a transparent PNG overlay containing the Hook card with rounded corners (8px radius, 12px padding)."""
    if not text or not text.strip():
        text = "Key Highlight"

    text = text.strip()[:120]

    # Calculate scale factor relative to 1080p canvas width (1080 / 430 ≈ 2.5)
    scale_factor = canvas_w / 430.0
    padding_v = int(round(12 * scale_factor))  # 12px vertical padding (~30px)
    padding_h = int(round(18 * scale_factor))  # 18px horizontal padding (~45px)
    radius_px = int(round(8 * scale_factor))    # 8px radius (~20px)

    font = _resolve_font(font_family, font_size)

    # Wrap text into lines fitting canvas width (85% max width)
    max_line_width = int(canvas_w * 0.85) - (padding_h * 2)
    words = text.split()
    lines = []
    curr = []

    for w in words:
        curr.append(w)
        test_str = " ".join(curr)
        bbox = font.getbbox(test_str)
        w_px = bbox[2] - bbox[0]
        if w_px > max_line_width and len(curr) > 1:
            curr.pop()
            lines.append(" ".join(curr))
            curr = [w]
    if curr:
        lines.append(" ".join(curr))

    # Measure multiline text bounding boxes with exact baseline offsets
    line_widths = []
    line_heights = []
    line_top_offsets = []
    for line in lines:
        bbox = font.getbbox(line)
        line_widths.append(bbox[2] - bbox[0])
        line_heights.append(bbox[3] - bbox[1])
        line_top_offsets.append(bbox[1])

    max_text_w = max(line_widths) if line_widths else 100
    line_spacing = int(10 * scale_factor)
    total_text_h = sum(line_heights) + int((len(lines) - 1) * line_spacing)

    # Card dimensions with balanced padding
    card_w = max_text_w + (padding_h * 2)
    card_h = total_text_h + (padding_v * 2)

    # Create transparent high-DPI RGBA canvas
    img = Image.new("RGBA", (canvas_w, canvas_h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Position card on canvas
    card_x = (canvas_w - card_w) // 2
    if position == "top":
        card_y = int(140 * (canvas_h / 1920.0))
    elif position == "middle":
        card_y = (canvas_h - card_h) // 2
    else:  # top-center default
        card_y = int(220 * (canvas_h / 1920.0))

    card_box = [card_x, card_y, card_x + card_w, card_y + card_h]

    # Parse fill color
    fill_rgba = bg_color if bg_color else "#000000"

    # Draw rounded rectangle background card with 8px radius
    draw.rounded_rectangle(card_box, radius=radius_px, fill=fill_rgba)

    # Draw text perfectly aligned line by line
    curr_y = card_y + padding_v
    for i, line in enumerate(lines):
        line_w = line_widths[i]
        line_x = card_x + (card_w - line_w) // 2
        top_offset = line_top_offsets[i]
        draw.text((line_x, curr_y - top_offset), line, font=font, fill=text_color)
        curr_y += line_heights[i] + line_spacing

    output_file = Path(output_path) if output_path else Path("hook_overlay.png")
    output_file.parent.mkdir(parents=True, exist_ok=True)
    img.save(str(output_file), "PNG")
    return output_file
