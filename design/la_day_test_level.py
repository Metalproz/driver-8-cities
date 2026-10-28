"""Design test harness: v11 level + day_v3 pixels/CLUT for every night_targets() texture -> design/out/design_laday_test.lev (local test only)."""
import sys, os, struct
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(HERE, "..", "chicago"))
import numpy as np, inputs, polish_laday as L, la_day_repaint as R, la_day_pixels as P
from levfile import Lev
from mapinfo import SpoolInfo, SPOOLINFO
from texpages import BLOCK, MAX_CLUTS, decode_compressed, encode_compressed, pad
from textures import TexInfo
SRC = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "..", "chicago", "work", "var_polish_la_day_13.lev")
OUT = sys.argv[2] if len(sys.argv) > 2 else os.path.join(HERE, "out", "design_laday_test.lev")
ONLY = set(sys.argv[3].split(",")) if len(sys.argv) > 3 else None
la0 = Lev.parse(open(inputs.path("d1_LA.lev"), "rb").read()); _, tx0 = L.textures(la0); uses = L.use_counts(la0)
targets = [t for t in R.night_targets(tx0, uses) if not ONLY or t[0] in ONLY]
ents = []
for t in targets:
    if t[0] in R.VEG_RECIPE:
        ents.append((t[1], t[2], t[3], t[4], t[5], t[6], t[8], struct.pack('<16H', *R.VEG_RECIPE[t[0]](t[7])))); continue      # roads / grass / palms / cone / post: own CLUT recipe
    rgb = np.array([R.rgb(c) for c in t[7]], float)[t[8]]; Lm = rgb @ np.array([0.299, 0.587, 0.114]); lit = ((Lm > 105) & ((rgb[..., 0] - rgb[..., 2]) > 25)).mean()
    qi, wd = P.day_v3(t)                                                # R34: region-based pixel recipe for every night texture
    ents.append((t[1], t[2], t[3], t[4], t[5], t[6], qi, struct.pack("<16H", *wd)))
print(len(ents), "textures")
data = open(SRC, "rb").read(); la = Lev.parse(data)
ti = TexInfo.parse(la.loadtime.get(34).data); sp = SpoolInfo.parse(la.inmem.get(SPOOLINFO).data); spooled = bytearray(la.spooled)
order = list(ti.permanent) + list(ti.special); comp, pos = {}, 0
for page, size in order:
    comp[page] = [decode_compressed(la.tpages[pos: pos + size])[0], la.tpages[pos: pos + size], False]; pos += (size + BLOCK - 1) // BLOCK * BLOCK
for page, k, x, y, w, h, idx, clut in ents:
    if page in comp:
        pg = comp[page][0]; pg.cluts[k] = clut
        for j in range(h):
            for i in range(w): pg.put(x + i, y + j, int(idx[j, i]))
        comp[page][2] = True; continue
    for a in sorted({v[7] for v in sp.spools.values()} - {255}):
        gfx = sp.areas[a][0]
        for kk, pgn in enumerate(p for p in sp.area_tpages[a] if p != 0xFF):
            if pgn != page: continue
            base = (gfx + 17 * kk) * BLOCK; spooled[base + 4 + 32 * k: base + 36 + 32 * k] = clut; tex0 = base + 4 + 32 * MAX_CLUTS + 28
            for j in range(h):
                for i in range(w):
                    o = tex0 + (y + j) * 128 + (x + i) // 2; v = int(idx[j, i])
                    spooled[o] = (spooled[o] & 0x0F) | (v << 4) if (x + i) & 1 else (spooled[o] & 0xF0) | v
la.spooled = bytes(spooled); tp, sizes = bytearray(), {}
for page, size in order:
    pg, blob, changed = comp[page]
    if changed: blob = encode_compressed(pg)
    sizes[page] = len(blob); tp += pad(bytes(blob))
la.tpages = bytes(tp); lump = la.loadtime.get(34); info = bytearray(lump.data); p = ti.end - 8 * 16 - 4 - 8 * 16
for base, lst in ((p, ti.permanent), (p + 8 * 16 + 4, ti.special)):
    for kk, (page, size) in enumerate(lst): struct.pack_into("<ii", info, base + 8 * kk, page, sizes[page])
lump.data = bytes(info); open(OUT, "wb").write(la.build(keep_layout=False)); print("wrote", OUT)
