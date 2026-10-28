"""polish_map.py - Driver 2's Chicago overhead map as Driver 1's minimap (Polish, C12).

Switch CHI_POLISH_MAP (default 1 since b11; 0 = LA's overlay lump stays, as before).

Driver 1's minimap reads lump 24 (OVERLAYMAP): u16 offsets of RNC2-packed 32 x 32 4-bit
tiles at +0 (room for 160), 8 bytes at +320 (kept from the base city), the 16-colour CLUT at
+0x148 (328, read at 0x80054194), tile data after. Its per-city parameters are an exe table
at 0x8008B080 + CITY * 24: x_offset, y_offset, width, height (pixels), toptile (byte; tiles
>= it are filled with the byte at +0x11), scale (units per pixel); column = x_offset + z / scale, row = y_offset + x / scale
(0x800563CC, checked in game: LA's frame at D1 (-87238, z 790527) gives (605, 144)), so a
Driver 1 map is Driver 2's turned a quarter. LA (CITY 3): 324, 175, 192, 416, 78, 2812.

Driver 2's Chicago map is 384 x 672 (252 tiles) at 2145 D2 units per pixel; 252 tiles do not
fit 160, so the map is resampled by 3/4 and turned (512 x 288 = 16 x 9 = 144 tiles, 2831 x 4/3 = 3775
D1 units per pixel), keeping thin features (roads, labels): each new pixel takes the rarest
colour that covers at least a quarter of its footprint.

The CITY 3 table entry must hold Chicago's values while Chicago is loaded (PARAMS below):
that is a plugin change (driver_chicago.c, like the glow offsets); without it the minimap
keeps LA's frame and shows garbage, so this switch only makes sense together with it.
"""
from __future__ import annotations

import collections
import os
import struct

from d2overlay import Overlay, rnc2, WINDOW
import worldscale as ws

# Scale (C12 follow-up, default since b14): 1.5 = 448 x 256 (14 x 8 tiles), within Driver 1's 448 px
# minimap width; CHI_POLISH_MAP_F=4/3 = the old 512 x 288 (16 x 9 tiles).
# CHI_POLISH_MAP_F=1 (C12 zoom, Polish 15.10.): Driver 2's own scale (1 D2 map pixel = 1 minimap pixel; D2 shows
# its map 1:1 in a 64 x 60 window). Needs more than Driver 1's 160 tile slots (Chicago: 21 x 12 = 252), so the
# tile table grows and the CLUT moves behind it (CLUT_AT): the exe reads the CLUT at map + 0x148 (immediate at
# 0x80054194, `addiu a1,a1,0x148`), which must then read CLUT_AT for a Driver 2 city (plugin code word, see NOTES).
_FENV = os.environ.get("CHI_POLISH_MAP_F", "1")      # C12 adopted 16.10. (user verified): D2 zoom; "1.5" = old
F = 1.0 if _FENV == "1" else 4.0 / 3.0 if _FENV == "4/3" else 1.5   # D2 overlay pixels per new pixel (default 1.5 since b14)
NATIVE = F == 1.0
if NATIVE:
    _OV = __import__("d2overlay").CITY[__import__("cityprofile").P.name]   # M3: the city's D2 overlay size
    ACROSS, DOWN = _OV[3] // 32, _OV[2] // 32       # Chicago: 21 x 12 = 672 x 384 (D2 384 x 672 turned)
else:
    ACROSS, DOWN = (14, 8) if F == 1.5 else (16, 9)   # tiles (Driver 1 maps are turned: columns = world z, rows = world x)
W, H = ACROSS * 32, DOWN * 32
MAX_TILES = max(160, ACROSS * DOWN)
CLUT_AT = 0x148 if MAX_TILES == 160 else (2 * MAX_TILES + 8 + 3) // 4 * 4   # behind the table + the 8-byte block
DATA_AT = CLUT_AT + 32
TABLE = 0x8008B080                # exe: per-city minimap parameters, 24 bytes each


def enabled():
    return os.environ.get("CHI_POLISH_MAP", "1") == "1"


