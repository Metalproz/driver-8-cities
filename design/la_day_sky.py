"""Design: a Los Angeles DAY sky in Driver 1's own SKY.BIN layout (R30). Recipe only, nothing is stored:
base = Driver 1's San Francisco day sky (sky 10: blue sky, thin cloud streaks, hills) read from the player's disc
(chicago/inputs.py), re-graded warm and hazy (LA smog light), hills tinted lavender-brown, plus a procedural low LA
skyline (script-generated block silhouettes, fixed seed: no hand-painted pixels) standing on the horizon.
    python la_day_sky.py preview OUT.png     mockup next to D1's Miami / SF / NY day skies
    python la_day_sky.py bmps                (library) la_day_pieces() -> 12 PIL images 64x42 ; la_day_bmps() -> 12 4-bit BMPs
    python la_day_sky.py bin OUT.BIN         D1's 13 skies + the LA day sky as sky 13 (same layout; written locally only)
Horizon = v108 (Design QUEUE 6c, D1 dome band 3 horizon)."""
import sys, os, io, math, random
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "chicago"))
import numpy as np
from PIL import Image, ImageFilter
import inputs, polish_sky as P
BASE_SKY = 10; HORIZON = 108
TOP_TINT = (0.97, 1.0, 1.0)            # keep D1's blue top almost as is
HAZE = np.array([238, 216, 186], float)  # warm LA haze at the horizon
GROUND = np.array([168, 152, 128], float)
def _sky_image(n):
    sk = P.read_skybin(open(inputs.path("d1_SKY.BIN"), "rb").read())
    im = Image.new("RGB", (256, 126))
    for i, b in enumerate(sk[n]):
        im.paste(Image.open(io.BytesIO(b)).convert("RGB"), ((i % 4) * 64, (i // 4) * 42))
    return im
def _smooth(a, b, x): t = np.clip((x - a) / (b - a), 0, 1); return t * t * (3 - 2 * t)
def la_day_image():
    a = np.asarray(_sky_image(BASE_SKY), float)
    h, w, _ = a.shape
    v = np.arange(h)[:, None, None]
    # 1. warm haze rising toward the horizon (alpha 0 at v40 -> 0.78 at the horizon)
    alpha = 0.78 * _smooth(34, HORIZON, v)
    sky = a * (1 - alpha) + HAZE * alpha
    # 2. top: slightly deeper and less green than SF, LA is a clear blue under the haze
    top = 1 - _smooth(0, 60, v)
    sky = sky * (1 - 0.12 * top) + np.array([70, 110, 190]) * 0.12 * top
    # 3. the hills of the base sky (v ~86..108, darker than the sky) -> lavender-brown, hazy
    lum = a.mean(2, keepdims=True)
    row_lum = lum[:, :, 0].mean(1, keepdims=True)[:, :, None] if False else None
    hills = (lum < 150) & (v > 84) & (v <= HORIZON + 1)
    tint = np.array([132, 118, 140], float)
    sky = np.where(hills, (a * 0.55 + tint * 0.45) * 0.7 + HAZE * 0.3, sky)
    # 4. procedural LA skyline on the horizon: rows of blocks, a few towers, hazy blue-grey, fixed seed
    rnd = random.Random(1947)
    sil = np.zeros((h, w), float)
    x = 0
    while x < w:
        bw = rnd.randint(2, 7); hh = rnd.choice([1, 2, 3, 3, 4, 5, 7, 9]) + (rnd.random() < 0.05) * rnd.randint(10, 18)
        top_v = HORIZON - hh
        sil[top_v:HORIZON + 1, x:x + bw] = 1
        x += bw + rnd.randint(0, 3)
    sil_img = Image.fromarray((sil * 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(0.5))
    s = np.asarray(sil_img, float)[:, :, None] / 255
    build = np.array([150, 150, 166], float) * 0.6 + HAZE * 0.4
    sky = sky * (1 - s * 0.7) + build * s * 0.7
    # 5. below the horizon: flat warm ground like D1's skies (v > horizon blends to GROUND)
    g = _smooth(HORIZON - 1, HORIZON + 4, v)
    sky = sky * (1 - g) + GROUND * g
    return Image.fromarray(np.clip(sky, 0, 255).astype(np.uint8))
def la_day_pieces():
    im = la_day_image()
    return [im.crop(((i % 4) * 64, (i // 4) * 42, (i % 4) * 64 + 64, (i // 4) * 42 + 42)) for i in range(12)]
def la_day_bmps():
    return [P._bmp4(p) for p in la_day_pieces()]
def preview(out):
    from PIL import ImageDraw
    names = [(4, "Miami day (4)"), (10, "San Francisco day (10)"), (7, "New York day (7)")]
    sh = Image.new("RGB", (256 * 2 + 10, (126 + 14) * 2), (30, 30, 30)); d = ImageDraw.Draw(sh)
    ims = [(_sky_image(n), t) for n, t in names] + [(Image.open(io.BytesIO(b"")) if False else None, "")]
    cells = [(_sky_image(n), t) for n, t in names]
    pieces = la_day_pieces(); lad = Image.new("RGB", (256, 126))
    for i, b in enumerate(la_day_bmps()):
        lad.paste(Image.open(io.BytesIO(b)).convert("RGB"), ((i % 4) * 64, (i // 4) * 42))   # after 4-bit quantisation
    cells.append((lad, "LA day (new, 4-bit)"))
    for i, (im, t) in enumerate(cells):
        ox, oy = (i % 2) * 266, (i // 2) * 140
        sh.paste(im.resize((256 * 1, 126 * 1)) if False else im.resize((256, 126)), (ox, oy + 12))
        d.text((ox, oy), t, fill=(255, 255, 0))
    sh = sh.resize((sh.width * 2, sh.height * 2), Image.NEAREST); sh.save(out)
def build_bin(out):
    sk = P.read_skybin(open(inputs.path("d1_SKY.BIN"), "rb").read())
    sk.append(la_day_bmps()); open(out, "wb").write(P.write_skybin(sk)); print("wrote", out, len(sk), "skies")
if __name__ == "__main__":
    c = sys.argv[1] if len(sys.argv) > 1 else "preview"
    if c == "preview": preview(sys.argv[2] if len(sys.argv) > 2 else os.path.join(HERE, "out", "la_day_sky_preview.png"))
    elif c == "bin": build_bin(sys.argv[2])
