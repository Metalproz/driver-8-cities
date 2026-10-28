"""C103: host CPU load of a normal (windowed, paced 100 %) game: run with DT_WINDOWED=1 DT_NORMAL_PRIORITY=1.
CITY (chicago at SPOT fps_drop_2 / miami start), standing; after WARM s: process CPU seconds per wall second over
SECS (all threads; 1.0 = one core), EMU %, FPS; PROF=1 also samples the threads (hostprof.py) into the run dir."""
import ctypes, ctypes.wintypes as W, json, os, subprocess, sys, time
from pathlib import Path
CITY = os.environ.get("CITY", "chicago")
SPOTS = json.load(open(Path(__file__).resolve().parents[2] / "spots.json"))
SPOT = os.environ.get("SPOT", "fps_drop_2")
SESSION = dict(day="var_polish_specdmg2_day.lev", night="var_polish_specdmg2_night.lev", s4=True,
               start=tuple(SPOTS[SPOT]["d2"]) if CITY == "chicago" else None,
               dev_mode=os.environ.get("DEV", "1") == "1")


def cpu_seconds(pid):
    k32 = ctypes.WinDLL("kernel32")
    h = k32.OpenProcess(0x1000, False, pid)
    ft = [W.FILETIME() for _ in range(4)]
    k32.GetProcessTimes(h, *[ctypes.byref(f) for f in ft])
    k32.CloseHandle(h)
    v = lambda f: (f.dwHighDateTime << 32 | f.dwLowDateTime) / 1e7
    return v(ft[2]) + v(ft[3])


def run(s):
    s.menu("take_a_ride/" + CITY); s.wait_world(what="start")
    time.sleep(float(os.environ.get("WARM", "6")))
    pid = s.p.pid
    c0, t0, v0, f0 = cpu_seconds(pid), time.time(), s.word(0x80095250), s.word(0x800970D8)
    prof = None
    if os.environ.get("PROF") == "1":
        prof = subprocess.Popen([sys.executable, str(Path(__file__).resolve().parents[2] / "hostprof.py"), str(pid), "--secs",
                                 os.environ.get("SECS", "20"), "--map", os.environ.get("SYMS", "")],
                                stdout=open(s.dir / "hostprof.txt", "w"), stderr=subprocess.STDOUT)
    time.sleep(float(os.environ.get("SECS", "20")))
    c1, t1, v1, f1 = cpu_seconds(pid), time.time(), s.word(0x80095250), s.word(0x800970D8)
    if prof: prof.wait(60)
    vb = (v1 - v0) & 0xFFFFFFFF
    try:
        lat = s.d.cmd("latency", window=1200)
        (s.dir / "latency.json").write_text(json.dumps(lat), encoding="utf-8")
        s.record("latency", detail=json.dumps(lat.get("summary"))[:1500])
    except Exception as e:
        s.record("latency", detail="err %s" % e)
    s.record("load", detail="%s %s: CPU %.2f cores, EMU %.0f %%, FPS %.1f" % (CITY, os.environ.get("TAG", ""),
             (c1 - c0) / (t1 - t0), vb / (t1 - t0) / 59.94 * 100, ((f1 - f0) & 0xFFFFFFFF) / max(vb, 1) * 59.94))
