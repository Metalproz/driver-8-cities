"""Las Vegas + Rio menu pictures (Design, M3): same format / sepia CLUT as HAVANA v2 (make_havana.py, make_previews.py).
Vegas: top = casino block + palm from a game capture of the converted city, a hand-drawn 'Welcome to Fabulous Las Vegas'
style diamond sign breaks the frame; bottom = the street with the car.
Rio: top = D2's own Rio mountain (SKY3.RAW panorama) with a hand-drawn Christ the Redeemer silhouette breaking the frame;
bottom = a downtown Rio facade from a game capture (shadows lifted).
    python make_vegas_rio.py VEGAS_DIR RIO_DIR OUT_DIR   (capture dirs hold the runner PNGs; see CAPS below)
"""
import sys, math
from pathlib import Path
import numpy as np
from PIL import Image, ImageDraw
sys.path.insert(0, str(Path(__file__).parent)); sys.path.insert(0, str(Path(__file__).parents[2] / "chicago"))
import make_havana as mh          # applies the sepia palette
import make_previews as mp


def ss_mask(w, h, draw_fn, S=6):
    im = Image.new("L", (w * S, h * S), 0)
    draw_fn(ImageDraw.Draw(im), S)
    return np.asarray(im.resize((w, h), Image.Resampling.LANCZOS)) > 128


def sign(d, S, cx=96, top=3):
    d.line([(cx * S, (top + 14) * S), (cx * S, (top + 62) * S)], fill=255, width=int(2.4 * S))      # pole
    d.polygon([(cx * S, (top + 3) * S), ((cx + 13) * S, (top + 15) * S), (cx * S, (top + 27) * S), ((cx - 13) * S, (top + 15) * S)], fill=255)
    for k in range(10):                                                                            # star on top
        a = -math.pi / 2 + k * math.pi / 5; r = 5.5 if k % 2 == 0 else 2.2
        pts = [(cx + r * math.cos(a)) * S, (top + 1 + r * math.sin(a)) * S]
        if k == 0: poly = []
        poly.append(tuple(pts))
    d.polygon(poly, fill=255)


def christ(d, S, cx=58, base=42, h=36):
    s = h / 27.0
    X = lambda v: (cx + v * s) * S
    Y = lambda v: (base - v * s) * S
    d.polygon([(X(-7), Y(0)), (X(7), Y(0)), (X(5), Y(5)), (X(-5), Y(5))], fill=255)                 # pedestal
    d.polygon([(X(-3.2), Y(5)), (X(3.2), Y(5)), (X(2.2), Y(21)), (X(-2.2), Y(21))], fill=255)       # robe
    d.polygon([(X(-12), Y(20.5)), (X(12), Y(20.5)), (X(12), Y(18.2)), (X(-12), Y(18.2))], fill=255)  # arms
    d.ellipse((X(-2.1), Y(26.2), X(2.1), Y(21.8)), fill=255)                                        # head


def build(top, street, extra):
    W, H, B, TOPY = mp.W, mp.H, mp.BORDER, mp.TOP
    iw, top_h = W - 2 * B, 60
    canvas = Image.new("L", (W, H), 255)
    canvas.paste(top, (B, TOPY + B)); canvas.paste(street, (B, TOPY + B + top_h))
    idx = mp.grey_to_index(canvas)
    pm = extra
    idx[pm] = 11
    brk = pm.copy(); brk[TOPY + B + 2:, :] = False
    out = mp.compose(idx, brk)
    out[pm & (np.arange(H)[:, None] < TOPY + B) & (out == 0)] = 11
    return out


