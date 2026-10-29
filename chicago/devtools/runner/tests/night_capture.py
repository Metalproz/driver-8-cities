"""C132 helper: Take a Ride CITY at night (NIGHT=0: day), POSE="x,z,heading4096" optional, screenshot + one GPU frame
capture (psxrecomp/tools/gpu_frame_capture.py: GP0 packets attributed to guest functions) into the run dir."""
import math, os, subprocess, sys, time
CITY = os.environ.get("CITY", "vegas")
NIGHT = os.environ.get("NIGHT", "1") == "1"
SESSION = dict(day="var_polish_cheats6_day.lev", night="var_polish_cheats6_night.lev", s4=True)
TOOLS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", "..", "..", "psxrecomp", "tools")


def run(s):
    s.menu("take_a_ride/%s%s" % (CITY, "/night" if NIGHT else "")); s.wait_world(what=CITY)
    if os.environ.get("POSE"):
        x, z, h = (int(v) for v in os.environ["POSE"].split(","))
        s.pose(x, z, h * 2 * math.pi / 4096)
    time.sleep(2)
    s.screenshot("view")
    s.record("night_words", detail="facing %08X %08X car %08X %08X glow count %d LX4 %d carcol %06X" % (
        s.word(0x8002D46C), s.word(0x8002D488), s.word(0x8003A6D0), s.word(0x8003A6D4), s.word(0x8008AE68),
        s.word(0x80093640) - (1 << 32) if s.word(0x80093640) >> 31 else s.word(0x80093640), s.word(0x800971A0) & 0xFFFFFF))
    import collections
    cc = collections.Counter(s.word(0x800971A0) & 0xFFFFFF for _ in range(200))
    s.record("carcol_samples", detail=str({hex(k): v for k, v in cc.most_common(6)}))
    if os.environ.get("NO_CAPTURE") == "1":
        return
    r = subprocess.run([sys.executable, os.path.join(TOOLS, "gpu_frame_capture.py"), "--port", str(s.port), "--tag", "frame",
                        "--out", str(s.dir), "--summary", "--top", "40", "--no-shot"], capture_output=True, text=True, timeout=120)
    (s.dir / "frame_summary.txt").write_text(r.stdout + r.stderr, encoding="utf-8")
    s.record("capture", detail=(r.stdout or r.stderr)[-1500:])
