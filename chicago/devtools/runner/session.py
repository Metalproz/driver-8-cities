"""runner.session - one game instance on a test copy, driven like a browser page (Q42, Infrastructure 23.10.).

Test-copy only: dt.prepare + dt.launch (devtest/<copy>, own memory cards, own debug port, BELOW_NORMAL); never build-dev
or build-release. The process is stopped by its PID only. Every step goes to <run dir>/steps.jsonl; the console gets one
short line per step (capped), screenshots / WAVs / dumps stay on disk.
"""
from __future__ import annotations

import glob, json, math, os, shutil, struct, sys, time, wave
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE.parent.parent))
import dt  # noqa: E402

WORK = dt.CHI / "work"
RUNS = dt.OUT / "runner"

# game addresses (Driver 1, see chicago/NOTES.md)
CITY, MISSION, NIGHT = 0x80096834, 0x80096808, 0x80096850
AREA, LOADING, VSYNC, REGION = 0x800972C0, 0x800969E8, 0x80095250, 0x8009732C
CARS, CAR_SIZE, AI_REC = 0x8009B0A4, 0x18C, 0x80098950
BTN = dt.BTN

BASE_STATE = """format_version = 2

[[package]]
id = "driver.chicago"
version = "0.1.0"

[[package]]
id = "driver.personal"
version = "1.0.0"

[[feature]]
package_id = "driver.personal"
id = "skip-intro"
enabled = true

[[feature]]
package_id = "driver.personal"
id = "unlock-all"
enabled = true

[[feature]]
package_id = "driver.chicago"
id = "model-table"
enabled = true

[[feature]]
package_id = "driver.chicago"
id = "chicago-slot"
enabled = true
values = { city = "la", menu = "pages" }
"""


class StepFailed(AssertionError):
    pass


