"""C119: overclock host guard on a simulated slow host. Run windowed + paced: DT_WINDOWED=1 DT_NORMAL_PRIORITY=1
(RUNNER_UNCAP / RUNNER_XDRAW as wanted). In the level the game is pinned to one core (CORE, default 3) and a hog process
on the same core at ABOVE_NORMAL priority spins LOAD of each 100 ms (default 0.6). Stands SECS (default 120) at SPOT
(default fps_drop_2, CITY=chicago), records EMU % / FPS per 4 s and the guard's log lines. CHI_OC_GUARD=1 = the C115 rule."""
import ctypes, glob, json, os, subprocess, sys, time
from pathlib import Path
SPOTS = json.load(open(Path(__file__).resolve().parents[2] / "spots.json"))
SPOT = os.environ.get("SPOT", "fps_drop_2")
CITY = os.environ.get("CITY", "chicago")
CORE = int(os.environ.get("CORE", "3"))
LOAD = float(os.environ.get("LOAD", "0.6"))
SECS = float(os.environ.get("SECS", "120"))
SESSION = dict(day="var_polish_specdmg2_day.lev", night="var_polish_specdmg2_night.lev", s4=True,
               start=tuple(SPOTS[SPOT]["d2"]) if CITY == "chicago" else None,
               env={k: os.environ[k] for k in ("CHI_OC_GUARD",) if k in os.environ})
HOG = r"""
import ctypes, sys, time
k = ctypes.WinDLL("kernel32"); k.GetCurrentProcess.restype = ctypes.c_void_p; h = ctypes.c_void_p(k.GetCurrentProcess())
k.SetProcessAffinityMask(h, ctypes.c_size_t(1 << int(sys.argv[1]))); k.SetPriorityClass(h, 0x8000)
on = float(sys.argv[2]) * 0.100
while True:
    t = time.perf_counter()
    while time.perf_counter() - t < on: pass
    time.sleep(max(0.0, 0.100 - on))
"""


def pin(pid, core):
    k = ctypes.WinDLL("kernel32")
    k.OpenProcess.restype = ctypes.c_void_p
    h = ctypes.c_void_p(k.OpenProcess(0x0200 | 0x0400, False, pid))      # PROCESS_SET_INFORMATION | QUERY_INFORMATION
    ok = k.SetProcessAffinityMask(h, ctypes.c_size_t(1 << core)); k.CloseHandle(h)
    return bool(ok)


def run(s):
    s.menu("take_a_ride/" + CITY); s.wait_world(what="start")
    hog = None
    try:
        s.record("pin", detail="game pid %d on core %d: %s; hog load %.2f" % (s.p.pid, CORE, pin(s.p.pid, CORE), LOAD))
        hog = subprocess.Popen([sys.executable, "-c", HOG, str(CORE), str(LOAD)])
        series = []
        t_end = time.time() + SECS
        state = {"a": s.word(0x80095250), "f": s.word(0x800970D8), "t": time.time()}

        def tick(ss):
            now = time.time()
            if now - state["t"] >= 4.0:
                v, f = ss.word(0x80095250), ss.word(0x800970D8)
                dv = (v - state["a"]) & 0xFFFFFFFF
                series.append((round(dv / (now - state["t"]) / 59.94 * 100), round(((f - state["f"]) & 0xFFFFFFFF) / max(dv, 1) * 59.94, 1)))
                state.update(a=v, f=f, t=now)
            return now >= t_end
        while not tick(s):
            time.sleep(0.5)
        s.record("series", detail="EMU %%/FPS per 4 s: %s" % series)
        tail = series[len(series) // 2:]
        s.record("second_half", detail="EMU avg %.1f, FPS avg %.1f" % (sum(e for e, _ in tail) / max(len(tail), 1),
                                                                         sum(f for _, f in tail) / max(len(tail), 1)))
    finally:
        if hog:
            hog.kill()
    logs = sorted(glob.glob(str(s.copy_dir / "dev" / "logs" / "*.log")), key=os.path.getmtime)
    if logs:
        lines = [l.strip() for l in open(logs[-1], encoding="utf-8", errors="replace") if "emulation" in l or "Extra draw CPU" in l]
        s.record("guard", detail="%d lines: %s" % (len(lines), " | ".join(l.replace("driver.personal: ", "") for l in lines)[:1500]))
