"""C94 "Extra draw distance": CITY (miami|frisco|la|ny|chicago, default miami) Take a Ride, standing screenshot, then
drive DRIVE s (default 20) sampling the primitive-buffer use of the current draw buffer (high water vs the XOBJ / XTILE
limit words), guest FPS standing and driving, alive. Run once with RUNNER_XDRAW=1 (feature on) and once without (Driver 1
values) for the comparison; RUNNER_UNCAP as wanted. Chicago starts at SPOT (default fps_drop_2)."""
import json, math, os, time
from pathlib import Path
CITY = os.environ.get("CITY", "miami")
SPOTS = json.load(open(Path(__file__).resolve().parents[2] / "spots.json"))
SPOT = os.environ.get("SPOT", "fps_drop_2")
LEV = os.environ.get("LEV", "var_polish_specdmg2")
SESSION = dict(day=LEV + "_day.lev", night=LEV + "_night.lev", s4=True,
               start=tuple(SPOTS[SPOT]["d2"]) if CITY == "chicago" else None)
XR, XOBJ, XTILE, XPB0 = 0x80093404, 0x80093418, 0x8009341C, 0x80093420


def run(s):
    on = bool(os.environ.get("RUNNER_XDRAW"))
    s.menu("take_a_ride/" + CITY); s.wait_world(what="start")
    time.sleep(2)
    r, lim_o, lim_t, pb0 = s.word(XR), s.word(XOBJ), s.word(XTILE), s.word(XPB0)
    s.check("feature words %s" % ("on" if on else "off"), (r == 13) == on,
            "XR %d XOBJ %#x XTILE %#x XPB0 %#x" % (r, lim_o, lim_t, pb0))
    if os.environ.get("POSE"):                          # x,z,heading: same view for the on / off comparison
        x, z, hd = (float(v) for v in os.environ["POSE"].split(","))
        s.pose(int(x), int(z), hd); time.sleep(2)
    s.screenshot("%s_%s_stand" % (CITY, "on" if on else "off"))
    fps_s, pk_s = s.perf(6.0)
    hw = [0]

    def tick(s):
        b = s.word(0x80097530)
        used = (s.word(b) - s.word(b + 8)) & 0xFFFFFFFF
        if used < 0x100000:
            hw[0] = max(hw[0], used)
        trail.append(s.pos()); del trail[:-6]
    trail = []
    p0, v0 = s.word(0x800970D8), s.word(0x80095250)
    s.drive(float(os.environ.get("DRIVE", "20")), on_tick=tick)
    p1, v1 = s.word(0x800970D8), s.word(0x80095250)
    fps_d = round(((p1 - p0) & 0xFFFFFFFF) / max((v1 - v0) & 0xFFFFFFFF, 1) * 59.94, 1)
    s.screenshot("%s_%s_drive" % (CITY, "on" if on else "off"))
    if len(trail) > 4:
        (ax, _, az), (bx, _, bz) = trail[0], trail[-1]
        s.record("pos", detail="POSE=%d,%d,%.2f (end of drive, heading of travel)" % (bx, bz, math.atan2(bx - ax, bz - az)))
    s.record("pvs", detail="XPVS %d XR %d level entry %08X" % (s.word(0x80093430), s.word(0x80093404), s.word(0x800BE0A4 + 96)))
    s.record("perf", detail="%s %s uncap %s: FPS standing %.1f (%d GP0/frame), driving %.1f; prim high water %#x of XOBJ %#x"
             % (CITY, "ON" if on else "off", os.environ.get("RUNNER_UNCAP", "off"), fps_s, pk_s, fps_d, hw[0], lim_o))
    s.check("%s alive" % CITY, s.alive(2.0))
