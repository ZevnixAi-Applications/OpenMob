"""Generate the OpenMob Runner app icon (1024x1024)."""
from PIL import Image, ImageDraw, ImageFont

S = 1024
BG = (0x16, 0x18, 0x1D)          # #16181D
GREEN = (0x3D, 0xDC, 0x97)       # #3DDC97
WHITE = (0xF5, 0xF7, 0xFA)
GREY = (0x9A, 0xA3, 0xAF)

img = Image.new("RGB", (S, S), BG)
d = ImageDraw.Draw(img)

def font(size, bold=False):
    # Helvetica.ttc index 1 is Bold on macOS
    return ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", size, index=1 if bold else 0)

f_main = font(150, bold=True)
f_sub = font(84)

# Geometric mark: green dot with a thin ring, upper center
cx, cy, r = S // 2, 330, 84
d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=GREEN)
ring_r = r + 46
d.ellipse((cx - ring_r, cy - ring_r, cx + ring_r, cy + ring_r),
          outline=(0x2A, 0x2E, 0x36), width=10)

def center_text(y, text, f, fill):
    box = d.textbbox((0, 0), text, font=f)
    w = box[2] - box[0]
    d.text(((S - w) / 2 - box[0], y), text, font=f, fill=fill)

center_text(505, "OpenMob", f_main, WHITE)
center_text(690, "Runner", f_sub, GREY)

img.save(OUT := __import__("sys").argv[1])
print("wrote", OUT, img.size)
