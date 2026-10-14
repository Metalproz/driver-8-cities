"""polish_sky.py - Driver 2's Chicago skies in Driver 1's SKY.BIN format (Polish, C10).

Driver 1's sky is not level data: the dome models 0..3 are drawn with images from
DRIVER/DATA/SKY.BIN, chosen by the sky number gp+0xD7C (0x800974EC, set at 0x8004EDxx from
CITY: credits 1, LA 2 (rain 3), Miami 4/5/6, NY 7/8/9, SF 10/11/12; +1 night, +2 rain for
Miami/SF/NY); the loader reads 0x34 bytes at number * 0x30 (12 image offsets + the next
one) and then the images. SKY.BIN = 13 x 48-byte tables, the file size, then per sky 12
BMPs (64 x 42, 4-bit, 16 colours) = a 256 x 126 panorama in 4 columns x 3 rows.

Driver 2's DATA/SKY0.RAW (Chicago; extracted to work/d2_SKY0.RAW) holds the same layout at
twice the size: 5 x 64 KB VRAM images (day, night, rain, dawn, dusk) of 512 x 252 4-bit
texels in 12 pieces of 128 x 84, one 16-colour CLUT per piece at rows 252..254.

    python polish_sky.py D1_SKY.BIN OUT.BIN [--replace N=day,M=night] [--append day,night,rain]
    python polish_sky.py --preview day OUT.png

--append (default day,night,rain) adds Chicago skies as numbers 13, 14, 15 (the plugin would
set 0x800974EC for Chicago); --replace overwrites skies in place with the same size (test
only: e.g. 2=day makes LA's sky Chicago's, the file stays where it is on the disc).
"""
from __future__ import annotations

import io
import math
import os
import struct
import sys

SEGMENTS = {"day": 0, "night": 1, "rain": 2, "dawn": 3, "dusk": 4}
RAW = os.path.join(os.path.dirname(os.path.abspath(__file__)), "work", "d2_SKY0.RAW")
PW, PH = 64, 42           # Driver 1 piece
NSKY = 13


V_HORIZON = 105           # Driver 1 dome: v of the horizon (LA's rings: y -31 at v ~80, y 26 at v 127)
D2_ROWS = 168             # Driver 2 rows 0..167 (ry 0 + 1) = clouds down to skyline A's base


