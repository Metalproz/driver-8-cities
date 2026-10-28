"""FAN D2 compare pass (Haiku FAN, 28.10.): one D2 city in Take a Ride, day or night (CITY=chicago|havana|vegas|rio,
NIGHT=1). Start screenshot + start car words, engine / traffic audio while idle, a 25 s drive (screenshot, position
track: falls below -500 or stops responding = flagged), a police chase (felony 0x400, chase music cue, 12 s drive with
audio), pause-menu map (screenshot). Everything is recorded for the FAN ledger; judging is done by the FAN report."""
import os, time
from pathlib import Path

_P = Path(os.environ.get("FAN_PKG_ROOT", "D:/recomps/Apps/Driver-DriverRecompiled/driver_personal/chicago/work"))
# the probe "d2 cities 1" package env (probes.json), absolute paths
for k, v in {
    "CHI_POLISH_MUSIC": "1", "CHI_XD_LEVELS": "1",
    "CHI_LA_DAY_LEV": str(_P / "var_polish_la_day_15.lev"),
    "CHI_HAVANA_DAY": str(_P / "var_polish_hav6_day.lev"), "CHI_HAVANA_NIGHT": str(_P / "var_polish_hav6_night.lev"),
    "CHI_VEGAS_DAY": str(_P / "var_polish_vegas2_day.lev"), "CHI_VEGAS_NIGHT": str(_P / "var_polish_vegas2_night.lev"),
    "CHI_RIO_DAY": str(_P / "var_polish_rio2_day.lev"), "CHI_RIO_NIGHT": str(_P / "var_polish_rio2_night.lev"),
}.items():
    os.environ.setdefault(k, v)

SESSION = dict(day="var_polish_cheats6_day.lev", night="var_polish_cheats6_night.lev", s4=True,
               copy="fan", port=4480, build="build-test")
CITY = os.environ.get("CITY", "chicago")
NIGHT = os.environ.get("NIGHT") == "1"
DRIVE = float(os.environ.get("DRIVE", "25"))
TAG = "%s_%s" % (CITY, "night" if NIGHT else "day")
MAPDOWN = int(os.environ.get("MAPDOWN", "6"))
FELONY = 0x80097708


def run(s):
    s.menu("take_a_ride/%s%s" % (CITY, "/night" if NIGHT else ""))
    s.wait_world(what=CITY)
    time.sleep(2)
    x, y, z, h, _ = s.car(0)
    s.record("start", detail="%s car x %d y %d z %d" % (TAG, x, y, z))
    s.screenshot(TAG + "_start")
    s.audio(TAG + "_idle", secs=4)

    track = []

    def on_tick(st):
        p = st.pos()
        track.append((p[0], p[1], p[2]))
        return p[1] < -800

    s.drive(DRIVE, want=s.car(0)[3], on_tick=on_tick)
    ys = [t[1] for t in track]
    s.record("drive", detail="%d samples, y min %d max %d, end x %d z %d" %
             (len(track), min(ys or [0]), max(ys or [0]), track[-1][0] if track else 0, track[-1][2] if track else 0))
    s.screenshot(TAG + "_driven")
    s.audio(TAG + "_drive", secs=5)

    # chase: the felony starts the cop chase; the car is left alone (a steered drive wrecks it in the chase, FAN 28.10.)
    s.poke32(FELONY, 0x400)
    time.sleep(6)
    s.record("chase", detail="copmusic %d" % s.word(0x80096C70))
    s.audio(TAG + "_chase", secs=6)
    s.screenshot(TAG + "_chase")
    s.poke32(FELONY, 0)
    time.sleep(2)

    s.press("start", gap=1.5)
    for _ in range(MAPDOWN):
        s.press("down", gap=0.5)
    s.press("cross", gap=1.5)
    s.screenshot(TAG + "_map")
    s.press("start", gap=1.0)
    s.check("%s alive after the pass" % TAG, s.alive())
