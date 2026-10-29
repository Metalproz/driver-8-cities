"""C134 (Vegas Fremont start: VRAM noise where Driver 2 has no ground): start Las Vegas at D2 (172000, 682000) (package start
CHI_START_VEGAS; runner env), screenshot; the screen area left of / below the minimap (x 320..395, y 150..235) must not be
noise (mean neighbour difference of RGB < 12; the noise measured ~60+). DRAWENV isbg words recorded."""
import os, time
os.environ.setdefault("CHI_START_VEGAS", "172000,682000,0")   # package start (read when the session packages)
SESSION = dict(day="var_polish_cheats6_day.lev", night="var_polish_cheats6_night.lev", s4=True)


def run(s):
    s.menu("take_a_ride/vegas"); s.wait_world(what="vegas")
    time.sleep(2)
    path = s.screenshot("fremont")
    from PIL import Image
    import numpy as np
    im = np.asarray(Image.open(path).convert("RGB"), dtype=np.int16)
    h, w = im.shape[:2]
    x0, x1, y0, y1 = int(320 * w / 512), int(395 * w / 512), int(150 * h / 240), int(235 * h / 240)
    reg = im[y0:y1, x0:x1]
    noise = float(np.abs(np.diff(reg, axis=1)).mean())
    s.record("isbg", detail="%08X %08X" % (s.word(0x800BDFB4 + 0x18), s.word(0x800BE034 + 0x18)))
    s.check("Fremont start: no VRAM noise beside the minimap", noise < 12, "neighbour diff %.1f" % noise)
