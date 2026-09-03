import os
from PIL import Image, ImageDraw, ImageFont

def render_hook_image(
    text: str = "This Changed Everything...",
    font_name: str = "arial.ttf",
    font_size: int = 64,
    text_color: str = "#ffffff",
    bg_color: str = "#16a34a",
    padding: int = 24,
    radius: int = 20,
    canvas_w: int = 1080,
    canvas_h: int = 1920,
    position: str = "top-center"
) -> Image.Image:
    # Try loading requested font or fallback to default
    try:
        # Common Windows font paths
        font_path = f"C:\\Windows\\Fonts\\{font_name}"
        if not os.path.exists(font_path):
            font_path = "C:\\Windows\\Fonts\\arialbd.ttf"
        font = ImageFont.truetype(font_path, font_size)
    except Exception:
        font = ImageFont.load_default()

    # Wrap text into lines if long
    words = text.strip().split()
    lines = []
    curr = []
    for w in words:
        curr.append(w)
        test_str = " ".join(curr)
        bbox = font.getbbox(test_str)
        w_px = bbox[2] - bbox[0]
        if w_px > (canvas_w - 200) and len(curr) > 1:
            curr.pop()
            lines.append(" ".join(curr))
            curr = [w]
    if curr:
        lines.append(" ".join(curr))

    # Calculate multiline text dimensions
    line_heights = []
    line_widths = []
    for line in lines:
        bbox = font.getbbox(line)
        line_widths.append(bbox[2] - bbox[0])
        line_heights.append(bbox[3] - bbox[1])

    max_text_w = max(line_widths) if line_widths else 100
    total_text_h = sum(line_heights) + (len(lines) - 1) * 12

    # Card dimensions with fixed padding
    card_w = max_text_w + (padding * 2)
    card_h = total_text_h + (padding * 2)

    # Transparent canvas
    img = Image.new("RGBA", (canvas_w, canvas_h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Position card on 1080x1920 canvas
    card_x = (canvas_w - card_w) // 2
    if position == "top":
        card_y = 150
    elif position == "middle":
        card_y = (canvas_h - card_h) // 2
    else:  # top-center default
        card_y = 220

    # Draw rounded rectangle background card
    card_box = [card_x, card_y, card_x + card_w, card_y + card_h]
    draw.rounded_rectangle(card_box, radius=radius, fill=bg_color)

    # Draw text centered line by line
    curr_y = card_y + padding
    for i, line in enumerate(lines):
        line_w = line_widths[i]
        line_x = card_x + (card_w - line_w) // 2
        draw.text((line_x, curr_y), line, font=font, fill=text_color)
        curr_y += line_heights[i] + 12

    return img

if __name__ == "__main__":
    hook_img = render_hook_image()
    out_path = "test_hook.png"
    hook_img.save(out_path)
    print(f"Hook image saved successfully to {out_path}, size: {hook_img.size}")
