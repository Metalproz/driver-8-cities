"""d2overlay.py - Driver 2's overhead map (LUMP_OVERLAYMAP 24) as a pixel grid.

REDRIVER2 overmap.c: the lump starts with u16 offsets of 32x32 4-bit tiles
(RNC method 2 packed, rnc_2.c), the 16-colour CLUT sits at +512. Tiles run
12 across (width / 32). Pixel (px, py) <-> Driver 2 world:
x = (px - x_offset - 48) * scale, z = (y_offset + 48 - py) * scale.

    m = Overlay("work/d2_CHICAGO.LEV")
    m.at(x, z) -> palette index; m.rgb(index) -> (r, g, b)
"""
from __future__ import annotations

import struct

from levfile import Lev

OVERLAYMAP = 24
# x_offset, y_offset, width, height, toptile, dummy, scale (overmap.c overlaidmaps)
CITY = {"CHICAGO": (197, 318, 384, 672, 252, 0x99, 2145)}
WINDOW = 48     # pixels: the offsets are for the drawn window, not the bitmap (fitted on the roads)


def rnc2(src: bytes, size: int) -> bytes:
    """RNC method 2 unpack (rnc_2.c); src starts after the 18-byte header."""
    out = bytearray()
    p = 0
    bits = 0

    def byte():
        nonlocal p
        b = src[p] if p < len(src) else 0
        p += 1
        return b

    def get(n):
        nonlocal bits
        v = 0
        for _ in range(n):
            nb = 1 if bits & 0x80 else 0
            bits = (bits << 1) & 0xFF
            if not bits:
                bits = byte()
                nb = 1 if bits & 0x80 else 0
                bits = ((bits << 1) & 0xFF) | 1
            v = (v << 1) + nb
        return v

    def offset():
        v = 0
        if get(1):
            v = get(1)
            if get(1):
                v = v * 2 + 4 + get(1)
                if not get(1):
                    v = v * 2 + get(1)
            elif v == 0:
                v = get(1) + 2
        return (v << 8) + byte() + 1

    get(2)
    while len(out) < size and p < len(src):
        if not get(1):
            out.append(byte())
            continue
        length = 2
        if not get(1):
            length = 4 + get(1)
            if get(1):
                length = (length - 1) * 2 + get(1)
                if length == 9:
                    length = (get(4) + 3) * 4
                    for _ in range(length):
                        out.append(byte())
                    continue
            off = offset()
        else:
            if get(1):
                if get(1):
                    length = byte() + 8
                    if length == 8:
                        if not get(1):
                            break
                        continue
                else:
                    length = 3
                off = offset()
            else:
                off = byte() + 1
        for _ in range(length):
            out.append(out[-off] if off <= len(out) else 0)
    return bytes(out[:size])


class Overlay:
    def __init__(self, path: str, city: str = "CHICAGO"):
        lev = Lev.parse(open(path, "rb").read())
        data = None
        for sec in (lev.loadtime, lev.inmem):
            try:
                data = sec.get(OVERLAYMAP).data
                break
            except Exception:
                pass
        self.xo, self.yo, self.w, self.h, self.tiles, self.dummy, self.scale = CITY[city]
        self.clut = [struct.unpack_from("<H", data, 512 + 2 * k)[0] for k in range(16)]
        across = self.w // 32
        self.px = bytearray([self.dummy & 15]) * (self.w * self.h)
        for t in range(self.tiles):
            off = struct.unpack_from("<H", data, 2 * t)[0]
            if data[off: off + 3] != b"RNC":
                continue
            tile = rnc2(data[off + 18:], 512)
            tx, ty = (t % across) * 32, (t // across) * 32
            for k, b in enumerate(tile):
                y, x = divmod(2 * k, 32)
                if ty + y < self.h:
                    self.px[(ty + y) * self.w + tx + x] = b & 15
                    self.px[(ty + y) * self.w + tx + x + 1] = b >> 4

    def rgb(self, i):
        c = self.clut[i]
        return ((c & 31) << 3, ((c >> 5) & 31) << 3, ((c >> 10) & 31) << 3)

    def at(self, x: int, z: int) -> int:
        px, py = self.xo + WINDOW + x // self.scale, self.yo + WINDOW - z // self.scale
        if 0 <= px < self.w and 0 <= py < self.h:
            return self.px[py * self.w + px]
        return self.dummy & 15