class Session:
    """with Session("bus_head_on", day="var_polish_opt2d_day.lev", ...) as s: s.menu("take_a_ride/chicago") ..."""

    def __init__(self, test: str, day: str = "var_polish_opt2d_day.lev", night: str | None = "var_polish_opt2d_night.lev",
                 copy: str = "runner", port: int = 4468, build: str = "build-test", s4: bool = True, dev_mode: bool = True,
                 env: dict | None = None, out: str | None = None, quiet: bool = False, reuse: bool = False, start=None):
        self.test, self.copy, self.port, self.build = test, copy, port, build
        self.day = str(WORK / day) if not os.path.isabs(day) else day
        self.night = (str(WORK / night) if night and not os.path.isabs(night) else night)
        self.s4, self.dev_mode, self.env, self.quiet, self.reuse = s4, dev_mode, dict(env or {}), quiet, reuse
        self.start_d2 = start            # (x, z) Driver 2 coords: the level STARTS there (package start)
        self.dir = Path(out) if out else RUNS / ("%s-%s" % (time.strftime("%Y%m%d-%H%M%S"), test))
        self.dir.mkdir(parents=True, exist_ok=True)
        self.pose_file = self.dir / "pose.txt"
        self.steps, self.checks, self.p, self.d, self.t0 = [], [], None, None, time.time()
        self._log = open(self.dir / "steps.jsonl", "w", encoding="utf-8")
        self._printed = 0

    # --- lifecycle -------------------------------------------------------------------------------------------------
    def __enter__(self):
        self.start()
        return self

    def __exit__(self, et, ev, tb):
        if et is not None:
            self.record("error", ok=False, detail="%s: %s" % (et.__name__, ev))
            try:
                self.screenshot("on_error")
            except Exception:
                pass
        self.stop()
        return False

    def start(self):
        os.environ.update({"CHI_TEST_BUILD": self.build, "CHI_SLOT": "1", "CHI_MENU_PAGES": "1",
                           "CHI_TEST_POSE": str(self.pose_file), **self.env})
        if self.night:
            os.environ["CHI_NIGHT"] = self.night
        dt.BUILD = self.build
        if self.reuse:                     # an exact copy prepared elsewhere (ship pre-check): exe, package, state as they are
            d0 = dt.TEST / self.copy
        else:
            d0 = dt.prepare(self.copy, self.start_d2, self.day)
            st = BASE_STATE
            if self.dev_mode:
                st += '\n[[feature]]\npackage_id = "driver.personal"\nid = "dev-mode"\nenabled = true\n'
            if os.environ.get("RUNNER_XDRAW"):           # C94: "Extra draw distance"
                st += '\n[[feature]]\npackage_id = "driver.personal"\nid = "extra-draw"\nenabled = true\n'
            if os.environ.get("RUNNER_UNCAP"):           # C92: "Uncap GPU usage" at RUNNER_UNCAP % CPU
                st += ('\n[[feature]]\npackage_id = "driver.personal"\nid = "uncap-gpu"\nenabled = true\n'
                       'values = { cpu_percent = %d }\n' % int(os.environ["RUNNER_UNCAP"]))
            (d0 / "mods" / "state.toml").write_text(st, encoding="utf-8")
            # RUNNER_SETTINGS="key=value;key=value": settings.toml overrides in the copy (host-speed profiling)
            sf = d0 / "settings.toml"
            if sf.exists():
                import re as _re
                txt = sf.read_text(encoding="utf-8")   # dt.prepare wrote build-dev's settings (minus memcards) just now
                for kv in filter(None, os.environ.get("RUNNER_SETTINGS", "").split(";")):
                    k, v = kv.split("=", 1)
                    txt, n = _re.subn(r"(?m)^(%s\s*=\s*).*$" % _re.escape(k.strip()), lambda m: m.group(1) + v.strip(), txt)
                    if not n:
                        raise SystemExit("RUNNER_SETTINGS: %s not in settings.toml" % k)
                sf.write_text(txt, encoding="utf-8")
            flag = d0 / "chi_s4.flag"
            if self.s4:
                flag.write_text("1")
            elif flag.exists():
                flag.unlink()
        self.copy_dir = d0
        self.dumps_before = set(glob.glob(str(d0 / "dev" / "dumps" / "*")))
        self.p, self.d = dt.launch(self.copy, self.port)
        self.record("launch", detail="copy %s port %d pid %d build %s s4 %s" % (self.copy, self.port, self.p.pid, self.build, self.s4))
        self.wait_for(lambda: (self.d.frame() or 0) >= 2300, 120, "boot")

    def stop(self):
        if self.p is not None and self.p.poll() is None:
            self.p.kill()                    # by PID (our own Popen), never by image name
            time.sleep(1)
        self.new_dumps = sorted(set(glob.glob(str(self.copy_dir / "dev" / "dumps" / "*"))) - self.dumps_before) \
            if hasattr(self, "copy_dir") else []
        crash = getattr(self, "copy_dir", None) and self.copy_dir / "psx_crash.txt"
        if crash and crash.exists() and crash.stat().st_mtime > self.t0:
            self.record("crash", ok=False, detail=crash.read_text(errors="replace")[:300])
        stalls = [x for x in self.new_dumps if x.endswith("-stall")]      # watchdog fired, game recovered (FMV)
        self.new_dumps = [x for x in self.new_dumps if x not in stalls]
        if stalls:
            self.record("stalls", detail="recovered watchdog snapshots: " + " ".join(Path(x).name for x in stalls))
        if self.new_dumps:
            self.record("dumps", ok=False, detail=" ".join(self.new_dumps))
        if hasattr(self, "copy_dir"):
            logs = sorted(glob.glob(str(self.copy_dir / "dev" / "logs" / "*.log")), key=os.path.getmtime)
            src = Path(logs[-1]) if logs and os.path.getmtime(logs[-1]) > self.t0 else self.copy_dir / "run.log"
            if src.exists():
                shutil.copy2(src, self.dir / "game.log")       # dev-mode sends stdout to dev/logs
        self._log.close()

    # --- recording -------------------------------------------------------------------------------------------------
    def record(self, step, ok=True, detail="", **data):
        e = {"t": round(time.time() - self.t0, 2), "step": step, "ok": ok, "detail": detail, **data}
        self.steps.append(e)
        self._log.write(json.dumps(e) + "\n"); self._log.flush()
        if not self.quiet and self._printed < 60:
            print("  %6.1fs %-4s %s %s" % (e["t"], "ok" if ok else "FAIL", step, str(detail)[:110]), flush=True)
            self._printed += 1
        return e

    def check(self, name, cond, detail=""):
        self.checks.append({"name": name, "ok": bool(cond), "detail": detail})
        self.record("check:" + name, ok=bool(cond), detail=detail)
        return bool(cond)

    # --- reading ---------------------------------------------------------------------------------------------------
    def word(self, a):
        return self.d.word(a)

    def ram(self, a, n):
        return self.d.ram(a, n)

    def poke32(self, a, v):
        for k, b in enumerate(struct.pack("<I", v & 0xFFFFFFFF)):
            self.d.cmd("write_ram", addr="0x%08X" % (a + k), val=b)
        self.record("poke", detail="%08x = %08x (readback %08x)" % (a, v, self.word(a)))

    def pos(self):
        return tuple(self.d.pos())

    def car(self, i):
        """(x, y, z, heading rad, damage) of car slot i (0 = player)."""
        raw = self.d.ram(CARS + i * CAR_SIZE, 0x180)
        x, y, z = struct.unpack_from("<3i", raw, 0x18)
        fx, fz = struct.unpack_from("<h", raw, 8)[0], struct.unpack_from("<h", raw, 20)[0]
        return x, y, z, math.atan2(fx, fz), struct.unpack_from("<H", raw, 0x17C)[0]

    def find_model(self, model):
        rec = self.d.ram(AI_REC, 0x50 * 22)
        for i in range(22):
            if rec[i * 0x50 + 0x10] == model:
                x, y, z, h, _ = self.car(i + 1)
                if (x, y, z) != (0, 0, 0):
                    return i + 1
        return None

    def in_level(self):
        return self.pos() != (0, 0, 0)

    # --- waiting ---------------------------------------------------------------------------------------------------
    def wait_for(self, pred, timeout, what, poll=0.25, fail=True):
        t = time.time()
        while time.time() - t < timeout:
            try:
                if pred():
                    self.record("wait", detail="%s (%.1fs)" % (what, time.time() - t))
                    return True
            except (OSError, ConnectionError):
                pass
            if self.p.poll() is not None:
                raise StepFailed("game exited while waiting for %s" % what)
            time.sleep(poll)
        self.record("wait", ok=False, detail="%s: timeout %ds" % (what, timeout))
        if fail:
            raise StepFailed("timeout waiting for " + what)
        return False

    def perf(self, secs=5.0):
        """(FPS, GP0 packets per game frame) over secs: game frames = word 0x800970D8 (PHASE), VBlanks = 0x80095250
        (research_fps.md method); packets from the runtime's GP0 ring counter (gpu_ring_stats total)."""
        p0, v0, g0 = self.word(0x800970D8), self.word(VSYNC), int(self.d.cmd("gpu_ring_stats").get("total", 0))
        time.sleep(secs)
        p1, v1, g1 = self.word(0x800970D8), self.word(VSYNC), int(self.d.cmd("gpu_ring_stats").get("total", 0))
        frames, vbl = (p1 - p0) & 0xFFFFFFFF, (v1 - v0) & 0xFFFFFFFF
        return (round(frames / vbl * 59.94, 1) if vbl else 0.0), (round((g1 - g0) / frames) if frames else 0)

    def alive(self, secs=3.0):
        a = self.word(VSYNC); time.sleep(secs); return self.word(VSYNC) != a

    # --- input -----------------------------------------------------------------------------------------------------
    def press(self, *buttons, hold=0.12, gap=0.8):
        self.d.press(*buttons, hold=hold, gap=gap)

    def hold(self, *buttons):
        m = 0xFFFF
        for b in buttons:
            m &= ~(1 << BTN[b])
        self.d.cmd("set_input", buttons="0x%04X" % m)

    def release(self):
        self.d.cmd("set_input", buttons="0xFFFF")

    def menu(self, path: str):
        """Named navigation from the title screen (pages menu, quick-city-select off):
        take_a_ride/<miami|frisco|la|ny|newtown|interview|desert|chicago|havana|vegas|rio>[/night], undercover/new_game."""
        parts = path.split("/")
        self.press("triangle"); time.sleep(2)
        if parts[0] == "undercover":
            self.press("cross"); time.sleep(2); self.press("cross")
            t = time.time()
            while time.time() - t < 150 and not self.in_level():   # intro FMV: start skips it
                time.sleep(9); self.press("start", gap=0.5)
            self.record("menu", ok=self.in_level(), detail=path)
            return
        rows = {"miami": 0, "frisco": 1, "la": 2, "ny": 3, "newtown": 4, "interview": 5, "desert": 6}
        for b in ["right"] * 5 + ["cross"]:
            self.press(b)
        time.sleep(1.5)
        city = parts[1]
        d2rows = {"chicago": 0, "havana": 1, "vegas": 2, "rio": 3}
        if city in d2rows:                           # page 2 "Driver 2 cities": Chicago, Havana, Las Vegas, Rio (M3)
            for _ in range(7):
                self.press("down", gap=0.6)
            self.press("cross", gap=1.0); time.sleep(1)
            for _ in range(d2rows[city]):
                self.press("down", gap=0.8)
            self.press("cross"); time.sleep(3)
        else:
            for _ in range(rows[city]):
                self.press("down", gap=0.6)
            self.press("cross"); time.sleep(3)
        if len(parts) > 2 and parts[2] == "night":
            self.press("down")
        self.press("cross")
        self.wait_for(self.in_level, 120, "in level (%s)" % path)
        time.sleep(3)
        self.record("menu", detail="%s city %d" % (path, self.word(CITY)))

    def _write_pose(self, x, y, z, heading):
        tmp = str(self.pose_file) + ".t"
        open(tmp, "w").write("%d %d %d %d" % (x, y, z, int(round(heading * 4096 / (2 * math.pi))) & 4095))
        for _ in range(50):
            try:
                os.replace(tmp, self.pose_file); break
            except PermissionError:
                time.sleep(0.02)

    def _release_pose(self):
        for _ in range(50):
            try:
                os.remove(self.pose_file); break
            except FileNotFoundError:
                break
            except PermissionError:
                time.sleep(0.02)

    def wait_world(self, timeout=45.0, stable_s=1.5, what="world loaded"):
        """The world around the car is loaded and drawn: no area load running (0x800969E8), the region (0x8009732C)
        unchanged and NO CD sector read for stable_s (the region / texture / model spooling has finished). A plain
        'loading flag = 0' check returns at once after a teleport, before the spool even starts (the old bug: white /
        grey ground, invalid screenshots and FPS). Fails loudly."""
        t = time.time(); last = None; since = None
        while time.time() - t < timeout:
            try:
                total = self.d.cmd("cdrom_sector_history", count=1).get("total")
            except Exception:
                total = None
            state = (total, self.word(REGION), self.word(LOADING))
            if state == last and not state[2]:
                since = since or time.time()
                if time.time() - since >= stable_s:
                    self.record("wait", detail="%s (%.1fs, %s sectors read)" % (what, time.time() - t, total))
                    return True
            else:
                since = None
            last = state
            if self.p.poll() is not None:
                raise StepFailed("game exited while waiting for " + what)
            time.sleep(0.25)
        self.record("wait", ok=False, detail="%s: not settled after %ds" % (what, timeout))
        raise StepFailed("world not loaded after %ds (%s)" % (timeout, what))

    def region_areas(self):
        """(region, its area byte or the border list's areas, loaded area). Driver 1 (CheckLoadAreaData 0x80033F9C):
        spool info = *0x80097254 + offsets(*0x800972AC)[region]; byte +8 = the region's area, 0xFF = border region whose
        +9 entries at +2.. (area | side << 6) switch only near the region's edge."""
        reg = self.word(REGION)
        info, offs = self.word(0x80097254), self.word(0x800972AC)
        off = int.from_bytes(self.ram(offs + reg * 2, 2), "little")
        rec = self.ram(info + off, 2 + 64)
        area, n = rec[8], rec[9]
        areas = [area] if area != 0xFF else sorted({b & 0x3F for b in rec[2:2 + n]})
        return reg, areas, self.word(AREA)

    def ensure_area(self, timeout=40.0):
        """After a teleport the loaded area (textures / models) can belong to the old place: Driver 1 switches areas only
        when the car crosses a border region's edge. A plain region: force its load (old_region = -1 = the level-start
        path of CheckLoadAreaData) and wait; a border region whose areas do not include the loaded one: fail."""
        reg, areas, loaded = self.region_areas()
        if loaded in areas:
            return True
        if len(areas) == 1:
            for k, b in enumerate((0xFFFFFFFF).to_bytes(4, "little")):
                self.d.cmd("write_ram", addr="0x%08X" % (0x80097324 + k), val=b)   # old_region = -1
            t = time.time()
            while time.time() - t < timeout:
                if self.word(AREA) == areas[0] and not self.word(LOADING):
                    self.record("wait", detail="area %d loaded for region %d (%.1fs)" % (areas[0], reg, time.time() - t))
                    return self.wait_world(what="world after area load")
                time.sleep(0.25)
        self.record("wait", ok=False, detail="region %d needs area %s, area %d is loaded" % (reg, areas, loaded))
        raise StepFailed("teleport target's area not loaded (region %d needs %s, loaded %d): start at the spot instead"
                         % (reg, areas, loaded))

    def pose(self, x, z, heading, y=None, settle=2.0, ground=True):
        """Teleport the player (plugin test pose, any city; test copies only): hold the car there until the world around it is
        loaded and drawn (wait_world), then release it. ground=True: if the car then drops / rises by more than 200
        (the pose y was not the ground's), it is posed again at the height it landed on and repaired. This is a
        TELEPORT: the menu's start position is not moved. To start a level AT a spot, use the package start
        (dt.prepare(name, d2_start, ...) / CHI_START) instead."""
        # M3 (Polish 27.10., RAM dump): after a long teleport the target region's road / height table slot (barrel) can
        # keep the start region's data (cars standing on 'water', lifts, white ground). A pose more than one region
        # (90000) away goes to a point one region short of the target first, so the target region is loaded the way
        # driving loads it. Not a guarantee (Polish: one region stayed stale even so); spots that matter get a second
        # pose or a drive-in (havana_sea_trace / havana_water_p).
        here = self.pos()
        if abs(x - here[0]) > 90000 or abs(z - here[2]) > 90000:
            sx = x - 90000 if x > here[0] else x + 90000
            self._write_pose(sx, here[1] if y is None else y, z, heading)
            time.sleep(1.0)
            self.wait_world(what="world one region before %d %d" % (x, z))
            # (28.10., Polish: a waypoint over water / void drowned the car once released) the car stays held: the
            # pose moves straight on to the target
        y = self.pos()[1] if y is None else y
        self._write_pose(x, y, z, heading)
        time.sleep(1.0)
        self.wait_world(what="world after pose %d %d" % (x, z))
        self.ensure_area()
        time.sleep(settle)
        self._release_pose()
        if ground:
            time.sleep(1.5)
            y1 = self.pos()[1]
            if abs(y1 - y) > 200:
                self._write_pose(x, y1 - 40, z, heading)
                for k, b in enumerate(struct.pack("<I", 0)):
                    self.d.cmd("write_ram", addr="0x%08X" % (0x8009B220 + k), val=b)   # repair (DAMAGE)
                time.sleep(1.0)
                self.wait_world(what="world after re-pose at ground %d" % y1)
                self._release_pose()
                time.sleep(1.0)
                self.record("pose", detail="re-posed at the ground: y %d -> %d" % (y, y1 - 40))
        self.record("pose", detail="%d %d heading %.0f deg, y %d" % (x, z, math.degrees(heading), self.pos()[1]))

    def drive(self, secs, want=None, on_tick=None):
        """Throttle; with `want` (rad) hold that heading, reverse when stuck. on_tick(s) -> True stops."""
        t = time.time(); last = self.pos(); stuck = rev = 0
        while time.time() - t < secs:
            p = self.pos(); mvx, mvz = p[0] - last[0], p[2] - last[2]; spd = math.hypot(mvx, mvz); last = p
            stuck = stuck + 1 if spd < 30 else 0
            m = 0xFFFF & ~(1 << BTN["cross"])
            if rev:
                m = 0xFFFF & ~(1 << BTN["square"]); rev -= 1
            elif stuck > 8:
                rev = 6; stuck = 0
            elif want is not None and spd > 40:
                err = (math.atan2(mvx, mvz) - want + math.pi) % (2 * math.pi) - math.pi
                if abs(err) > math.radians(8):
                    m &= ~(1 << BTN["left" if err > 0 else "right"])
            self.d.cmd("set_input", buttons="0x%04X" % m)
            if on_tick and on_tick(self):
                break
            time.sleep(0.25)
        self.release()

    # --- capture ---------------------------------------------------------------------------------------------------
    def screenshot(self, name, baseline: str | None = None, tol: float = 12.0, mask=None):
        path = self.dir / ("%s.png" % name)
        self.d.shot(str(path))
        e = self.record("screenshot", detail=str(path))
        if baseline:
            score = image_diff(path, baseline, mask)
            self.check("image:" + name, score <= tol, "mean abs diff %.1f (tol %.1f) vs %s" % (score, tol, baseline))
        return path

    def audio(self, name, secs=5.0, tap=0):
        """The last `secs` of the game's audio (tap 0 = SPU out, 3 = SPU voices) -> WAV + metrics."""
        time.sleep(secs)
        st = self.d.cmd("audio_stats")
        frames = int(st["taps"][0]["frames"]) if tap in (0, 3) else int(st["taps"][min(tap, 2)]["frames"])
        n = int(secs * 44100)
        path = self.dir / ("%s.wav" % name)
        r = self.d.cmd("audio_wav", path=str(path), tap=tap, start=str(max(0, frames - n)), count=str(n))
        m = wav_metrics(path) if path.exists() else {}
        self.record("audio", ok=bool(r.get("ok")) and path.exists(), detail="%s %s" % (path.name, m), metrics=m)
        return path, m


