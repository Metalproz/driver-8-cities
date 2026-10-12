"""lab.py - continuous background test lab for the Chicago port.

    python lab.py run [--slots 6] [--no-rotation]   start the lab (runs until stopped)
    python lab.py add KIND SPOT [key=value ...]      queue a job
    python lab.py status                             slots, queue, last events

Jobs (devtest/_lab/jobs/pending/*.json): {"kind": "capture"|"soak", "spot": NAME,
"experiment": "" (CHI_EXPERIMENT for a converter variant, cached as
work/var_<exp>.lev), "env": {"CHI_AREA_TEX": "200", ...} (more converter
settings), "pokes": {"0x80097148": 0}, "steps": 80, "seed": 1, "cams": false,
"prio": 5 (lower first), "note": ""}.

Idle slots soak the known issue spots (spots.json) with rotating seeds; a new
build-dev exe queues a capture of every spot (regression check). Only notable
results and finished queued jobs go to devtest/_lab/events.log (one line each).
Each slot is a test copy devtest/slot<k> on debug port 4400+k.

Health alert: when 3 jobs of one kind fail in a row, or more than half of the
jobs of the last 15 minutes (at least 4) fail, the lab appends a "LAB ALERT"
line to driver_personal/WORKLOG.md (the planning chat's hook shows it), logs
an event, and pauses the idle rotation; queued jobs still run. It resumes
(and logs "LAB OK") after 3 passing jobs in a row or a new build-dev exe.
"""
from __future__ import annotations

import hashlib, json, os, subprocess, sys, time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import dt

LAB = dt.TEST / "_lab"
JOBS = LAB / "jobs"
EVENTS = LAB / "events.log"
STATUS = LAB / "status.txt"
PORT0 = 4400
WORKLOG = dt.CHI.parent / "WORKLOG.md"


def event(msg):
    LAB.mkdir(parents=True, exist_ok=True)
    with open(EVENTS, "a", encoding="utf-8") as f:
        f.write("%s %s\n" % (time.strftime("%H:%M:%S"), msg))


def add_job(job: dict):
    for q in ("pending", "running", "done"):
        (JOBS / q).mkdir(parents=True, exist_ok=True)
    job.setdefault("prio", 5)
    jid = "%d_%s_%s_%s" % (job["prio"], time.strftime("%m%d%H%M%S"), job["kind"], job["spot"])
    jid += "_%04x" % (hash(json.dumps(job, sort_keys=True)) & 0xFFFF)
    job["id"] = jid
    (JOBS / "pending" / (jid + ".json")).write_text(json.dumps(job, indent=1))
    return jid


# --- converter variants ------------------------------------------------------------
def variant_lev(job) -> Path:
    exp, env = job.get("experiment", ""), job.get("env", {})
    if not exp and not env:
        return dt.lev_path()
    key = hashlib.md5(json.dumps([exp, env], sort_keys=True).encode()).hexdigest()[:10]
    out = dt.CHI / "work" / ("var_%s.lev" % key)
    src_time = max(p.stat().st_mtime for p in dt.CHI.glob("*.py"))
    lock = out.with_suffix(".lock")
    while lock.exists() and time.time() - lock.stat().st_mtime < 900:
        time.sleep(5)                          # another slot is building it
    if out.exists() and out.stat().st_mtime > src_time:
        return out
    lock.write_text(str(os.getpid()))
    try:
        e = dict(os.environ)
        e.pop("CHI_START", None)
        e["CHI_EXPERIMENT"] = exp
        e.update({k: str(v) for k, v in env.items()})
        r = subprocess.run([sys.executable, "convert.py", str(out)], cwd=dt.CHI, env=e,
                           capture_output=True, text=True)
        if r.returncode:
            raise RuntimeError("variant %s failed: %s" % (key, r.stderr.strip().splitlines()[-1:]))
        (out.with_suffix(".txt")).write_text(json.dumps([exp, env]))
    finally:
        lock.unlink(missing_ok=True)
    return out