def _panorama(seg: int):
    """Driver 2 sky as one 512 x 252 RGB image (per-piece CLUTs applied)."""
    from PIL import Image
    d = open(RAW, "rb").read()[seg * 0x10000:(seg + 1) * 0x10000]
    im = Image.new("RGB", (512, 252))
    px = im.load()
    for ry in range(3):
        for p in range(4):
            cl = [struct.unpack_from("<H", d, (252 + ry) * 256 + 2 * (16 * p + k))[0] for k in range(16)]
            for y in range(84):
                for x in range(128):
                    b = d[(ry * 84 + y) * 256 + (p * 128 + x) // 2]
                    t = (b >> 4) if x & 1 else (b & 15)
                    w = cl[t]
                    px[p * 128 + x, ry * 84 + y] = ((w & 31) << 3, (w >> 5 & 31) << 3, (w >> 10 & 31) << 3)
    return im


def _pieces(seg: int):
    """12 RGB pieces (64 x 42) of a Driver 1 panorama (256 x 126): Driver 2's continuous rows
    TOP..167 (clouds down to the skyline's base) squeezed to v 0..V_HORIZON (Driver 1's dome
    reads the 12 pieces through its own fixed per-piece UV table, 0x800BDE40, and ignores the
    sky models' UVs, so the arrangement can only be set here). Below the horizon:
    CHI_POLISH_SKY=mirror = the rows above it mirrored at half brightness (Driver 2 draws the
    flipped rows as the sky's reflection, REDRIVER2 sky.c y3/y4), else one flat ground colour.
    Driver 2's second skyline band (ry 2) is used by D2 for two of its four dome models; Driver 1
    has one panorama for all quadrants, so it is not used."""
    from PIL import Image, ImageOps
    top = int(os.environ.get("CHI_POLISH_SKY_TOP", "0"))
    src = _panorama(seg).crop((0, top, 512, D2_ROWS)).resize((256, V_HORIZON), Image.Resampling.BOX)
    base = src.crop((0, V_HORIZON - 1, 256, V_HORIZON)).resize((1, 1), Image.Resampling.BOX).getpixel((0, 0))
    full = Image.new("RGB", (256, 126), base)
    full.paste(src, (0, 0))
    if os.environ.get("CHI_POLISH_SKY", "") == "mirror":
        below = 126 - V_HORIZON
        refl = ImageOps.flip(src.crop((0, V_HORIZON - below, 256, V_HORIZON)))
        refl = refl.point(lambda c: c // 2)
        full.paste(refl, (0, V_HORIZON))
    return [full.crop(((i % 4) * PW, (i // 4) * PH, (i % 4 + 1) * PW, (i // 4 + 1) * PH)) for i in range(12)]


def _bmp4(im) -> bytes:
    """64 x 42 RGB -> 4-bit BMP like Driver 1's (BITMAPINFOHEADER, 16-entry palette, bottom-up)."""
    from PIL import Image
    q = im.quantize(colors=16, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE)
    pal = (q.getpalette() or [])[:48]
    pal += [0] * (48 - len(pal))
    w, h = q.size
    stride = ((w * 4 + 31) // 32) * 4
    pix = q.tobytes()
    rows = b""
    for y in range(h - 1, -1, -1):
        line = bytearray(stride)
        for x in range(0, w, 2):
            line[x // 2] = pix[y * w + x] << 4 | (pix[y * w + x + 1] if x + 1 < w else 0)
        rows += bytes(line)
    palb = b""
    for k in range(16):
        r, g, b = (max(c, 8) for c in pal[3 * k:3 * k + 3])     # pure black would be a transparent CLUT word
        palb += bytes([b, g, r, 0])
    off = 14 + 40 + 64
    hdr = struct.pack("<2sIHHI", b"BM", off + len(rows), 0, 0, off)
    info = struct.pack("<IiiHHIIiiII", 40, w, h, 1, 4, 0, len(rows), 0, 0, 16, 0)
    blob = hdr + info + palb + rows
    return blob + bytes(-len(blob) % 4)            # Driver 1 keeps every image 4-byte aligned (1464)


def _pieces_test():
    """CHI_POLISH_SKY_TEST=1 (diagnostic): row r top half / bottom half in distinct colours, piece p
    marked by a white bar of p+1 texels at its left edge."""
    from PIL import Image, ImageDraw
    cols = [((255, 0, 0), (0, 200, 0)), ((0, 0, 255), (255, 255, 0)), ((255, 0, 255), (0, 255, 255))]
    out = []
    for r in range(3):
        for p in range(4):
            im = Image.new("RGB", (PW, PH), cols[r][0])
            d = ImageDraw.Draw(im)
            d.rectangle([0, PH // 2, PW - 1, PH - 1], fill=cols[r][1])
            d.rectangle([0, 0, 4 * (p + 1) - 1, PH - 1], fill=(255, 255, 255))
            out.append(im)
    return out


def sky_bmps(name: str) -> list[bytes]:
    if os.environ.get("CHI_POLISH_SKY_TEST") == "1":
        return [_bmp4(p) for p in _pieces_test()]
    pieces = _pieces(SEGMENTS[name])
    return [_bmp4(p) for p in pieces]


def read_skybin(data: bytes) -> list[list[bytes]]:
    n = struct.unpack_from("<I", data, 0)[0] // 48
    skies = []
    for s in range(n):
        offs = list(struct.unpack_from("<13I", data, 48 * s))
        skies.append([data[offs[i]:offs[i + 1]] for i in range(12)])
    return skies


def write_skybin(skies: list[list[bytes]]) -> bytes:
    head = 48 * len(skies) + 4
    out, offs, p = bytearray(), [], head
    for sky in skies:
        row = []
        for bmp in sky:
            row.append(p)
            out += bmp
            p += len(bmp)
        offs.append(row)
    table = b"".join(struct.pack("<12I", *row) for row in offs) + struct.pack("<I", p)
    return table + bytes(out)


def main():
    a = sys.argv[1:]
    if a and a[0] == "--preview":
        from PIL import Image
        im = Image.new("RGB", (256, 126))
        for i, b in enumerate(sky_bmps(a[1])):
            im.paste(Image.open(io.BytesIO(b)).convert("RGB"), ((i % 4) * 64, (i // 4) * 42))
        im.resize((512, 252)).save(a[2])
        return
    src, dst = a[0], a[1]
    data = open(src, "rb").read()
    skies = read_skybin(data)
    assert len(skies) == NSKY and write_skybin(skies) == data, "SKY.BIN layout not as expected"
    if "--replace" in a:
        for item in a[a.index("--replace") + 1].split(","):
            n, name = item.split("=")
            new = sky_bmps(name)
            old = skies[int(n)]
            assert all(len(b) <= len(o) for b, o in zip(new, old)), "replace: a new image is larger"
            skies[int(n)] = [b + bytes(len(o) - len(b)) for b, o in zip(new, old)]   # same offsets
    else:
        names = a[a.index("--append") + 1].split(",") if "--append" in a else ["day", "night", "rain"]
        for name in names:
            skies.append(sky_bmps(name))
    out = write_skybin(skies)
    open(dst, "wb").write(out)
    print("wrote %s: %d skies, %d bytes (was %d)" % (dst, len(skies), len(out), len(data)))


if __name__ == "__main__":
    main()
