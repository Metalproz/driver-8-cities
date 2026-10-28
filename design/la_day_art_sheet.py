"""Design R31: concept sheet for the LA day art pass (originals | current donor | new recipe)."""
import sys, os, json
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(HERE, "..", "chicago"))
import numpy as np
from PIL import Image, ImageDraw
import inputs, polish_laday as L, la_day_repaint as R
from levfile import Lev
def img(t, clut, S=88):
    pal = np.array([R.rgb(c) + (0 if c == 0 else 255,) for c in clut], np.uint8); im = Image.fromarray(pal[t[8]], "RGBA")
    k = min(S / im.width, S / im.height); im = im.resize((max(1, int(im.width * k)), max(1, int(im.height * k))), Image.NEAREST)
    bg = Image.new("RGB", (S, S), (255, 0, 255)); bg.paste(im, (0, 0), im); return bg
def main():
    la = Lev.parse(open(inputs.path("d1_LA.lev"), "rb").read()); _, lat = L.textures(la); by = {t[0]: t for t in lat}
    sw = json.load(open(inputs.WORK + "/polish_la_day_table.json"))["swaps"]; dm = {}
    for dn in L.DONORS:
        dl = Lev.parse(open(inputs.path(dn), "rb").read()); _, tx = L.textures(dl)
        for t in tx: dm[(dn, t[1], t[2])] = t
    rows = []   # (label, original, [(label, clut)])
    for n in ("ROAD2A", "ROAD01A", "NEWROAD3", "PATHC"):
        t = by[n]; s = next(x for x in sw if x["la"] == n); d = dm[(s["donor"], s["donor_page"], s["donor_k"])]
        rows.append((n, [(t, t[7]), (d, d[7]), (t, R.asphalt_clut(t[7]))]))
    ex = [s for s in sw if s["la"] in ("SM04", "SS2-57", "SM2-09", "NEW01", "ROD16", "DT3-03")]
    for s in ex:
        t = by[s["la"]]; d = dm[(s["donor"], s["donor_page"], s["donor_k"])]
        rows.append((s["la"] + ">" + s["donor_tex"], [(t, t[7]), (d, d[7]), (d, R.la_grade_clut(d[7]))]))
    for n, fn in (("DT2-35A", R.veg_clut), ("DT2-35B", R.trunk_clut), ("TREE", R.veg_clut), ("CONE2", R.cone_clut), ("GRASS02", R.VEG_RECIPE["GRASS02"])):
        t = by[n]; rows.append((n, [(t, t[7]), (t, t[7]), (t, fn(t[7]))]))
    S = 90; W = 3 * (S + 4); cols = 3
    sh = Image.new("RGB", (cols * (W + 6), ((len(rows) + cols - 1) // cols) * (S + 14)), (36, 36, 36)); d = ImageDraw.Draw(sh)
    for i, (lab, trip) in enumerate(rows):
        ox, oy = (i % cols) * (W + 6), (i // cols) * (S + 14)
        for j, (t, cl) in enumerate(trip): sh.paste(img(t, cl, S), (ox + j * (S + 4), oy))
        d.text((ox, oy + S + 1), lab[:30], fill=(255, 255, 0))
    sh.resize((sh.width * 2, sh.height * 2), Image.NEAREST).save(os.path.join(HERE, "out", "la_art_sheet.png"))
main()
