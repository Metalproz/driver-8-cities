"""dt.py - Chicago port dev tools. All heavy work runs locally; output is compact.

    python dt.py snaps [--since YYYYMMDD-HHMMSS]     summarize user snapshots (+ contact sheet)
    python dt.py live [--port 4370]                  inspect a running/frozen game, save dumps
    python dt.py spots [names...] [--cams]           capture known issue spots in parallel
    python dt.py soak [--spot NAME] [--steps N] [--seed S] [--n K]   random-drive soaks in parallel
    python dt.py addspot NAME D1X D1Z "note"         register an issue spot (D1 coords from a snapshot)
    python dt.py dis START [END] [--orig]            disassemble the game EXE (patched by default)

Tests never use build-dev (the user's dev client) or build-release: each run
uses a copy under <app>/devtest/<name> (exe refreshed from build-dev), its own
memory cards and debug port. Results: devtest/_out/<run>/ (summary.txt, sheet.png).
"""
from __future__ import annotations

import glob, json, math, os, random, shutil, socket, struct, subprocess, sys, time
from pathlib import Path

HERE = Path(__file__).resolve().parent
CHI = HERE.parent
APP = CHI.parent.parent
TEST = APP / "devtest"
OUT = TEST / "_out"
sys.path.insert(0, str(CHI))
sys.path.insert(0, str(HERE / "_pylib"))

# --- game addresses -----------------------------------------------------------
POS = 0x8009B0BC          # player x, y, z (i32)
AREA, REGION, LOADING = 0x800972C0, 0x8009732C, 0x800969E8
BUILD = os.environ.get("CHI_TEST_BUILD", "build-dev")   # exe/packages the test copies come from
SPOOL_LEFT = 0x800971F8                  # spool sectors still to read
DRAWBUF = 0x80097530      # current draw buffer struct (primptr, ot, base)
VCOUNT = 0x80095250       # libetc VSync counter
CITY, CHICAGO_CITY = 0x80096834, 3   # current city; Chicago replaces Los Angeles (3)
MODEL_TABLE, MODEL_ENTRIES = 0x9F000000, 2048
FEATURES = [("driver.personal", "skip-intro"), ("driver.personal", "unlock-all"),
            ("driver.chicago", "model-table"), ("driver.chicago", "chicago-la")]
COPY = ["Driver_Recompiled.exe", "_deps", "assets", "bios", "bios.cfg", "disc.cfg", "game.toml",
        "game_options.toml", "psx_game_version.txt", "psxrecomp_exe_name-psx-runtime.txt"]
BTN = {"select": 0, "l3": 1, "r3": 2, "start": 3, "up": 4, "right": 5, "down": 6, "left": 7,
       "l2": 8, "r2": 9, "l1": 10, "r1": 11, "triangle": 12, "circle": 13, "cross": 14, "square": 15}
SPOTS_FILE = HERE / "spots.json"


