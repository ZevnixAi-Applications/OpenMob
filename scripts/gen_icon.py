"""Generate the OpenMob app icon (1024x1024 master + Android adaptive foreground).

Design: dark charcoal rounded square field with a minimal geometric phone
outline and a green signal/cursor dot. Flat, no text, readable at 48px.

Run:  uv run --with pillow python scripts/gen_icon.py
"""

from pathlib import Path

from PIL import Image, ImageDraw

CHARCOAL = (0x16, 0x18, 0x1D, 255)
GREEN = (0x3D, 0xDC, 0x97, 255)
STROKE = (0xE8, 0xEA, 0xEE, 255)  # near-white for the phone outline

S = 1024  # master size
SS = 4  # supersampling factor
BIG = S * SS

OUT_DIR = Path(__file__).resolve().parent.parent / "app" / "assets" / "icon"


def rounded_rect(draw, box, radius, **kw):
    draw.rounded_rectangle(box, radius=radius, **kw)


def draw_mark(draw, cx, cy, scale):
    """Draw the phone outline + green dot, centered at (cx, cy).

    scale = height of the phone body in px.
    """
    ph = scale  # phone height
    pw = ph * 0.52  # phone width
    lw = max(int(ph * 0.075), 1)  # line width
    r = ph * 0.14  # corner radius

    x0, y0 = cx - pw / 2, cy - ph / 2
    x1, y1 = cx + pw / 2, cy + ph / 2
    rounded_rect(draw, (x0, y0, x1, y1), r, outline=STROKE, width=lw)

    # Speaker slot: short rounded line near the top, subtle.
    sw = pw * 0.30
    sy = y0 + ph * 0.115
    draw.line((cx - sw / 2, sy, cx + sw / 2, sy), fill=STROKE, width=max(lw // 2, 1))

    # Green signal/cursor dot: lower-right inside the screen, with a single
    # concentric arc suggesting a live signal.
    dot_r = ph * 0.10
    dx = cx
    dy = y1 - ph * 0.26
    draw.ellipse((dx - dot_r, dy - dot_r, dx + dot_r, dy + dot_r), fill=GREEN)

    arc_r = dot_r * 1.9
    aw = max(int(lw * 0.75), 1)
    draw.arc(
        (dx - arc_r, dy - arc_r, dx + arc_r, dy + arc_r),
        start=200,
        end=340,
        fill=GREEN,
        width=aw,
    )


def make_master():
    img = Image.new("RGBA", (BIG, BIG), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    # Rounded charcoal field (small margin so the shape reads as an icon tile).
    margin = int(BIG * 0.03)
    radius = int(BIG * 0.20)
    rounded_rect(d, (margin, margin, BIG - margin, BIG - margin), radius, fill=CHARCOAL)
    draw_mark(d, BIG / 2, BIG / 2, BIG * 0.56)
    return img.resize((S, S), Image.LANCZOS)


def make_adaptive_foreground():
    """Android adaptive foreground: transparent background, mark only, scaled
    into the safe zone (inner ~66% of the canvas)."""
    img = Image.new("RGBA", (BIG, BIG), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    draw_mark(d, BIG / 2, BIG / 2, BIG * 0.40)
    return img.resize((S, S), Image.LANCZOS)


def make_full_bleed():
    """Edge-to-edge opaque square for iOS (iOS masks its own corners and
    rejects alpha in app icons)."""
    img = Image.new("RGBA", (BIG, BIG), CHARCOAL)
    d = ImageDraw.Draw(img)
    draw_mark(d, BIG / 2, BIG / 2, BIG * 0.56)
    return img.resize((S, S), Image.LANCZOS).convert("RGB")


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    make_master().save(OUT_DIR / "icon.png")
    make_adaptive_foreground().save(OUT_DIR / "icon_foreground.png")
    make_full_bleed().save(OUT_DIR / "icon_full.png")
    print(f"Wrote icon.png, icon_foreground.png, icon_full.png in {OUT_DIR}")


if __name__ == "__main__":
    main()