def image_diff(a, b, mask=None) -> float:
    import numpy as np
    from PIL import Image
    x = np.asarray(Image.open(a).convert("RGB"), dtype=np.int16)
    y = np.asarray(Image.open(b).convert("RGB").resize((x.shape[1], x.shape[0])), dtype=np.int16)
    d = np.abs(x - y).mean(axis=2)
    if mask:                                     # [(x0, y0, x1, y1), ...] ignored rectangles
        for x0, y0, x1, y1 in mask:
            d[y0:y1, x0:x1] = 0
    return float(d.mean())


def wav_metrics(path) -> dict:
    """RMS, peak, clicks (sample steps above 4 x the 99.9th percentile step), silent stretches (> 50 ms)."""
    import numpy as np
    with wave.open(str(path)) as w:
        ch, rate, n = w.getnchannels(), w.getframerate(), w.getnframes()
        a = np.frombuffer(w.readframes(n), dtype=np.int16).reshape(-1, ch).astype(np.int32)
    mono = a.mean(axis=1)
    if len(mono) < 2:
        return {"frames": int(len(mono))}
    step = np.abs(np.diff(mono)); p999 = float(np.percentile(step, 99.9)) or 1.0
    clicks = int((step > 4 * p999).sum())
    silent = np.abs(mono) < 8
    runs, cur, longest = 0, 0, 0
    for s in silent[:: max(1, rate // 1000)]:          # 1 ms resolution
        cur = cur + 1 if s else 0
        if cur == 50: runs += 1
        longest = max(longest, cur)
    return {"secs": round(len(mono) / rate, 2), "rms": round(float(np.sqrt((mono ** 2).mean())), 1),
            "peak": int(np.abs(mono).max()), "clicks": clicks, "silences_50ms": runs, "longest_silence_ms": longest}