# --- debug server client ------------------------------------------------------
class Dbg:
    """psxrecomp TCP debug server: one compact-JSON request per connection."""

    def __init__(self, port=4370, timeout=30):
        self.port, self.n = port, 0
        end = time.time() + timeout
        while True:
            try:
                if self.cmd("ping").get("ok"):
                    return
            except OSError:
                pass
            if time.time() > end:
                raise TimeoutError("debug server %d not reachable" % port)
            time.sleep(0.3)

    def cmd(self, name, **kw):
        self.n += 1
        kw.update(id=self.n, cmd=name)
        with socket.create_connection(("127.0.0.1", self.port), timeout=40) as s:
            s.sendall((json.dumps(kw, separators=(",", ":")) + "\n").encode())
            buf = b""
            while not buf.endswith(b"\n"):
                c = s.recv(1 << 20)
                if not c:
                    break
                buf += c
        return json.loads(buf.decode().splitlines()[0])

    def frame(self):
        return self.cmd("frame").get("frame")

    def ram(self, addr, n):
        r = self.cmd("read_ram", addr="0x%08X" % addr, len=n)
        return bytes.fromhex(r["hex"]) if r.get("ok") else b""

    def word(self, addr):
        return int.from_bytes(self.ram(addr, 4), "little")

    def press(self, *names, hold=0.15, gap=0.25):
        mask = 0xFFFF
        for n in names:
            mask &= ~(1 << BTN[n])
        self.cmd("set_input", buttons="0x%04X" % mask)
        time.sleep(hold)
        self.cmd("clear_input")
        time.sleep(gap)

    def shot(self, path):
        return self.cmd("screenshot", path=str(path))

    def pos(self):
        return list(struct.unpack("<3i", self.ram(POS, 12)))

    def ram_all(self):
        return b"".join(self.ram(a, 0x10000) for a in range(0x80000000, 0x80200000, 0x10000))

    def mod_all(self):
        return b"".join(self.ram(MODEL_TABLE + k, 0x10000) for k in range(0, 0x90000, 0x10000))

    def vram(self):
        import numpy as np
        img = np.zeros((512, 1024), dtype=np.uint16)
        for y in range(0, 512, 128):
            for x in range(0, 1024, 128):
                h = self.cmd("vram_peek", x=x, y=y, w=128, h=128)["hex"]
                img[y:y + 128, x:x + 128] = np.frombuffer(bytes.fromhex(h), dtype=">u2").reshape(128, 128)
        return img


# --- level knowledge ----------------------------------------------------------
def spots():
    return json.loads(SPOTS_FILE.read_text()) if SPOTS_FILE.exists() else {}


def lev_path():
    return CHI / "work" / "chicago_d1.lev"


def model_sigs(lev=None):
    """model id -> [vertices, polygons, shape flags & ~4] of a converted level (cached)."""
    lev = Path(lev or lev_path())
    cache = TEST / "_cache" / ("sig_%d_%d.json" % (lev.stat().st_size, int(lev.stat().st_mtime)))
    if cache.exists():
        return {int(k): v for k, v in json.loads(cache.read_text()).items()}
    from levfile import Lev
    from models import inmem_models, area_models
    l = Lev.parse(lev.read_bytes())
    cmem, _ = inmem_models(l)
    from models import model_names
    from texrepack import ENGINE_MODEL_NAMES          # wheels etc.: changed by the game at runtime
    names = model_names(l)
    sig = {i: [m.num_vertices, m.num_polys, m.shape_flags & 0xFFFB] for i, m in {**area_models(l), **cmem}.items()
           if not (i < len(names) and names[i] in ENGINE_MODEL_NAMES)}
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps(sig))
    return sig


def copy_lev(name):
    """Level file a test copy was prepared with."""
    f = TEST / name / "lev.txt"
    return Path(f.read_text().strip()) if f.exists() else lev_path()


def table_check(ram: bytes, mod: bytes, sig=None):
    """Model table entries whose header does not match the converted level."""
    sig = sig or model_sigs()
    bad = []
    tab = struct.unpack_from("<%dI" % MODEL_ENTRIES, mod, 0)
    for i, p in enumerate(tab):
        if i not in sig or not p or p >> 24 == 0x9F:
            continue
        a = p & 0x1FFFFF
        if a + 0x10 > len(ram):
            bad.append((i, hex(p), "out of RAM")); continue
        fl, = struct.unpack_from("<H", ram, a)
        nv, npo = struct.unpack_from("<HH", ram, a + 0xC)
        if [nv, npo, fl & 0xFFFB] != sig[i]:
            bad.append((i, hex(p), (nv, npo, hex(fl))))
    return bad


def d2_of(x, z):
    import worldscale as ws
    return ws.to_d2(x, z)