# --- one job (worker process) --------------------------------------------------------
def run_job(path: Path, slot: int):
    job = json.loads(path.read_text())
    name, port = "slot%d" % slot, PORT0 + slot
    out = LAB / "results" / job["id"]
    out.mkdir(parents=True, exist_ok=True)
    res = {"job": job}
    try:
        lev = variant_lev(job)
        sp = dt.spots()[job["spot"]]
        dt.prepare(name, sp["d2"], lev)
        if job["kind"] == "capture":
            dt.cmd_capture(name, port, out, job.get("cams", False), job.get("pokes"))
            res["result"] = json.loads((out / "info.json").read_text())
        else:
            dt.cmd_soak_one(name, port, int(job.get("steps", 80)), int(job.get("seed", 1)), out, job.get("pokes"))
            res["result"] = json.loads((out / "result.json").read_text())
    except Exception as e:
        res["result"] = {"error": repr(e)}
    (out / "job.json").write_text(json.dumps(res, indent=1))
    notable = notables(res["result"])
    desc = job_desc(job)
    if notable or not job.get("auto"):
        event("%s %s: %s  [%s]" % ("!!" if notable else "ok", desc, "; ".join(notable) or "fine", out))
    path.rename(JOBS / "done" / path.name)


def job_desc(job):
    return "%s %s%s%s" % (job["kind"], job["spot"], (" exp=" + job["experiment"]) if job.get("experiment") else "",
                          (" env=%s" % job["env"]) if job.get("env") else "")


def notables(r):
    """What went wrong in a job result (empty = fine)."""
    notable = []
    if r.get("fatal"):
        notable.append("FATAL " + r["fatal"])
    if r.get("exited"):
        notable.append("GAME EXITED PC=%s ra=%s%s" % (r["exited"].get("pc"), r["exited"].get("ra"),
                       (" stack " + " ".join(r["exited"]["callers"][:3])) if r["exited"].get("callers") else ""))
    if r.get("hang"):
        notable.append("HANG %s" % r["hang"])
    if r.get("kernel_ok") is False or "kernel_bad_step" in r:
        notable.append("KERNEL overwritten")
    tb = r.get("table_bad")
    if tb:
        notable.append("WRONG MODELS %s" % (tb if isinstance(tb, int) else len(tb)))
    if r.get("alive") is False:
        notable.append("NOT ALIVE")
    if r.get("error") and not r.get("exited"):
        notable.append("ERROR " + r["error"][:120])
    return notable


# --- health alert ----------------------------------------------------------------------
class Health:
    """Tracks job outcomes; alerts into WORKLOG.md and pauses the idle rotation."""
    STREAK, WINDOW, MIN_WINDOW, REALERT = 3, 15 * 60, 4, 60 * 60

    def __init__(self):
        self.hist = []                 # (time, kind, ok, desc)
        self.alerted = None            # time of the active alert, or None
        self.last_alert = 0
        self.paused = False

    def worklog(self, text):
        line = "%s | lab (auto) | — | %s | devtest/_lab/events.log\n" % (time.strftime("%Y-%m-%d %H:%M"), text)
        try:
            with open(WORKLOG, "a", encoding="utf-8") as f:
                f.write(line)
        except OSError as e:
            event("could not write WORKLOG: %r" % e)
        event(text)

    def record(self, kind, ok, desc):
        now = time.time()
        self.hist.append((now, kind, ok, desc))
        self.hist = self.hist[-200:]
        reason = self.failing()
        if reason:
            if self.alerted is None or now - self.last_alert > self.REALERT:
                first = self.alerted is None
                self.alerted = self.alerted or now
                self.last_alert = now
                self.paused = True
                self.worklog("LAB ALERT: %s; last: %s; idle rotation paused until 3 jobs pass or a new build-dev exe"
                             % (reason, desc) if first else "LAB ALERT (still failing): %s; last: %s" % (reason, desc))
        elif self.alerted is not None and all(h[2] for h in self.hist[-self.STREAK:]) and len(self.hist) >= self.STREAK:
            self.worklog("LAB OK: %d jobs passed in a row after the alert of %s; rotation resumed"
                         % (self.STREAK, time.strftime("%H:%M", time.localtime(self.alerted))))
            self.alerted = None
            self.paused = False

    def failing(self):
        """Alert reason or None."""
        if not self.hist or self.hist[-1][2]:
            return None
        kind = self.hist[-1][1]
        same = [h for h in self.hist if h[1] == kind]
        streak = 0
        for h in reversed(same):
            if h[2]:
                break
            streak += 1
        if streak >= self.STREAK:
            return "%d %s jobs failed in a row" % (streak, kind)
        now = time.time()
        recent = [h for h in self.hist if now - h[0] <= self.WINDOW]
        bad = sum(1 for h in recent if not h[2])
        if len(recent) >= self.MIN_WINDOW and bad * 2 > len(recent):
            return "%d of %d jobs failed in the last 15 min" % (bad, len(recent))
        return None

    def reset(self, why):
        if self.alerted is not None:
            self.worklog("LAB alert cleared (%s); rotation resumed" % why)
        self.alerted, self.paused, self.hist = None, False, []