def clear_sky(path, horizon):
    """the captures have a dusk cloud sky: replace blue-dominant dark pixels above the horizon with a light sky gradient
    (keeps palms, trees, buildings), so the sepia picture reads as a bright day like Havana's."""
    from PIL import ImageFilter
    a = np.asarray(Image.open(path).convert("RGB")).astype(np.int32)
    h, w, _ = a.shape
    m = (a[..., 2] > a[..., 0] + 6) & (a[..., 0] + a[..., 1] + a[..., 2] < 420)
    m[horizon:] = False
    m = np.asarray(Image.fromarray((m * 255).astype(np.uint8)).filter(ImageFilter.MedianFilter(5))) > 128
    grad = np.linspace(0, 1, h)[:, None]
    sky = np.stack([250 - 30 * grad, 240 - 28 * grad, 225 - 40 * grad], -1) * np.ones((1, w, 1))
    a[m] = sky[m].astype(np.int32)
    out = Path(path).with_name(Path(path).stem + "_clear.png")
    Image.fromarray(a.astype(np.uint8)).save(out)
    return out


def cap(d, name):
    return Path(d) / (name + ".png")


def vegas(vdir):
    iw = mp.W - 2 * mp.BORDER; sh = mp.H - mp.TOP - 2 * mp.BORDER - 60
    top = mh.prep(clear_sky(cap(vdir, "a0"), 95), (230, 20, 512, 135), iw, 60, 0.9, 1.3)
    street = mh.prep(cap(vdir, "a0"), (155, 100, 345, 240), iw, sh, 0.7, 1.25)
    return build(top, street, ss_mask(mp.W, mp.H, sign))


def car_cutout(vdir):
    """the clean player car from the Vegas capture (RGBA): pixels that differ from the grey road, largest blob, holes filled.
    Used because Rio's own player car renders smeared until Polish's car-page fix (design/QUEUE)."""
    from PIL import ImageFilter
    from scipy import ndimage as ndi
    im = Image.open(cap(vdir, "a0")).convert("RGB").crop((170, 132, 330, 225))
    a = np.asarray(im).astype(np.int32)
    road = np.median(a[-6:, :8].reshape(-1, 3), 0)
    m = np.abs(a - road).max(-1) > 38
    m = ndi.binary_closing(m, iterations=3); m = ndi.binary_fill_holes(m)
    lab, n = ndi.label(m)
    big = np.argmax(ndi.sum(m, lab, range(1, n + 1))) + 1
    m = ndi.binary_opening(lab == big, iterations=1)
    al = Image.fromarray((m * 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(0.7))
    out = im.convert("RGBA"); out.putalpha(al)
    return out


def rio(rdir, vdir):
    import inputs, polish_sky
    iw = mp.W - 2 * mp.BORDER; sh = mp.H - mp.TOP - 2 * mp.BORDER - 60
    polish_sky.RAW = str(inputs.path("d2_SKY3.RAW"))
    pano = polish_sky._panorama(0)
    top = mp.fit(mp.to_grey(pano.crop((60, 186, 240, 252)), 1.15), iw, 60)
    # street: the Copacabana wave-pattern promenade + beach from a capture at the normal start region (build-test), with Rio's
    # own player car (rio2: D2 model 1, a yellow sedan, seen from behind; pixel-exact 120 x 146 crop). HUD bars painted out.
    fr = Image.open(cap(rdir, "k14500_0")).convert("RGB")
    ref = fr.getpixel((300, 8))
    ImageDraw.Draw(fr).rectangle((0, 0, 190, 60), fill=ref)
    street = mh.prep_img(fr, (195, 94, 315, 240), iw, sh, 1.0, 1.4)
    ex = ss_mask(mp.W, mp.H, lambda d, S: christ(d, S, cx=PEAK[0], base=PEAK[1], h=44))
    return build(top, street, ex)


PEAK = (100, 58)
KCAR = 0.75


if __name__ == "__main__":
    out = Path(sys.argv[3]); out.mkdir(parents=True, exist_ok=True)
    mp.save(vegas(sys.argv[1]), out, "VEGAS", None)
    mp.save(rio(sys.argv[2], sys.argv[1]), out, "RIO", None)
    print("ok")
