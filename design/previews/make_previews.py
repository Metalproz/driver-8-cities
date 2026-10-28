"""Driver 1 style city preview pictures for the Driver 2 cities (Design chat, 2026-10-14).

Driver 1 format (TPDATA.DAT entry + FECLUT.CLT + FRNT.B1 page half): 128 x 228 px (LA2's quad height; MIAMI/NY2 use 232), 4-bit, one 16-colour
CLUT (index 0 = transparent), drawn as the Take a Ride picture quad at (160,190)-(288,422).
Sources: Driver 2's own city-select photos (DRIVER2/DATA/CITY.RAW, 4 x 256x219, red duotone, unpacked with
DriverImageTool -bg2tim) and Driver 2's Chicago sky panorama (SKY0.RAW, polish_sky._panorama).

    python make_previews.py SRC_DIR OUT_DIR
SRC_DIR holds CITY.RAW_0..3.TIM.png and d2_sky_day.png (see README.md). Writes per city:
    NAME.png (1x), NAME_3x.png, NAME.4bit (128*H/2 B raw, low nibble first), NAME.clut (32 B, 15-bit BGR)
and mockup_<city>.png when a menu screenshot menu_page2.png is in SRC_DIR.
"""
from __future__ import annotations
import struct, sys
from pathlib import Path
import numpy as np
from PIL import Image, ImageDraw, ImageOps, ImageEnhance, ImageFilter

W, H = 128, 228          # LA2's quad shows 228 rows (Infrastructure 14.10.): the picture is built 228 tall
# 16-colour CLUT in the LA2 / SF2 spirit: transparent, 11 greys, 2 golds, 1 brown, 1 gold highlight
PALETTE = [(0, 0, 0), (248, 248, 248), (224, 224, 224), (200, 200, 200), (176, 176, 176), (152, 152, 152),
           (128, 128, 128), (104, 104, 104), (80, 80, 80), (56, 56, 56), (32, 32, 32), (16, 16, 16),
           (216, 160, 8), (208, 152, 0), (144, 120, 72), (240, 208, 96)]
GREYS = list(range(1, 12))
GOLD, GOLD_DK, BROWN, GOLD_HI = 12, 13, 14, 15
FRAME_R, BORDER = 14, 4          # corner radius, gold border width (outer 1 px darker)
TOP = 14                         # the frame starts this far down: room for a landmark poking out (NY's Liberty)


def to_grey(im: Image.Image, contrast=1.35, dithered=False) -> Image.Image:
    """D2's red duotone / colour photo -> punchy greyscale like Driver 1's posterised previews.
    dithered: the source is one of D2's 2-tone dithered city photos (CITY.RAW): recover the tones with a
    low-pass first, otherwise the dither pattern turns into noise after posterising."""
    g = im.convert("L")
    if dithered:
        g = g.filter(ImageFilter.GaussianBlur(1.6)).filter(ImageFilter.MedianFilter(3))
    g = ImageOps.autocontrast(g, cutoff=1)
    g = ImageEnhance.Contrast(g).enhance(contrast)
    return g.filter(ImageFilter.UnsharpMask(radius=1, percent=60))


def grey_to_index(g: Image.Image) -> np.ndarray:
    """nearest of the 11 greys (no dither: Driver 1's pictures are flat-toned)."""
    a = np.asarray(g, dtype=np.float32)
    levels = np.array([PALETTE[i][0] for i in GREYS], dtype=np.float32)
    idx = np.abs(a[..., None] - levels[None, None, :]).argmin(-1)
    return np.array(GREYS, dtype=np.uint8)[idx]


def frame_masks():
    """inside mask (interior of the rounded rectangle) and the gold border (two tones)."""
    inside = Image.new("L", (W, H), 0)
    ImageDraw.Draw(inside).rounded_rectangle((BORDER, TOP + BORDER, W - 1 - BORDER, H - 1 - BORDER), FRAME_R - BORDER, fill=255)
    outer = Image.new("L", (W, H), 0)
    ImageDraw.Draw(outer).rounded_rectangle((0, TOP, W - 1, H - 1), FRAME_R, fill=255)
    rim = Image.new("L", (W, H), 0)
    ImageDraw.Draw(rim).rounded_rectangle((0, TOP, W - 1, H - 1), FRAME_R, outline=255, width=1)
    return np.asarray(inside) > 0, np.asarray(outer) > 0, np.asarray(rim) > 0


def compose(interior: np.ndarray, breakout: np.ndarray | None = None) -> np.ndarray:
    """interior: HxW index image (any size >= inner area, cropped centrally); breakout: HxW bool mask of
    pixels allowed to show outside the frame (a landmark poking through the border, like Liberty / the palm)."""
    inside, outer, rim = frame_masks()
    out = np.zeros((H, W), dtype=np.uint8)
    out[outer] = GOLD
    out[rim] = GOLD_DK
    inner_line = inside & ~np.roll(inside, 1, 0) | inside & ~np.roll(inside, -1, 0) | inside & ~np.roll(inside, 1, 1) | inside & ~np.roll(inside, -1, 1)
    out[inside] = interior[inside]
    out[inner_line] = 11
    if breakout is not None:
        show = breakout & ~inside
        out[show] = interior[show]
    return out