def params(ov: Overlay):
    """(x_off, y_off, width, height, toptile | fill << 8, scale) for the exe table.
    Driver 2 pixel: px2 = xo2 + WINDOW + x2 / s2, py2 = yo2 + WINDOW - z2 / s2; Driver 1 world
    x1 = 1.32 x2 + OFFSET_X. New pixel: row qr = px2 / F, column qc = (h2 - py2) / F."""
    k = ws.SCALE * ov.scale
    yo = (ov.xo + WINDOW - ws.OFFSET_X / k) / F
    xo = (ov.h - ov.yo - WINDOW - ws.OFFSET_Z / k) / F
    # the exe's offsets name the minimap WINDOW's corner; the car sits WINDOW (48) pixels in from it
    # (like Driver 2's overmap.c +48), measured in game 14.10.: without this the map showed the area
    # ~50 px down-right of the car (Gold Coast instead of the L downtown)
    # C12 dot calibration (Polish 16.10.): marks at 5 spots (corners, Loop, lakeshore, river) showed the dot the same
    # 1 map row below the true pixel everywhere (no scale drift; column within 1/3 px): CHI_POLISH_MAP_NUDGE="dc,dr"
    # (map pixels added to the exe offsets; "0,-1" = the measured fix)
    dc, dr = (int(v) for v in os.environ.get("CHI_POLISH_MAP_NUDGE", "1,0").split(","))   # C12 default 16.10.
    return round(xo) - WINDOW + dc, round(yo) - WINDOW + dr, W, H, ACROSS * DOWN | (ov.dummy & 15) << 8, round(k * F)


def bitmap(ov: Overlay) -> bytearray:
    freq = collections.Counter(ov.px)
    out = bytearray([ov.dummy & 15]) * (W * H)
    for qy in range(H):                       # row = Driver 2 pixel column (x)
        for qx in range(W):                   # column = Driver 2 pixel row, reversed (z)
            x0, x1 = qy * F, (qy + 1) * F
            y0, y1 = ov.h - (qx + 1) * F, ov.h - qx * F
            cover = collections.Counter()
            for py in range(max(int(y0), 0), min(int(y1 - 1e-9) + 1, ov.h)):
                wy = min(y1, py + 1) - max(y0, py)
                for px in range(int(x0), min(int(x1 - 1e-9) + 1, ov.w)):
                    wx = min(x1, px + 1) - max(x0, px)
                    cover[ov.px[py * ov.w + px]] += wx * wy
            if not cover:
                continue
            area = (x1 - x0) * (y1 - y0)
            cands = [c for c, a in cover.items() if a >= 0.25 * area] or [max(cover, key=cover.get)]
            out[qy * W + qx] = min(cands, key=lambda c: freq[c])
    return out


# --- RNC method 2 packer (the inverse of d2overlay.rnc2) ----------------------
class _Bits:
    def __init__(self):
        self.out = bytearray()
        self.slot = None
        self.n = 8

    def bit(self, b):
        if self.n == 8:
            self.out.append(0)
            self.slot, self.n = len(self.out) - 1, 0
        if b:
            self.out[self.slot] |= 0x80 >> self.n
        self.n += 1

    def bits(self, s):
        for ch in s:
            self.bit(ch == "1")

    def byte(self, v):
        self.out.append(v & 0xFF)


def _offset(w: _Bits, off: int):
    v, lo = (off - 1) >> 8, (off - 1) & 0xFF
    if v == 0:
        w.bits("0")
    elif v == 1:
        w.bits("110")
    elif v in (2, 3):
        w.bits("100" + str(v - 2))
    elif v < 8:
        a, b = (v - 4) >> 1, (v - 4) & 1
        w.bits("1%d1%d1" % (a, b))
    else:
        u, d = v >> 1, v & 1
        a, b = (u - 4) >> 1, (u - 4) & 1
        w.bits("1%d1%d0%d" % (a, b, d))
    w.byte(lo)


def rnc2_pack(data: bytes) -> bytes:
    w = _Bits()
    w.bits("00")
    i, n = 0, len(data)
    while i < n:
        best_len, best_off = 0, 0
        for off in range(1, min(i, 4096) + 1):
            k = 0
            while i + k < n and k < 263 and data[i + k - off] == data[i + k]:
                k += 1
            if k > best_len or (k == best_len and off < best_off):
                best_len, best_off = k, off
        L, off = best_len, best_off
        if L == 2 and off > 256:
            L = 0
        if L == 9:
            L = 8                                      # 9 is the literal-run code
        if L < 2:
            w.bits("0"); w.byte(data[i]); i += 1
            continue
        if L == 2:
            w.bits("110"); w.byte(off - 1)
        elif L == 3:
            w.bits("1110"); _offset(w, off)
        elif L in (4, 5):
            w.bits("10%d0" % (L - 4)); _offset(w, off)
        elif L <= 8:
            x, y = divmod(L - 6, 2)
            w.bits("10%d1%d" % (x, y)); _offset(w, off)
        else:
            w.bits("1111"); w.byte(L - 8); _offset(w, off)
        i += L
    w.bits("1111"); w.byte(0); w.bits("0")             # end of block
    body = bytes(w.out)
    return (b"RNC\x02" + struct.pack(">II", n, len(body)) + struct.pack(">HH", _crc(data), _crc(body))
            + bytes([0, 1]) + body)


