"""
Branded table QR card as a print-ready PNG (A6 at 300 dpi): logo, café name,
headline, the table QR with the logo in the middle, the table number and the
three steps. Drawn at 2x and scaled down for smooth edges.
"""

import io
from pathlib import Path

import qrcode
from django.conf import settings
from PIL import Image, ImageDraw, ImageFilter, ImageFont

W, H = 1240, 1748  # A6 portrait at 300 dpi
S = 2  # supersampling

DARK = (42, 42, 44)
INK = (30, 30, 30)
MUTED = (94, 94, 98)
YELLOW = (245, 200, 66)
CREAM = (243, 243, 241)
GREY = (169, 169, 174)

FONT_DIR = Path(settings.BASE_DIR) / "static" / "fonts"


def _font(weight, size):
    try:
        return ImageFont.truetype(str(FONT_DIR / f"Outfit-{weight}.ttf"), size * S)
    except OSError:
        return ImageFont.load_default(size * S)


def _logo(business, size):
    """Circular logo, or the café's initial on a dark circle."""
    img = None
    logo = getattr(business, "logo", None)
    if logo:
        try:
            with logo.open("rb") as fh:
                img = Image.open(fh).convert("RGBA")
                img.load()
        except Exception:
            img = None
    canvas = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).ellipse((0, 0, size - 1, size - 1), fill=255)
    if img is not None:
        bg = Image.new("RGBA", (size, size), (255, 255, 255, 255))
        img.thumbnail((int(size * 0.86), int(size * 0.86)), Image.LANCZOS)
        bg.alpha_composite(img, ((size - img.width) // 2, (size - img.height) // 2))
        canvas.paste(bg, (0, 0), mask)
    else:
        d = ImageDraw.Draw(canvas)
        d.ellipse((0, 0, size - 1, size - 1), fill=DARK)
        letter = (getattr(business, "business_name", "") or "C")[:1].upper()
        f = ImageFont.truetype(str(FONT_DIR / "Outfit-Regular.ttf"), int(size * 0.5)) if (FONT_DIR / "Outfit-Regular.ttf").exists() else ImageFont.load_default()
        d.text((size / 2, size / 2), letter, font=f, fill=YELLOW, anchor="mm")
    return canvas


def _center_text(draw, y, text, font, fill, tracking=0):
    if tracking:
        widths = [draw.textlength(ch, font=font) for ch in text]
        total = sum(widths) + tracking * (len(text) - 1)
        x = (W * S - total) / 2
        for ch, w in zip(text, widths):
            draw.text((x, y), ch, font=font, fill=fill, anchor="ls")
            x += w + tracking
        return
    draw.text((W * S / 2, y), text, font=font, fill=fill, anchor="ms")


def _fit(draw, text, weight, size, max_w):
    """Shrink the font until the text fits the width."""
    while size > 20:
        f = _font(weight, size)
        if draw.textlength(text, font=f) <= max_w:
            return f
        size -= 4
    return _font(weight, size)


def _qr(url, size):
    """The QR on a white tile: rounded dots, square corner eyes, clear centre for the logo."""
    qr = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_H, border=0)
    qr.add_data(url)
    qr.make(fit=True)
    m = qr.get_matrix()
    n = len(m)
    quiet = 2
    cell = size / (n + quiet * 2)
    img = Image.new("RGBA", (size, size), (255, 255, 255, 0))
    d = ImageDraw.Draw(img)
    eyes = [(0, 0), (n - 7, 0), (0, n - 7)]
    hole = int(n * 0.22) | 1
    h0 = (n - hole) // 2

    def at(v):
        return (v + quiet) * cell

    for r in range(n):
        for c in range(n):
            if not m[r][c]:
                continue
            if any(er <= r < er + 7 and ec <= c < ec + 7 for er, ec in eyes):
                continue
            if h0 - 1 <= r <= h0 + hole and h0 - 1 <= c <= h0 + hole:
                continue
            pad = cell * 0.06
            d.rounded_rectangle((at(c) + pad, at(r) + pad, at(c + 1) - pad, at(r + 1) - pad), radius=cell * 0.32, fill=DARK)
    for er, ec in eyes:
        d.rectangle((at(ec), at(er), at(ec + 7) - 1, at(er + 7) - 1), fill=DARK)
        d.rectangle((at(ec + 1), at(er + 1), at(ec + 6) - 1, at(er + 6) - 1), fill="white")
        d.rectangle((at(ec + 2), at(er + 2), at(ec + 5) - 1, at(er + 5) - 1), fill=DARK)
    return img, (hole + 2) * cell


def render_table_card(table, url, business, headline="Scan to see the menu", subline="& order right from your table"):
    w, h = W * S, H * S
    card = Image.new("RGBA", (w, h), CREAM + (255,))

    # Soft yellow glow, as on the app's screens (blend solid colours through blurred masks)
    def wash(color, box, blur, strength=255):
        mask = Image.new("L", (w, h), 0)
        ImageDraw.Draw(mask).ellipse(box, fill=strength)
        mask = mask.filter(ImageFilter.GaussianBlur(blur))
        card.paste(Image.new("RGBA", (w, h), color + (255,)), (0, 0), mask)

    wash((248, 231, 166), (int(w * 0.2), int(h * 0.55), int(w * 1.6), int(h * 1.45)), 170 * S)
    wash((255, 255, 255), (int(-w * 0.4), int(-h * 0.3), int(w * 0.65), int(h * 0.35)), 150 * S, 190)

    d = ImageDraw.Draw(card)
    name = getattr(business, "business_name", "") or ""

    # Brand row: logo + name
    logo_size = 104 * S
    name_font = _fit(d, name, "Medium", 50, (W - 300) * S)
    name_w = d.textlength(name, font=name_font)
    gap = 26 * S
    x0 = (w - (logo_size + gap + name_w)) / 2
    y_brand = 120 * S
    card.alpha_composite(_logo(business, logo_size), (int(x0), int(y_brand)))
    d.text((x0 + logo_size + gap, y_brand + logo_size / 2), name, font=name_font, fill=INK, anchor="lm")

    # Headline
    _center_text(d, 390 * S, headline, _fit(d, headline, "Light", 96, (W - 160) * S), INK)
    _center_text(d, 460 * S, subline, _fit(d, subline, "Regular", 42, (W - 200) * S), MUTED)

    # QR tile
    tile = 720 * S
    tx, ty = (w - tile) // 2, 540 * S
    shadow = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    ImageDraw.Draw(shadow).rounded_rectangle((tx, ty + 18 * S, tx + tile, ty + tile + 18 * S), radius=64 * S, fill=(30, 30, 40, 40))
    card.alpha_composite(shadow.filter(ImageFilter.GaussianBlur(26 * S)))
    d = ImageDraw.Draw(card)
    d.rounded_rectangle((tx, ty, tx + tile, ty + tile), radius=64 * S, fill="white")
    pad = 34 * S
    qr_img, hole_px = _qr(url, tile - pad * 2)
    card.alpha_composite(qr_img, (tx + pad, ty + pad))
    badge = int(hole_px * 0.9)
    bx, by = tx + tile // 2 - badge // 2, ty + tile // 2 - badge // 2
    d.ellipse((bx, by, bx + badge, by + badge), fill="white")
    inner = int(badge * 0.86)
    card.alpha_composite(_logo(business, inner), (bx + (badge - inner) // 2, by + (badge - inner) // 2))

    # Table pill
    label_f, num_f = _font("Regular", 34), _font("Regular", 92)
    number = str(table.number)
    label_w = sum(d.textlength(ch, font=label_f) for ch in "TABLE") + 8 * S * 4
    num_w = d.textlength(number, font=num_f)
    pill_h, pill_pad, inner_gap = 150 * S, 64 * S, 30 * S
    pill_w = pill_pad * 2 + label_w + inner_gap + num_w
    px, py = (w - pill_w) / 2, 1330 * S
    d.rounded_rectangle((px, py, px + pill_w, py + pill_h), radius=pill_h / 2, fill=DARK)
    x = px + pill_pad
    for ch in "TABLE":
        d.text((x, py + pill_h / 2), ch, font=label_f, fill=GREY, anchor="lm")
        x += d.textlength(ch, font=label_f) + 8 * S
    d.text((px + pill_pad + label_w + inner_gap, py + pill_h / 2 + 4 * S), number, font=num_f, fill=YELLOW, anchor="lm")

    # Three steps
    steps = ["Scan the code", "Pick your dishes", "Pay from your phone"]
    step_f, dot_f = _font("Regular", 30), _font("Medium", 32)
    col = w / 3
    sy = 1580 * S
    r = 34 * S
    for i, label in enumerate(steps):
        cx = col * i + col / 2
        d.ellipse((cx - r, sy - r, cx + r, sy + r), fill="white")
        d.text((cx, sy + 2 * S), str(i + 1), font=dot_f, fill=INK, anchor="mm")
        d.text((cx, sy + r + 52 * S), label, font=step_f, fill=MUTED, anchor="ms")

    out = card.resize((W, H), Image.LANCZOS).convert("RGB")
    buf = io.BytesIO()
    out.save(buf, format="PNG", dpi=(300, 300), optimize=True)
    return buf.getvalue()
