"""Design R33: concept sheet: LA night original | current day level | new day_v2 recipe (largest night-painted textures)."""
import sys, os
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(HERE, "..", "chicago"))
import numpy as np
import la_day_repaint as R, inputs, polish_laday as L
from levfile import Lev
from PIL import Image, ImageDraw
CUR = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "..", "chicago", "work", "var_polish_la_day_13.lev")
FIRST = int(sys.argv[2]) if len(sys.argv) > 2 else 0
def main():
    la = Lev.parse(open(inputs.path("d1_LA.lev"), "rb").read()); ti, tx = L.textures(la); uses = L.use_counts(la)
    cur = Lev.parse(open(CUR, "rb").read()); _, tc = L.textures(cur); bc = {(t[1], t[2]): t for t in tc}
    sp = {p for p, _ in ti.special}; cand = []
    for t in tx:
        n = t[0].upper()
        if n.startswith(L.SKIP_PREFIX) or t[1] in sp or not uses.get((t[1], t[2])) or any(w in n for w in L.AD_WORDS + L.GROUND_WORDS): continue
        dark, warm, Lm, comps = L.night_info(t)
        if dark > L.NIGHT_SHARE or (warm > 0.04 and comps > L.GRID_BLOBS): cand.append((uses[(t[1], t[2])] * t[5] * t[6], t))
    cand.sort(key=lambda x: -x[0]); print(len(cand), "night-painted textures")
    sel = [t for _, t in cand[FIRST:FIRST + 30]]
    S = 84; sh = Image.new("RGB", (5 * (S * 3 + 10), 6 * (S + 14)), (36, 36, 36)); d = ImageDraw.Draw(sh)
    for i, t in enumerate(sel):
        ox, oy = (i % 5) * (S * 3 + 10), (i // 5) * (S + 14); c = bc.get((t[1], t[2]), t)
        for j, (tt, cl) in enumerate(((t, t[7]), (c, c[7]), (t, R.day_v2_clut(t[7], t[8], t[0])))):
            pal = np.array([R.rgb(x) + (0 if x == 0 else 255,) for x in cl], np.uint8); im = Image.fromarray(pal[tt[8]], "RGBA"); k = min(S / im.width, S / im.height)
            im = im.resize((max(1, int(im.width * k)), max(1, int(im.height * k))), Image.NEAREST); bg = Image.new("RGB", (S, S), (255, 0, 255)); bg.paste(im, (0, 0), im); sh.paste(bg, (ox + j * S, oy))
        d.text((ox, oy + S), t[0], fill=(255, 255, 0))
    sh.save(os.path.join(HERE, "out", "laday3_sheet%d.png" % (FIRST // 30)))
main()
