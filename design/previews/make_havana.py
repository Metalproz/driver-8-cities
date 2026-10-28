"""Havana menu picture v2 (Design, M3): same format as CHICAGO (128x228 4-bit + 16-colour CLUT), reuses make_previews.
Top: sunlit colonial Havana block from the converted level (balconies, arcades, 50s cars; game capture), a hand-drawn palm
silhouette breaks the frame (like Miami's palm); bottom: Havana street with the car (runner havana_drive capture, shadows lifted).
Warm sepia ramp like Miami's picture.
    python make_havana.py TOP_PNG STREET_PNG OUT_DIR
"""
import sys, math
from pathlib import Path
import numpy as np
from PIL import Image, ImageDraw
sys.path.insert(0, str(Path(__file__).parent))
import make_previews as mp

SEPIA = [(255, 244, 222), (240, 224, 192), (224, 204, 168), (204, 182, 144), (184, 160, 122), (160, 136, 100),
         (136, 112, 80), (108, 86, 60), (80, 62, 42), (52, 38, 26), (26, 18, 12)]
for i, c in enumerate(SEPIA):
    mp.PALETTE[1 + i] = c

TOP_CROP = (700, 0, 905, 128)         # in the top capture (512 x 240 shots pasted 2 wide: p0 lives at x 512..1023)
STREET_CROP = (178, 75, 338, 228)
GAMMA = 0.55                          # lifts the street's shadows


def palm(w, h, cx, cy, S=6):
    """clean palm silhouette (trunk + 8 fronds) as a bool mask w x h, drawn supersampled."""
    im = Image.new("L", (w * S, h * S), 0)
    d = ImageDraw.Draw(im)
    top = (cx * S, cy * S)
    trunk = [(top[0] + -5 * S * t * t, top[1] + 56 * S * t) for t in np.linspace(0, 1, 30)]
    for k in range(len(trunk) - 1):
        d.line([trunk[k], trunk[k + 1]], fill=255, width=int((2.6 - 1.0 * k / 30) * S))
    for ang, ln in ((-172, 24), (-140, 24), (-108, 17), (-72, 17), (-40, 24), (-8, 24), (170, 16), (12, 16)):
        a = math.radians(ang)
        pts = []
        for t in np.linspace(0, 1, 16):
            x = top[0] + math.cos(a) * ln * S * t
            y = top[1] + math.sin(a) * ln * S * t + (15 * S) * t * t * (0.5 + 0.5 * abs(math.cos(a)))
            pts.append((x, y))
        for k in range(15):
            d.line([pts[k], pts[k + 1]], fill=255, width=max(1, int((4.2 * (1 - k / 15) + 0.8) * S)))
    d.ellipse((top[0] - 2.2 * S, top[1] - 2.2 * S, top[0] + 2.2 * S, top[1] + 2.2 * S), fill=255)
    return np.asarray(im.resize((w, h), Image.Resampling.LANCZOS)) > 128


def prep(path, crop, w, h, gamma=1.0, contrast=1.45):
    return prep_img(Image.open(path).convert("RGB"), crop, w, h, gamma, contrast)


def prep_img(im, crop, w, h, gamma=1.0, contrast=1.45):
    im = im.crop(crop)
    if gamma != 1.0:
        a = (np.asarray(im, dtype=np.float32) / 255.0) ** gamma
        im = Image.fromarray((a * 255).astype(np.uint8))
    return mp.fit(mp.to_grey(im, contrast), w, h)


def havana(top_png, street_png):
    W, H, B, TOPY = mp.W, mp.H, mp.BORDER, mp.TOP
    iw, top_h = W - 2 * B, 60
    strip_h = top_h + TOPY + B
    canvas = Image.new("L", (W, H), 255)
    canvas.paste(prep(top_png, TOP_CROP, iw, top_h, 0.85, 1.35), (B, TOPY + B))
    canvas.paste(prep(street_png, STREET_CROP, iw, H - TOPY - 2 * B - top_h, GAMMA, 1.2), (B, TOPY + B + top_h))
    idx = mp.grey_to_index(canvas)
    pm = palm(W, H, 100, 7)
    idx[pm] = 11                       # darkest sepia: palm over the facade and above the frame
    brk = pm.copy()
    brk[TOPY + B + 2:, :] = False
    out = mp.compose(idx, brk)
    out[(pm) & (np.arange(H)[:, None] < TOPY + B) & (out == 0)] = 11
    return out


if __name__ == "__main__":
    out = Path(sys.argv[3]); out.mkdir(parents=True, exist_ok=True)
    mp.save(havana(Path(sys.argv[1]), Path(sys.argv[2])), out, "HAVANA", None)
    print("ok")