def nearest_spot(x, z):
    best = None
    for n, s in spots().items():
        import worldscale as ws
        sx, sz = ws.to_d1(*s["d2"])
        d = ((sx - x) ** 2 + (sz - z) ** 2) ** 0.5
        if best is None or d < best[0]:
            best = (d, n)
    return "%s (%dk away)" % (best[1], best[0] // 1000) if best else "-"


# --- test copies ----------------------------------------------------------------
def write_state(d: Path, features):
    s = "format_version = 2\n"
    for p in sorted({p for p, _ in features}):
        s += '\n[[package]]\nid = "%s"\nversion = "%s"\n' % (p, "0.1.0" if p == "driver.chicago" else "1.0.0")
    for p, f in features:
        s += '\n[[feature]]\npackage_id = "%s"\nid = "%s"\nenabled = true\n' % (p, f)
    (d / "mods").mkdir(parents=True, exist_ok=True)
    (d / "mods" / "state.toml").write_text(s)


def build_package(start=None, lev=None, pkg_dir=None):
    """Package with a Driver 2 start / level file; pkg_dir: write into a test copy
    (CHI_PKG_DIR) so the preloaded package of the dev client is never touched."""
    env = dict(os.environ)
    env.pop("CHI_START", None); env.pop("CHI_PKG_DIR", None)
    if start:
        env["CHI_START"] = "%d,%d" % tuple(start)
    if pkg_dir:
        env["CHI_PKG_DIR"] = str(pkg_dir)
    subprocess.run([sys.executable, "build_package.py", "--test-bigmiami", "work/test_bigmiami.lev",
                    "--chicago", str(lev or lev_path())], cwd=CHI, env=env, check=True,
                   stdout=subprocess.DEVNULL)


def stable_exe():
    """build-dev's exe once it has not changed for 20 s (not mid-link)."""
    exe = APP / BUILD / "Driver_Recompiled.exe"
    while time.time() - exe.stat().st_mtime < 20:
        time.sleep(5)
    return exe


def prepare(name, start=None, lev=None):
    """Refresh devtest/<name> from build-dev; package with the given Driver 2 start."""
    stable_exe()
    lf = Path(lev or lev_path())
    while time.time() - lf.stat().st_mtime < 30:      # never copy a level that is being written
        time.sleep(5)
    d = TEST / name
    d.mkdir(parents=True, exist_ok=True)
    src = APP / BUILD
    for k in COPY:
        s, t = src / k, d / k
        if not s.exists():
            continue
        if s.is_dir():
            if not t.exists():
                shutil.copytree(s, t)
        elif not t.exists() or s.stat().st_mtime > t.stat().st_mtime or s.stat().st_size != t.stat().st_size:
            shutil.copy2(s, t)
    gt = (d / "game.toml").read_text(encoding="utf-8")
    base = str(APP).replace("\\", "/")
    for key in ('exe = "disc/', 'disc = "disc/'):
        gt = gt.replace(key, key.replace('"disc/', '"%s/disc/' % base))
    gt = gt.replace('out_dir = "disc"', 'out_dir = "%s/disc"' % base)
    (d / "game.toml").write_text(gt, encoding="utf-8")
    pk = d / "mods" / "packages"
    shutil.rmtree(pk, ignore_errors=True)
    shutil.copytree(src / "mods" / "packages", pk)
    shutil.rmtree(pk / "driver.chicago", ignore_errors=True)
    build_package(start, lev, pk / "driver.chicago" / "0.1.0")
    (d / "lev.txt").write_text(str(lev or lev_path()))
    write_state(d, FEATURES)
    return d


def launch(name, port):
    d = TEST / name
    log = open(d / "run.log", "w")
    p = subprocess.Popen([str(d / "Driver_Recompiled.exe"), "--headless", "--no-launcher",
                          "--memcard-dir", str(d / "cards"), "--debug-port", str(port)],
                         cwd=d, stdout=log, stderr=subprocess.STDOUT)
    time.sleep(3)
    return p, Dbg(port=port)


def to_take_a_ride(d: Dbg):
    while (d.frame() or 0) < 2300:
        time.sleep(0.1)
    for b in ["right"] * 5 + ["cross", "down", "down", "cross", "cross"]:
        d.press(b, hold=0.12, gap=0.8)
    time.sleep(35)


def poke(d: Dbg, pokes: dict):
    """{"0x80097148": value} -> 32-bit writes."""
    for a, v in (pokes or {}).items():
        for k, b in enumerate(struct.pack("<i", int(v, 0) if isinstance(v, str) else v)):
            d.cmd("write_ram", addr="0x%08X" % (int(a, 16) + k), val=b)


def alive(d: Dbg, span=0.6):
    seen, t = set(), time.time()
    while time.time() - t < span:
        seen.add(d.word(DRAWBUF)); time.sleep(0.05)
    return len(seen) > 1


def run_dir(tag):
    r = OUT / ("%s-%s" % (time.strftime("%m%d-%H%M%S"), tag))
    r.mkdir(parents=True, exist_ok=True)
    return r


def sheet(images, path, labels=None, cols=5, w=256, h=120):
    from PIL import Image, ImageDraw
    images = [i for i in images if Path(i).exists()]
    if not images:
        return
    rows = (len(images) + cols - 1) // cols
    out = Image.new("RGB", (cols * w, rows * h), (255, 0, 255))
    for k, f in enumerate(images):
        im = Image.open(f).convert("RGB").resize((w, h))
        if labels:
            ImageDraw.Draw(im).text((3, 3), labels[k], fill=(255, 0, 0))
        out.paste(im, ((k % cols) * w, (k // cols) * h))
    out.save(path)


# --- commands -------------------------------------------------------------------
FATAL_MARKS = ("FATAL", "FAIL-FAST", "starvation_watchdog", "unknown command", "aborting")


def fatal_of(name):
    """First fatal line of a test copy's run log, if any."""
    log = TEST / name / "run.log"
    if log.exists():
        for line in log.read_text(errors="replace").splitlines():
            if any(m in line for m in FATAL_MARKS):
                return line[:200]
    return None


def kernel_ok(d: Dbg):
    return d.ram(0x800000A0, 4) == bytes.fromhex("0000083c")


def cmd_capture(name, port, out, cams, pokes=None):
    """(worker) one spot: start view, camera modes, short drive, dumps."""
    out = Path(out); out.mkdir(parents=True, exist_ok=True)
    p, d = launch(name, port)
    info = {"spot": name}
    try:
        to_take_a_ride(d)
        poke(d, pokes)
        info.update(pos=d.pos(), area=d.word(AREA), region=d.word(REGION))
        d.shot(out / "start.png")
        json.dump(d.cmd("gpu_frame_dump", frame=d.frame() - 2, count=20000), open(out / "gpu.json", "w"))
        import numpy as np
        np.save(out / "vram.npy", d.vram())
        ram, mod = d.ram_all(), d.mod_all()
        (out / "ram.bin").write_bytes(ram); (out / "mod.bin").write_bytes(mod)
        info["table_bad"] = len(table_check(ram, mod, model_sigs(copy_lev(name))))
        for k in range(4):
            d.press("select", hold=0.12, gap=1.0)
            d.shot(out / ("cam%d.png" % k))
            if cams:
                json.dump(d.cmd("gpu_frame_dump", frame=d.frame() - 2, count=20000), open(out / ("gpu_cam%d.json" % k), "w"))
        for k, keys in enumerate((("cross",), ("cross", "left"), ("cross", "left"), ("cross", "right"), ("cross",))):
            d.press(*keys, hold=1.0, gap=0.0); time.sleep(1.0)
            d.shot(out / ("drive%d.png" % k))
        info.update(end_pos=d.pos(), end_area=d.word(AREA), alive=alive(d) or alive(d, 5.0), kernel_ok=kernel_ok(d))   # 0.6 s alone failed under load
    except Exception as e:
        info["error"] = repr(e)
    finally:
        p.kill()
        info["fatal"] = fatal_of(name)
        (out / "info.json").write_text(json.dumps(info))


def cmd_spots(names, cams):
    sp = spots()
    names = names or list(sp)
    run = run_dir("spots")
    for n in names:
        prepare("spot_" + n, sp[n]["d2"])
    procs = []
    for k, n in enumerate(names):
        procs.append(subprocess.Popen([sys.executable, __file__, "_capture", "spot_" + n, str(4380 + k),
                                       str(run / n)] + (["--cams"] if cams else [])))
        time.sleep(4)
    for p in procs:
        p.wait()
    lines, imgs, labels = [], [], []
    for n in names:
        i = json.loads((run / n / "info.json").read_text()) if (run / n / "info.json").exists() else {"error": "no info"}
        lines.append("%-12s area %-3s pos %s -> %s  table_bad %s  alive %s %s" % (
            n, i.get("area"), i.get("pos"), i.get("end_pos"), i.get("table_bad"), i.get("alive"), i.get("error", "")))
        for f in ("start", "cam0", "cam1", "cam2", "cam3", "drive0", "drive1", "drive2", "drive3", "drive4"):
            imgs.append(run / n / (f + ".png")); labels.append("%s %s" % (n, f))
    sheet(imgs, run / "sheet.png", labels)
    (run / "summary.txt").write_text("\n".join(lines))
    print("\n".join(lines)); print("sheet:", run / "sheet.png")


def cmd_soak_one(name, port, steps, seed, out, pokes=None):
    """(worker) random drive with unstick, model table check, hang detection."""
    out = Path(out); out.mkdir(parents=True, exist_ok=True)
    p, d = launch(name, port)
    res = {"seed": seed, "areas": [], "table_bad": [], "hang": None,
           "dist": 0, "area_loading_steps": 0, "spooling_steps": 0}     # CD activity per distance
    try:
        to_take_a_ride(d)
        poke(d, pokes)
        sig = model_sigs(copy_lev(name)); rnd = random.Random(seed)
        moves = [("cross", "left"), ("cross", "right"), ("cross",), ("cross",)]
        for k in range(steps):
            before = d.pos()
            d.press(*rnd.choice(moves), hold=rnd.choice((0.5, 1.0, 2.0)), gap=0.0)
            after = d.pos()
            if abs(after[0] - before[0]) + abs(after[2] - before[2]) < 1500:
                d.press("square", rnd.choice(("left", "right")), hold=1.5, gap=0.0)
            res["dist"] += int(math.hypot(after[0] - before[0], after[2] - before[2]))
            res["last_pos"] = after; res["region"] = d.word(REGION)
            res["area_loading_steps"] += bool(d.word(LOADING))
            res["spooling_steps"] += d.word(SPOOL_LEFT) > 0
            a = d.word(AREA)
            if not res["areas"] or res["areas"][-1] != a:
                res["areas"].append(a)
            bad = table_check(d.ram_all(), d.ram(MODEL_TABLE, MODEL_ENTRIES * 4) + bytes(0x90000), sig) if k % 5 == 0 else []
            if d.word(CITY) != CHICAGO_CITY:
                res["left_chicago"] = k                # menus after a wreck started another city
                break
            if bad:
                if not res["table_bad"]:              # keep evidence of the first detection
                    (out / "bad_ram.bin").write_bytes(d.ram_all()); (out / "bad_mod.bin").write_bytes(d.mod_all())
                    d.shot(out / "bad.png")
                    res["bad_state"] = {"area": d.word(AREA), "loading": d.word(LOADING), "mode": d.word(0x800967F4),
                                        "pos": d.pos(), "frame": d.frame()}
                res["table_bad"].append((k, bad[:4]))
            if k % 5 == 0 and not kernel_ok(d):
                res["kernel_bad_step"] = k
                break
            if not alive(d) and not alive(d, 5.0):
                r = d.cmd("get_registers")
                res["hang"] = {"step": k, "pos": d.pos(), "pc": r.get("pc"), "epc": r.get("cop0_epc")}
                d.shot(out / "hung.png")
                (out / "hung_ram.bin").write_bytes(d.ram_all()); (out / "hung_mod.bin").write_bytes(d.mod_all())
                break
        res["steps_done"] = k + 1
    except Exception as e:
        res["error"] = repr(e)
    finally:
        p.kill()
        res["fatal"] = fatal_of(name)
        (out / "result.json").write_text(json.dumps(res))


def cmd_soak(spot, steps, seed, n):
    run = run_dir("soak")
    start = spots()[spot]["d2"] if spot else None
    for k in range(n):
        prepare("soak%d" % k, start)
    procs = [subprocess.Popen([sys.executable, __file__, "_soak", "soak%d" % k, str(4390 + k), str(steps),
                               str(seed + k), str(run / ("s%d" % k))]) for k in range(n)]
    for p in procs:
        p.wait()
    lines = []
    for k in range(n):
        f = run / ("s%d" % k) / "result.json"
        r = json.loads(f.read_text()) if f.exists() else {"error": "no result"}
        lines.append("soak%d seed %s steps %s areas %s table_bad %d hang %s %s" % (
            k, r.get("seed"), r.get("steps_done"), r.get("areas"), len(r.get("table_bad", [])), r.get("hang"), r.get("error", "")))
    (run / "summary.txt").write_text("\n".join(lines)); print("\n".join(lines))


def cmd_snaps(since):
    dumps = sorted(glob.glob(str(APP / "dev" / "dumps" / "*")))
    dumps = [d for d in dumps if os.path.basename(d) > (since or "")]
    sig = model_sigs()
    run = run_dir("snaps")
    lines, imgs, labels = [], [], []
    for k, d in enumerate(dumps):
        d = Path(d)
        ram = (d / "ram.bin").read_bytes() if (d / "ram.bin").exists() else b""
        if len(ram) < 0x200000:
            continue
        x, y, z = struct.unpack_from("<3i", ram, POS & 0x1FFFFF)
        area, = struct.unpack_from("<i", ram, AREA & 0x1FFFFF)
        region, = struct.unpack_from("<i", ram, REGION & 0x1FFFFF)
        kern = "ok" if ram[0xA0:0xA4] == bytes.fromhex("0000083c") else "BAD"
        tb = "-"
        if (d / "mod.bin").exists():
            tb = len(table_check(ram, (d / "mod.bin").read_bytes(), sig))
        try:
            dx, dz = d2_of(x, z)
        except Exception:
            dx = dz = 0
        lines.append("%2d %s pos %d,%d d2 %d,%d area %d reg %d kernel %s table_bad %s near %s" % (
            k + 1, d.name, x, z, dx, dz, area, region, kern, tb, nearest_spot(x, z)))
        shot = d / "screen.png" if (d / "screen.png").exists() else d / "screen_native.png"
        imgs.append(shot); labels.append(str(k + 1))
    sheet(imgs, run / "sheet.png", labels, cols=4, w=320, h=240)
    (run / "summary.txt").write_text("\n".join(lines))
    print("\n".join(lines)); print("sheet:", run / "sheet.png")


def cmd_live(port):
    d = Dbg(port=port, timeout=8)
    run = run_dir("live")
    f0, v0 = d.frame(), d.word(VCOUNT); time.sleep(1.5)
    f1, v1 = d.frame(), d.word(VCOUNT)
    r = d.cmd("get_registers")
    ram, mod = d.ram_all(), d.mod_all()
    (run / "ram.bin").write_bytes(ram); (run / "mod.bin").write_bytes(mod)
    d.shot(run / "screen.png")
    g = d.cmd("gpu_frame_dump", frame=f1, count=20000)
    json.dump(g, open(run / "gpu.json", "w"))
    rep = APP / "psx_last_run_report.json"
    reason = ""
    if rep.exists() and time.time() - rep.stat().st_mtime < 3600:
        reason = json.loads(rep.read_text(encoding="utf-8", errors="replace")).get("reason", "")[:160]
    W = lambda a: struct.unpack_from("<I", ram, a & 0x1FFFFF)[0]
    pp, base = W(0x800BDFA4), W(0x800BDFA4 + 8)
    lines = [
        "frames %s -> %s  vsync %d -> %d  (%s)" % (f0, f1, v0, v1, "RUNNING" if f1 != f0 else "STOPPED"),
        "pc %s epc %s ra %s" % (r.get("pc"), r.get("cop0_epc"), r["gpr"][31]),
        "pos %s area %d region %d loading %d" % (list(struct.unpack_from("<3i", ram, POS & 0x1FFFFF)), W(AREA), W(REGION), W(LOADING)),
        "kernel %s  table_bad %d  primbuf0 used 0x%X (limit 0x1E000)" % (
            "ok" if ram[0xA0:0xA4] == bytes.fromhex("0000083c") else "BAD", len(table_check(ram, mod)), (pp - base) & 0xFFFFFF),
        "gpu entries %d  last report: %s" % (len(g.get("entries", [])), reason or "-"),
        "dumps: %s" % run,
    ]
    (run / "summary.txt").write_text("\n".join(lines)); print("\n".join(lines))


def cmd_addspot(name, x, z, note):
    sp = spots()
    sp[name] = {"d2": list(d2_of(int(x), int(z))), "note": note}
    SPOTS_FILE.write_text(json.dumps(sp, indent=1))
    print(name, sp[name])


def cmd_dis(start, end, orig):
    import capstone
    exe = (APP / "disc" / ("SLUS_008.42.orig" if orig else "SLUS_008.42")).read_bytes()
    base = struct.unpack_from("<I", exe, 0x18)[0]
    a, b = int(start, 16), int(end, 16) if end else int(start, 16) + 0x80
    md = capstone.Cs(capstone.CS_ARCH_MIPS, capstone.CS_MODE_MIPS32 + capstone.CS_MODE_LITTLE_ENDIAN)
    for addr in range(a, b, 4):
        o = 0x800 + (addr & 0x1FFFFFFF) - (base & 0x1FFFFFFF)
        got = list(md.disasm(exe[o:o + 4], addr))
        w = struct.unpack_from("<I", exe, o)[0]
        txt = "%-8s %s" % (got[0].mnemonic, got[0].op_str) if got else ("cop2 0x%08x" % w if w >> 25 == 0x25 else ".word 0x%08x" % w)
        if "($gp)" in txt:
            try:
                txt += "  ; gp -> %08X" % ((0x80096770 + int(txt.split(",")[-1].split("(")[0], 0)) & 0xFFFFFFFF)
            except ValueError:
                pass
        print("%08X: %s" % (addr, txt))


if __name__ == "__main__":
    a = sys.argv[1:]
    flag = lambda f, dflt=None: (a[a.index(f) + 1] if f in a else dflt)
    pos = [x for i, x in enumerate(a[1:], 1) if not x.startswith("--") and not (a[i - 1] in ("--since", "--port", "--spot", "--steps", "--seed", "--n"))]
    if not a:
        print(__doc__)
    elif a[0] == "snaps":
        cmd_snaps(flag("--since"))
    elif a[0] == "live":
        cmd_live(int(flag("--port", 4370)))
    elif a[0] == "spots":
        cmd_spots(pos, "--cams" in a)
    elif a[0] == "soak":
        cmd_soak(flag("--spot"), int(flag("--steps", 100)), int(flag("--seed", 1)), int(flag("--n", 4)))
    elif a[0] == "addspot":
        cmd_addspot(*pos[:4])
    elif a[0] == "dis":
        cmd_dis(pos[0], pos[1] if len(pos) > 1 else None, "--orig" in a)
    elif a[0] == "_capture":
        cmd_capture(a[1], int(a[2]), a[3], "--cams" in a)
    elif a[0] == "_soak":
        cmd_soak_one(a[1], int(a[2]), int(a[3]), int(a[4]), a[5])
    else:
        print(__doc__)
