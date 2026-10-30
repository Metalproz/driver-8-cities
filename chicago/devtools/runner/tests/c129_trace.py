"""C129 phase 2: Driver 2 traffic lanes (host-side civ-AI core, CHI_C129=1). CITY (default vegas) Take a Ride, the level
starts at START (D2 x,z,rot; default a Las Vegas 45-degree boulevard, straight 0xC9); the player stays parked while every
AI record / car is sampled at ~10 Hz for SECS (default 60): records in state 10 = cars the core drives. Trace CSV
(t, frame, slot, x, z, heading from the car matrix) -> chicago/c129/lanecheck.py with the package's c129_roads.bin:
within 256 (D2 units) of a D2 lane centre line, heading within 64/4096 (<= 3 % may exceed, as D2's own path does), no
axis heading on diagonals / curves, speed <= the road's limit. Also: cars attached, every driven car moves (no stall),
alive. CITY=miami: no record ever in state 10 (Driver 1 traffic untouched)."""
import csv, glob, math, os, struct, subprocess, sys, time

from runner.session import CARS, CAR_SIZE, AI_REC

CITY = os.environ.get("CITY", "vegas")
SECS = float(os.environ.get("SECS", "60"))
START = os.environ.get("START", "-102900,414665")   # beside the 45-degree boulevard 0xC9 (10 lanes)
os.environ.setdefault("CHI_C129", "1")
if CITY != "miami":
    os.environ.setdefault("CHI_START_%s" % CITY.upper(), START)
SESSION = dict(day="var_polish_chi8_day.lev", night="var_polish_chi8_night.lev", s4=True)
C129 = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", "c129")


def run(s):
    s.menu("take_a_ride/%s" % CITY); s.wait_world(what=CITY)
    rows, moved, first, st10 = [], {}, {}, 0
    t0 = time.time()
    while time.time() - t0 < SECS:
        rec = s.d.ram(AI_REC, 0x50 * 22)
        raw = s.d.ram(CARS, CAR_SIZE * 23)
        fc = s.word(0x800970D8)
        for i in range(22):
            if rec[0x50 * i + 1] != 10:
                continue
            st10 += 1
            cid = rec[0x50 * i] + 1
            o = CAR_SIZE * cid
            x, y, z = struct.unpack_from("<3i", raw, o + 0x18)
            m02, m22 = struct.unpack_from("<h", raw, o + 8)[0], struct.unpack_from("<h", raw, o + 20)[0]
            h = int(round(math.atan2(m02, m22) * 4096 / (2 * math.pi))) & 4095
            rows.append((round(time.time() - t0, 2), fc, i, x, z, h))
            if i in first:
                moved[i] = max(moved.get(i, 0), math.hypot(x - first[i][0], z - first[i][1]))
            else:
                first[i] = (x, z)
        time.sleep(0.1)
    out = s.dir / "c129_trace.csv"
    with open(out, "w", newline="") as f:
        w = csv.writer(f); w.writerow(["t", "frame", "slot", "x", "z", "heading"]); w.writerows(rows)
    s.record("trace", detail="%d samples, %d cars driven by the D2 core -> %s" % (len(rows), len(first), out.name))
    if CITY == "miami":
        s.check("Driver 1 city: no record in state 10", st10 == 0, "%d" % st10)
        s.check("alive", s.alive()); return
    s.check("cars driven by the D2 core", len(first) >= 3, "%d cars" % len(first))
    stuck = [i for i, d in moved.items() if d < 500]
    s.check("no stalled D2-driven car (each moved >= 500)", not stuck, "stalled slots %s" % stuck)
    roads = sorted(glob.glob(str(s.copy_dir / "mods" / "packages" / "driver.chicago" / "*" / "assets" / "**" / "c129_roads.bin"), recursive=True))
    roads = [r for r in roads if os.sep + CITY in r or "/" + CITY in r.replace("\\", "/")] or roads
    if not roads:
        s.check("package carries c129_roads.bin", False, "none under the copy's package"); return
    p = subprocess.run([sys.executable, os.path.join(C129, "lanecheck.py"), roads[0], str(out)], capture_output=True, text=True)
    (s.dir / "lanecheck.txt").write_text(p.stdout + p.stderr)
    s.record("lanecheck", detail=(p.stdout.strip().splitlines() or ["?"])[-1])
    s.check("D2 lanes (lanecheck)", p.returncode == 0, (p.stdout.strip().splitlines() or ["?"])[-1][:160])
    log = (s.dir / "game.log").read_text(encoding="utf-8", errors="replace") if (s.dir / "game.log").exists() else ""
    if not log:
        logs = sorted(glob.glob(str(s.copy_dir / "dev" / "logs" / "*.log")), key=os.path.getmtime)
        log = open(logs[-1], encoding="utf-8", errors="replace").read() if logs else ""
    s.record("log", detail=" | ".join(l.split("driver.chicago: ")[-1] for l in log.splitlines() if "C129" in l)[-600:])
    s.check("alive", s.alive())
