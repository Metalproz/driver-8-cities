import sys, os
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(HERE, "..", "chicago"))
import numpy as np, la_day_repaint as R, la_day_pixels as P, inputs, polish_laday as L
from levfile import Lev
from PIL import Image, ImageDraw
names = sys.argv[1].split(",")
la = Lev.parse(open(inputs.path("d1_LA.lev"), "rb").read()); _, tx = L.textures(la); by = {t[0]: t for t in tx}
S = 100; sh = Image.new("RGB", (len(names) * (S + 4), 3 * (S + 4) + 12), (36, 36, 36)); d = ImageDraw.Draw(sh)
for i, n in enumerate(names):
    t = by[n]; qi, wd = P.day_v3(t)
    for j, (ix, cl) in enumerate(((t[8], t[7]), (t[8], __import__('la_day_v4').day_v4_clut(t[7], t[8], n)), (qi, wd))):
        pal = np.array([R.rgb(c) + (0 if c == 0 else 255,) for c in cl], np.uint8); im = Image.fromarray(pal[ix], "RGBA"); k = min(S / im.width, S / im.height)
        im = im.resize((max(1, int(im.width * k)), max(1, int(im.height * k))), Image.NEAREST); bg = Image.new("RGB", (S, S), (255, 0, 255)); bg.paste(im, (0, 0), im); sh.paste(bg, (i * (S + 4), j * (S + 4)))
    d.text((i * (S + 4), 3 * (S + 4)), n, fill=(255, 255, 0))
sh.save(os.path.join(HERE, "out", "laday3b_sheet.png"))