def _crc(data: bytes) -> int:
    c = 0
    for b in data:
        c ^= b
        for _ in range(8):
            c = (c >> 1) ^ 0xA001 if c & 1 else c >> 1
    return c


def marks(ov: Overlay, bm: bytearray):
    """TEST ONLY (C12 dot calibration): CHI_POLISH_MAP_MARKS="x,z;..." (Driver 1 coordinates) paints a 7 x 7 dark
    frame around the pixel where the car at (x, z) should be (engine map position + 48, C truncating division);
    in game the dot's offset from the frame's centre is the calibration error in map pixels."""
    v = os.environ.get("CHI_POLISH_MAP_MARKS", "")
    if not v:
        return
    nudge = os.environ.pop("CHI_POLISH_MAP_NUDGE", None)
    P = params(ov)
    if nudge is not None:
        os.environ["CHI_POLISH_MAP_NUDGE"] = nudge
    dark = min(range(16), key=lambda i: sum(ov.rgb(i)))
    for item in v.split(";"):
        x, z = (int(t) for t in item.split(","))
        col = P[0] + WINDOW + int(z / P[5])
        row = P[1] + WINDOW + int(x / P[5])
        for dy in range(-3, 4):
            for dx in range(-3, 4):
                if max(abs(dx), abs(dy)) == 3 and 0 <= row + dy < H and 0 <= col + dx < W:
                    bm[(row + dy) * W + col + dx] = dark
        print("minimap mark: (%d, %d) -> map px col %d row %d" % (x, z, col, row))


def lump(d2_lev: str, base_lump: bytes) -> tuple[bytes, tuple]:
    ov = Overlay(d2_lev)
    bm = bitmap(ov)
    marks(ov, bm)
    tiles = []
    for ty in range(DOWN):
        for tx in range(ACROSS):
            t = bytearray()
            for y in range(32):
                row = bm[(ty * 32 + y) * W + tx * 32: (ty * 32 + y) * W + tx * 32 + 32]
                t += bytes(row[x] | row[x + 1] << 4 for x in range(0, 32, 2))
            tiles.append(bytes(t))
    out = bytearray(DATA_AT)
    out[CLUT_AT - 8:CLUT_AT] = base_lump[320:328]      # the 8-byte block right before the CLUT (unused by the exe code found)
    out[CLUT_AT:CLUT_AT + 32] = struct.pack("<16H", *ov.clut)
    seen = {}
    offs = []
    for t in tiles:
        if t not in seen:
            packed = rnc2_pack(t)
            assert rnc2(packed[18:], 512) == t, "RNC2 round trip failed"
            seen[t] = len(out)
            out += packed
            while len(out) % 4:                           # keep tiles and the lump 4-byte aligned
                out.append(0)
        offs.append(seen[t])
    offs += [offs[0]] * (MAX_TILES - len(offs))
    struct.pack_into("<%dH" % MAX_TILES, out, 0, *offs)
    if CLUT_AT != 0x148 and os.environ.get("CHI_POLISH_MAP_TESTCLUT") == "1":
        # TEST ONLY (no exe change): a second CLUT copy where today's exe reads it (map + 0x148); this
        # overwrites the offsets of tiles 164..179, which then show garbage
        out[0x148:0x168] = struct.pack("<16H", *[c for c in struct.unpack_from("<16H", out, CLUT_AT)])
    prm = params(ov)
    out += TRAILER + struct.pack("<6i", *prm)            # the frame travels with the lump (C12 r2, see below)
    assert len(out) < 0x8000, "tile offsets are read signed (lh at 0x80056390)"
    return bytes(out), prm


# C12 round 2 (Polish 16.10.): probe 'minimap' showed a sheared map with no zoom: the level carried the F=4/3 lump
# (512 x 288, 16 tiles across) but build_package recomputed the exe frame from the environment at package time
# (CHI_POLISH_MAP_F unset there -> F=1.5: 448 x 256, 14 across, scale 4247). The frame the lump was built for is
# now stored after the tile data (the exe reads tiles by offset only) and build_package takes it from there.
TRAILER = b"PMAP"


def stored_params(lump_data: bytes):
    """The exe frame a lump was built with, or None (older lumps)."""
    at = len(lump_data) - 28
    if at >= 0 and lump_data[at:at + 4] == TRAILER:
        return struct.unpack_from("<6i", lump_data, at + 4)
    return None


if __name__ == "__main__":      # python polish_map.py out.png : preview the resampled map + params
    import sys
    from PIL import Image
    import inputs
    ov = Overlay(inputs.path(__import__("cityprofile").P.lev_day))
    bm = bitmap(ov)
    im = Image.new("RGB", (W, H))
    im.putdata([ov.rgb(v) for v in bm])
    im.save(sys.argv[1])
    print("params", params(ov))
