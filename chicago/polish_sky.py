"""polish_sky.py - Driver 2's Chicago skies in Driver 1's SKY.BIN format (Polish, C10).

Driver 1's sky is not level data: the dome models 0..3 are drawn with images from
DRIVER/DATA/SKY.BIN, chosen by the sky number gp+0xD7C (0x800974EC, set at 0x8004EDxx from
CITY: credits 1, LA 2 (rain 3), Miami 4/5/6, NY 7/8/9, SF 10/11/12; +1 night, +2 rain for
Miami/SF/NY); the loader reads 0x34 bytes at number * 0x30 (12 image offsets + the next
one) and then the images. SKY.BIN = 13 x 48-byte tables, the file size, then per sky 12
BMPs (64 x 42, 4-bit, 16 colours) = a 256 x 126 panorama in 4 columns x 3 rows.

Driver 2's DATA/SKY0.RAW (Chicago; read from the player's Driver 2 disc via inputs.py) holds the same layout at
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
RAW = os.environ.get("CHI_D2_SKY")   # override (experiments); default: inputs.py d2_SKY0.RAW (Option A)
PW, PH = 64, 42           # Driver 1 piece
NSKY = 13


V_HORIZON = 105           # Driver 1 dome: v of the horizon (LA's rings: y -31 at v ~80, y 26 at v 127)
D2_ROWS = 168             # Driver 2 rows 0..167 (ry 0 + 1) = clouds down to skyline A's base


def _panorama(seg: int):
    """Driver 2 sky as one 512 x 252 RGB image (per-piece CLUTs applied)."""
    from PIL import Image
    import inputs
    d = open(RAW or inputs.path(__import__("cityprofile").P.sky_raw), "rb").read()[seg * 0x10000:(seg + 1) * 0x10000]
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


def sky_mode() -> str:
    """R35 (user approved the d2raw sky, 18.10.): Chicago's default sky is d2raw (Driver 2's art unmodified, only
    placed); CHI_POLISH_SKY=old = the earlier default (flat ground colour below the horizon), other values as before."""
    v = os.environ.get("CHI_POLISH_SKY", "d2raw")
    return "" if v == "old" else v


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
    if sky_mode() == "d2v2":
        return _cut(_d2_v2(seg))
    if sky_mode() == "d2v3":
        return _cut(_d2_v2(seg, v3=True))
    if sky_mode() == "d2v4":
        return _cut(_d2_v2(seg, v3=True, v4=True))
    if sky_mode() == "d2raw":
        # d2raw (user R34): D2's sky art unmodified, only placed: cap v0..12 = D2's row-0 top colour (D2 draws a flat
        # cap), D2 clouds y0..83 -> v12..61, skyline y84..167 -> v61..108 (horizon), the reflection v108..126 = the
        # flipped skyline at half brightness (as D2 draws its last dome polygons); Lanczos 2:1, no grading. Night = d2v4.
        if seg == SEGMENTS["night"]:
            return _cut(_d2_v2(seg, v3=True, v4=True))
        from PIL import Image, ImageOps
        import numpy as np
        pano = _panorama(seg); L = Image.Resampling.LANCZOS
        full = Image.new("RGB", (256, 126))
        cap = tuple(int(v) for v in np.asarray(pano.crop((0, 0, 512, 1))).reshape(-1, 3).mean(0))
        full.paste(Image.new("RGB", (256, 12), cap), (0, 0))
        full.paste(pano.crop((0, 0, 512, 84)).resize((256, 49), L), (0, 12))
        full.paste(pano.crop((0, 84, 512, D2_ROWS)).resize((256, 47), L), (0, 61))
        refl = ImageOps.flip(pano.crop((0, 126, 512, D2_ROWS))).resize((256, 18), L).point(lambda c: c // 2)
        full.paste(refl, (0, 108))
        return _cut(full)
    if sky_mode() == "d2v6":
        # d2v6 (user R33: skyline too light / grey vs the D2 references): Design's d2v5 sky rows, but the skyline band
        # 0.85 * (0.8 c) + 0.15 (100,104,108): tower darks ~ (99,105,111) instead of (137,144,154); night = d2v4
        im = _d2_v2(seg, v3=True, v4=True)
        if seg != SEGMENTS["night"]:
            import numpy as np
            from PIL import Image
            a = np.asarray(im).astype(float)
            v = np.arange(a.shape[0])[:, None, None].astype(float)
            t = np.clip((v - 62) / 30, 0, 1); t = t * t * (3 - 2 * t)
            sky = 255 - (255 - a) * 0.58
            band = 0.85 * a * 0.8 + 0.15 * np.array([100.0, 104.0, 108.0])
            im = Image.fromarray(np.clip(sky * (1 - t) + band * t, 0, 255).astype(np.uint8))
        return _cut(im)
    if sky_mode() == "d2v5":
        # d2v5 (Design R31, design/sky_d2v5_levels.py): d2v4 + by day a levels pass (sky rows compressed toward white
        # x0.58, smoothstep v62..92 into 0.62 c + 0.38 (160,168,180)); the night sky stays d2v4
        im = _d2_v2(seg, v3=True, v4=True)
        if seg != SEGMENTS["night"]:
            import numpy as np
            from PIL import Image
            sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "design"))
            import sky_d2v5_levels
            im = Image.fromarray(sky_d2v5_levels.d2v5_day(np.asarray(im)).astype(np.uint8))
        return _cut(im)
    if sky_mode() == "d2":
        return _cut(_d2_order(seg))
    if os.environ.get("CHI_POLISH_SKY_GROUND", "") == "grad" and seg != SEGMENTS["night"]:
        _haze_ground(full)
    if sky_mode() == "mirror":
        below = 126 - V_HORIZON
        refl = ImageOps.flip(src.crop((0, V_HORIZON - below, 256, V_HORIZON)))
        refl = refl.point(lambda c: c // 2)
        full.paste(refl, (0, V_HORIZON))
    return _cut(full)


SEAM = os.environ.get("CHI_POLISH_SKY_SEAM", "1") != "0"
BORDER = 3
_EXT = []                 # C76: palette source per piece (the piece + its neighbours' border texels)


def _cut(full):
    """12 dome pieces. C76 (Infrastructure 20.10., user: sky 'cut' lines that move with the view): Driver 1's dome draws
    piece k with u 64k..64k+63 / v 42r..42r+41 (table 0x800BDE40), so the GPU shows texels 64k..64k+62 (the right / bottom
    edge texel is never sampled) and the next piece starts at 64k+64: one panorama column / row is skipped at every piece
    seam - invisible in Driver 1's soft gradients, a visible step in Driver 2's detailed clouds and skyline. SEAM: the
    panorama is resampled to 4 x 63 + 1 by 3 x 41 + 1 and cut with a one-texel overlap, so piece k's hidden last column
    equals piece k + 1's first (seamless). CHI_POLISH_SKY_SEAM=0: the old cut."""
    if not SEAM:
        return [full.crop(((i % 4) * PW, (i // 4) * PH, (i % 4 + 1) * PW, (i // 4 + 1) * PH)) for i in range(12)]
    from PIL import Image
    f = full.resize((4 * (PW - 1) + 1, 3 * (PH - 1) + 1), Image.Resampling.LANCZOS)
    boxes = [((i % 4) * (PW - 1), (i // 4) * (PH - 1), (i % 4) * (PW - 1) + PW, (i // 4) * (PH - 1) + PH) for i in range(12)]
    # palettes from the piece plus a BORDER-texel ring of its neighbours (wrapping around the panorama horizontally): the
    # colours along a seam are in both pieces' 16-colour palettes, so both sides quantise the seam alike (C76)
    W, H = f.size
    wrap = Image.new("RGB", (W + 2 * BORDER, H))
    wrap.paste(f.crop((W - BORDER, 0, W, H)), (0, 0)); wrap.paste(f, (BORDER, 0)); wrap.paste(f.crop((0, 0, BORDER, H)), (W + BORDER, 0))
    _EXT[:] = [wrap.crop((x0, max(0, y0 - BORDER), x1 + 2 * BORDER, min(H, y1 + BORDER))) for x0, y0, x1, y1 in boxes]
    return [f.crop(b) for b in boxes]


D2_SOFT = (84, 0.15, 0.9)     # C56 (Design 16.10.): haze ramp from v 84 (blend 0.15) to the horizon (0.9)
D2_REFL_HAZE = float(os.environ.get("CHI_POLISH_SKY_REFLHAZE", "0.8"))   # day: gradient share over the reflection
D2_REFL_FROM = 140            # reflection: Driver 2 rows 167 .. 140 flipped, half brightness, into v 105..125


def _d2_order(seg: int):
    """CHI_POLISH_SKY=d2 (C46 + C56, Design 16.10.; the generic rule for Driver 2 cities): Driver 2's sky order
    as far as Driver 1's fixed dome allows (data only): Driver 2 rows 0..167 (cap colour, image row 0, row 1 down
    to the skyline's base) squeezed to v 0..V_HORIZON (no crop: TOP=42 cut the clouds and stretched the skyline);
    the skyline's dark base rows v 84..104 blend towards the haze colour (the dark slab at the end of long avenues,
    C56; by day only); below the horizon Driver 2's reflection (row 1 flipped: rows 167 -> 140 at half
    brightness, as REDRIVER2 sky.c draws it) in v 105..125, seen only from high cameras / over the lake."""
    from PIL import Image, ImageOps
    pano = _panorama(seg)
    full = Image.new("RGB", (256, 126))
    full.paste(pano.crop((0, 0, 512, D2_ROWS)).resize((256, V_HORIZON), Image.Resampling.BOX), (0, 0))
    refl = ImageOps.flip(pano.crop((0, D2_REFL_FROM, 512, D2_ROWS))).resize((256, 126 - V_HORIZON), Image.Resampling.BOX)
    full.paste(refl.point(lambda c: c // 2), (0, V_HORIZON))
    if seg != SEGMENTS["night"]:
        v0, f0, f1 = D2_SOFT
        px = full.load()
        for v in range(v0, V_HORIZON):
            f = f0 + (f1 - f0) * (v - v0) / max(1, V_HORIZON - 1 - v0)
            for x in range(256):
                px[x, v] = tuple(int(round(c + (h - c) * f)) for c, h in zip(px[x, v], HAZE_TOP))
        # the band below the horizon IS seen from street level (bridge: screen rows ~75..115): the dark half-
        # brightness reflection read as the C56 slab, so by day it lies under the haze gradient (only a faint
        # mirrored skyline stays: D2_REFL_HAZE of the gradient over it)
        for v in range(V_HORIZON, 126):
            t = (v - V_HORIZON) / (126 - V_HORIZON)
            g = tuple(a + (b - a) * t for a, b in zip(HAZE_TOP, HAZE_LOW))
            for x in range(256):
                px[x, v] = tuple(int(round(c + (h - c) * D2_REFL_HAZE)) for c, h in zip(px[x, v], g))
    return full


HAZE_TOP = (216, 224, 234)  # C56 (Design 16.10.): pale haze at the horizon (v = V_HORIZON) ...
HAZE_LOW = (168, 175, 182)  # ... to a lighter grey at the dome's bottom row (v 126)
HAZE_SOFT = 10              # skyline rows above the horizon blended towards HAZE_TOP (0 .. HAZE_SOFT_MAX)
HAZE_SOFT_MAX = 0.6


def _haze_ground(full):
    """CHI_POLISH_SKY_GROUND=grad (C56, day skies): the band below the horizon (v 105..125) was one flat
    colour from the skyline's dark base row (~48,56,64) and read as a slate wall at the end of long
    avenues. Here it becomes a vertical gradient HAZE_TOP -> HAZE_LOW, and the last HAZE_SOFT skyline rows
    fade towards HAZE_TOP so the skyline's base melts into the haze (Design mockup t1/haze_cmp_base_bridge)."""
    px = full.load()
    w, h = full.size
    for v in range(V_HORIZON, h):
        t = (v - V_HORIZON) / max(1, h - V_HORIZON)
        c = tuple(int(round(a + (b - a) * t)) for a, b in zip(HAZE_TOP, HAZE_LOW))
        for x in range(w):
            px[x, v] = c
    for k in range(HAZE_SOFT):
        v = V_HORIZON - HAZE_SOFT + k
        f = HAZE_SOFT_MAX * (k + 1) / HAZE_SOFT
        for x in range(w):
            r, g, b = px[x, v]
            px[x, v] = tuple(int(round(c + (hz - c) * f)) for c, hz in zip((r, g, b), HAZE_TOP))


def _bmp4(im, pal_src=None) -> bytes:
    """64 x 42 RGB -> 4-bit BMP like Driver 1's (BITMAPINFOHEADER, 16-entry palette, bottom-up). pal_src: the image the
    16 colours are chosen from (C76: the piece with its neighbours' border), default the piece itself."""
    from PIL import Image
    if pal_src is not None:
        pq = pal_src.quantize(colors=16, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE)
        q = im.quantize(palette=pq, dither=Image.Dither.NONE)
    else:
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
    ext = list(_EXT) if SEAM and len(_EXT) == len(pieces) else [None] * len(pieces)
    return [_bmp4(p, e) for p, e in zip(pieces, ext)]


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



V2_HORIZON = 108                          # Design 17.10. (QUEUE 6c): D1's dome horizon is v108 (LA SKY01A bands)
V2_HORIZON_COLOUR = {"day": (176, 186, 198), "night": (38, 38, 35)}


def _d2_v2(seg: int, v3: bool = False, v4: bool = False):
    """CHI_POLISH_SKY=d2v2 (C46/C56, Design's target from the D2 reference shots, data only):
    v 0..26 = flat cap (D2 row 0's colour); D2 clouds y 0..83 -> v 26..61; D2 skyline y 84..167 -> v 61..108
    (horizon v108); by day the last 6 skyline rows (v102..108) blend 25 % toward the skyline base colour (no haze
    ramp: it bleached the towers); v 108..126 = D2's reflection (y 167 -> 126 flipped) at half brightness, then
    35 % toward the horizon colour (day (176,186,198) / night (38,38,35)) so the far-bank gap reads as distance.
    Horizontal 512 -> 256 box filter."""
    # d2v3 (Design QUEUE 8): Lanczos + light unsharp instead of box; deeper blue lower (clouds y0..83 -> v12..61,
    # cap v0..12); by day the skyline rows v84..108 blend 40 % toward the horizon colour with a body floor
    # (110,118,128), so the far city reads as distant haze, not a dark block
    from PIL import Image, ImageOps, ImageFilter
    import numpy as np
    night = seg == SEGMENTS["night"]
    pano = _panorama(seg)
    B = Image.Resampling.LANCZOS if v3 else Image.Resampling.BOX
    sharp = (lambda im: im.filter(ImageFilter.UnsharpMask(radius=1, percent=60, threshold=2))) if v3 else (lambda im: im)
    capv = 12 if v3 else 26
    full = Image.new("RGB", (256, 126))
    cap = tuple(int(v) for v in np.asarray(pano.crop((0, 0, 512, 1))).reshape(-1, 3).mean(0))
    full.paste(Image.new("RGB", (256, capv), cap), (0, 0))
    full.paste(sharp(pano.crop((0, 0, 512, 84)).resize((256, 61 - capv), B)), (0, capv))
    full.paste(sharp(pano.crop((0, 84, 512, D2_ROWS)).resize((256, V2_HORIZON - 61), B)), (0, 61))
    a = np.asarray(full).astype(float)
    if v3 and not night:
        hz = np.array(V2_HORIZON_COLOUR["day"], dtype=float)
        # d2v4 (user R30): one consistent brightness down to the mirror line: the blend covers the whole skyline
        # section v61..108 (v3 started at v84 and left a bright step across the towers)
        lo = 61 if v4 else 84
        a[lo:V2_HORIZON] = np.maximum(a[lo:V2_HORIZON] * 0.6 + hz * 0.4, np.array([110.0, 118.0, 128.0]))
    elif not night:
        base = a[V2_HORIZON - 1].mean(0)
        for v in range(V2_HORIZON - 6, V2_HORIZON):
            a[v] = a[v] * 0.75 + base * 0.25
    refl = np.asarray(ImageOps.flip(pano.crop((0, 126, 512, D2_ROWS))).resize((256, 126 - V2_HORIZON), B)).astype(float)
    hc = np.array(V2_HORIZON_COLOUR["night" if night else "day"], dtype=float)
    a[V2_HORIZON:] = (refl * 0.5) * 0.65 + hc * 0.35
    return Image.fromarray(np.clip(a, 0, 255).astype(np.uint8))


if __name__ == "__main__":
    main()
