"""polish_moon.py - Chicago night: Driver 2's moon in Driver 1's SKYSUN slot (Polish, 14.10.; Design SKY_SPRITES.md).

Switch CHI_NIGHT_MOON=1, night conversion only. Driver 1 draws the by-name sprite SKYSUN (24x24, 4-bit) as its sun and
at night as a dimmed "moon" disc; Chicago night drew the day sun. The night LEV gets Driver 2's SKYMOON pixels
(Design's design/out/SKYMOON_24.png, D2's 32x32 moon resampled to the 24x24 slot) in that slot, in Driver 1's sprite
style: background index = 0x0000 (as LA's SKYSUN: index 15 = 0), moon colours with the semi-transparency bit (0x8000).
"""
from __future__ import annotations

import os
import struct

MOON_PNG = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "design", "out", "SKYMOON_24.png")
BG_LUMA = 40
# C55 (Design 16.10.): the palette read as a dim grey; colours x GAIN (clamped): peak ~255, body ~(215,225,235)
GAIN = float(os.environ.get("CHI_POLISH_MOON_GAIN", "1.9"))


def enabled():
    return os.environ.get("CHI_NIGHT_MOON", "") == "1"


def moon_sprite(w: int, h: int):
    """(rows of 4-bit indices, 32-byte CLUT) for a w x h slot."""
    from PIL import Image
    im = Image.open(MOON_PNG).convert("RGB")
    if im.size != (w, h):
        im = im.resize((w, h), Image.LANCZOS)
    px = list(im.getdata())
    luma = [0.299 * r + 0.587 * g + 0.114 * b for r, g, b in px]
    fg = Image.new("RGB", (len(px), 1))
    fg.putdata([p for p, l in zip(px, luma) if l >= BG_LUMA] or [(0, 0, 0)])
    q = fg.quantize(colors=15)
    pal = q.getpalette()[:45]
    cols = [(pal[3 * i], pal[3 * i + 1], pal[3 * i + 2]) for i in range(15)]
    out_cols = [tuple(min(255, int(round(v * GAIN))) for v in c) for c in cols]

    def nearest(c):
        return min(range(15), key=lambda i: sum((a - b) ** 2 for a, b in zip(cols[i], c)))
    idx = [15 if l < BG_LUMA else nearest(c) for c, l in zip(px, luma)]
    rows = [bytes(idx[y * w:(y + 1) * w]) for y in range(h)]
    clut = b"".join(struct.pack("<H", 0x8000 | (b >> 3) << 10 | (g >> 3) << 5 | (r >> 3)) for r, g, b in out_cols) + struct.pack("<H", 0)
    return rows, clut


def apply(items) -> int:
    """Replace the pixels of every SKYSUN item (the name that wins the by-name lookup)."""
    n = 0
    for it in items:
        if it.name == b"SKYSUN":
            it.rows, it.clut = moon_sprite(it.w, it.h)
            n += 1
    return n
