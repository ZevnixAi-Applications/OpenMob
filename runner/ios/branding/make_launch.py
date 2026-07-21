"""Generate the OpenMob Runner launch-screen image (transparent, @3x).

The #16181D background comes from the LaunchBackground colorset; this image
is composited centered on it by iOS (UILaunchScreen.UIImageName).
"""
import sys
from PIL import Image, ImageDraw, ImageFont

W, H = 960, 840  # 320x280 pt at @3x
GREEN = (0x3D, 0xDC, 0x97, 255)
WHITE = (0xF5, 0xF7, 0xFA, 255)
GREY = (0x9A, 0xA3, 0xAF, 255)
RING = (0x2A, 0x2E, 0x36, 255)

img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
d = ImageDraw.Draw(img)

def font(size, bold=False):
    return ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", size,
                              index=1 if bold else 0)

def center_text(y, text, f, fill):
    box = d.textbbox((0, 0), text, font=f)
    d.text(((W - (box[2] - box[0])) / 2 - box[0], y), text, font=f, fill=fill)

# Green dot with thin ring, upper center (matches the app icon mark)
cx, cy, r = W // 2, 230, 78
d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=GREEN)
ring_r = r + 42
d.ellipse((cx - ring_r, cy - ring_r, cx + ring_r, cy + ring_r),
          outline=RING, width=9)

center_text(455, "OpenMob Runner", font(96, bold=True), WHITE)
center_text(640, "a product of Zevnix AI Private Ltd", font(44), GREY)

img.save(sys.argv[1])
print("wrote", sys.argv[1], img.size)