# --- scheduler ---------------------------------------------------------------------------
def run(slots: int, rotation: bool):
    for q in ("pending", "running", "done"):
        (JOBS / q).mkdir(parents=True, exist_ok=True)
    for f in (JOBS / "running").glob("*.json"):          # requeue after a restart
        f.rename(JOBS / "pending" / f.name)
    event("lab started: %d slots, rotation %s" % (slots, "on" if rotation else "off"))
    exe = dt.APP / dt.BUILD / "Driver_Recompiled.exe"
    last_exe = exe.stat().st_mtime
    busy, rot, seed, done = {}, 0, int(time.time()) % 1000, 0
    health = Health()
    while True:
        if exe.stat().st_mtime != last_exe and time.time() - exe.stat().st_mtime > 30:
            last_exe = exe.stat().st_mtime
            event("new dev build: queuing regression captures")
            health.reset("new build-dev exe")
            for s in dt.spots():
                add_job({"kind": "capture", "spot": s, "prio": 2, "note": "regression"})
        for k, (p, jid) in list(busy.items()):
            if p.poll() is not None:
                del busy[k]; done += 1
                try:
                    res = json.loads((LAB / "results" / jid / "job.json").read_text())
                    bad = notables(res["result"])
                    health.record(res["job"]["kind"], not bad, job_desc(res["job"]) + ((" — " + bad[0]) if bad else ""))
                except Exception as e:
                    health.record(jid.split("_")[2] if jid.count("_") >= 2 else "?", False, "%s — no result (%r)" % (jid, e))
        for k in range(slots):
            if k in busy:
                continue
            pend = sorted((JOBS / "pending").glob("*.json"))
            if not pend and rotation and not health.paused:
                names = list(dt.spots())
                add_job({"kind": "soak", "spot": names[rot % len(names)], "steps": 80, "seed": seed,
                         "prio": 9, "auto": True})
                rot += 1; seed += 1
                pend = sorted((JOBS / "pending").glob("*.json"))
            if not pend:
                continue
            f = JOBS / "running" / pend[0].name
            pend[0].rename(f)
            busy[k] = (subprocess.Popen([sys.executable, __file__, "_job", str(f), str(k)],
                                        stdout=subprocess.DEVNULL, stderr=open(LAB / ("slot%d.err" % k), "a")),
                       f.stem)
            time.sleep(5)
        STATUS.write_text("%s  slots busy %d/%d  pending %d  finished %d%s\n%s\n" % (
            time.strftime("%H:%M:%S"), len(busy), slots, len(list((JOBS / "pending").glob("*.json"))), done,
            ("  ALERT since %s (rotation paused)" % time.strftime("%H:%M", time.localtime(health.alerted))) if health.alerted else "",
            "\n".join(sorted(f.name for f in (JOBS / "running").glob("*.json")))))
        time.sleep(10)


def status():
    print(STATUS.read_text() if STATUS.exists() else "lab not running")
    if EVENTS.exists():
        print("\n".join(EVENTS.read_text(encoding="utf-8").splitlines()[-15:]))


if __name__ == "__main__":
    a = sys.argv[1:]
    if not a:
        print(__doc__)
    elif a[0] == "run":
        run(int(a[a.index("--slots") + 1]) if "--slots" in a else 6, "--no-rotation" not in a)
    elif a[0] == "add":
        job = {"kind": a[1], "spot": a[2]}
        for kv in a[3:]:
            k, v = kv.split("=", 1)
            try:
                job[k] = json.loads(v)
            except ValueError:
                job[k] = v
        print(add_job(job))
    elif a[0] == "status":
        status()
    elif a[0] == "_job":
        run_job(Path(a[1]), int(a[2]))