def fit(im: Image.Image, w: int, h: int) -> Image.Image:
    """scale to cover w x h, crop centre."""
    s = max(w / im.width, h / im.height)
    im = im.resize((max(w, round(im.width * s)), max(h, round(im.height * s))), Image.Resampling.LANCZOS)
    x, y = (im.width - w) // 2, (im.height - h) // 2
    return im.crop((x, y, x + w, y + h))


def chicago(src: Path) -> np.ndarray:
    """Top: Driver 2's Chicago skyline (sky panorama), the Sears Tower breaking the frame top like NY's
    Liberty. Bottom: Driver 2's own Chicago city-select photo (street under the L)."""
    pano = Image.open(src / "d2_sky_day.png").convert("RGB")
    top_h = 96                                           # skyline block inside the frame
    iw = W - 2 * BORDER
    # one skyline strip covering the breakout rows (0..TOP+BORDER) and the block below: 180 x (112 + 18)
    strip_h = top_h + TOP + BORDER
    sky = to_grey(pano.crop((150, 72, 330, 168)), 1.5).resize((iw, strip_h), Image.Resampling.LANCZOS)
    # lower half: a Chicago street from the converted city itself (downtown, probe screenshot 512x240,
    # HUD and minimap cropped away); D2's own city-select photo (CITY.RAW_0) is a 2-tone dither and
    # turns to mush at this size: kept as the fallback 'plain' variant
    shot = src / "chicago_street.png"
    if shot.exists():
        street = Image.open(shot).convert("RGB").crop((120, 8, 400, 232))
        street_g = to_grey(street, 1.45)
    else:
        street = Image.open(src / "CITY.RAW_0.TIM.png").convert("RGB")
        street_g = to_grey(street.crop((16, 0, 240, 219)), 1.3, dithered=True)
    street_g = fit(street_g, iw, H - TOP - 2 * BORDER - top_h)
    canvas = Image.new("L", (W, H), 255)
    canvas.paste(sky, (BORDER, 0))
    canvas.paste(street_g, (BORDER, TOP + BORDER + top_h))
    interior = grey_to_index(canvas)
    # breakout: only the tower silhouettes (dark pixels) may show above the frame's top edge
    breakout = np.asarray(canvas) < 100
    breakout[TOP + BORDER:, :] = False
    return compose(interior, breakout)


def plain(src: Path, k: int, contrast=1.4) -> np.ndarray:
    """Havana / Las Vegas / Rio draft: Driver 2's city-select photo filling the frame."""
    im = Image.open(src / ("CITY.RAW_%d.TIM.png" % k)).convert("RGB")
    g = fit(to_grey(im, contrast, dithered=True), W - 2 * BORDER, H - TOP - 2 * BORDER)
    canvas = Image.new("L", (W, H), 255)
    canvas.paste(g, (BORDER, TOP + BORDER))
    return compose(grey_to_index(canvas))


def save(idx: np.ndarray, out: Path, name: str, menu: Path | None):
    pal = np.array(PALETTE, dtype=np.uint8)
    rgb = pal[idx]
    alpha = (idx != 0).astype(np.uint8) * 255
    im = Image.fromarray(np.dstack([rgb, alpha]), "RGBA")
    im.save(out / (name + ".png"))
    im.resize((W * 3, H * 3), Image.Resampling.NEAREST).save(out / (name + "_3x.png"))
    raw = (idx[:, 0::2] | (idx[:, 1::2] << 4)).astype(np.uint8).tobytes()   # low nibble = left pixel
    (out / (name + ".4bit")).write_bytes(raw)
    clut = b"".join(struct.pack("<H", (r >> 3) | ((g >> 3) << 5) | ((b >> 3) << 10)) for r, g, b in PALETTE)
    (out / (name + ".clut")).write_bytes(clut)
    if menu and menu.exists():
        m = Image.open(menu).convert("RGBA")
        m.paste(im, (160, 190), im)
        m.save(out / ("mockup_" + name.lower() + ".png"))


def main():
    src, out = Path(sys.argv[1]), Path(sys.argv[2])
    out.mkdir(parents=True, exist_ok=True)
    menu = src / "menu_page2.png"
    save(chicago(src), out, "CHICAGO", menu)
    for k, name in ((1, "HAVANA"), (2, "VEGAS"), (3, "RIO")):
        save(plain(src, k), out, name, menu)
    print("written to", out)


if __name__ == "__main__":
    main()
