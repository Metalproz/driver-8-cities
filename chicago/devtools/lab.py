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
    r = res["result"]
    notable = []
    if r.get("fatal"):
        notable.append("FATAL " + r["fatal"])
    if r.get("hang"):
        notable.append("HANG %s" % r["hang"])
    if r.get("kernel_ok") is False or "kernel_bad_step" in r:
        notable.append("KERNEL overwritten")
    tb = r.get("table_bad")
    if tb:
        notable.append("WRONG MODELS %s" % (tb if isinstance(tb, int) else len(tb)))
    if r.get("alive") is False:
        notable.append("NOT ALIVE")
    if r.get("error"):
        notable.append("ERROR " + r["error"][:120])
    desc = "%s %s%s%s" % (job["kind"], job["spot"], (" exp=" + job["experiment"]) if job.get("experiment") else "",
                         (" env=%s" % job["env"]) if job.get("env") else "")
    if notable or not job.get("auto"):
        event("%s %s: %s  [%s]" % ("!!" if notable else "ok", desc, "; ".join(notable) or "fine", out))
    path.rename(JOBS / "done" / path.name)


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
    while True:
        if exe.stat().st_mtime != last_exe and time.time() - exe.stat().st_mtime > 30:
            last_exe = exe.stat().st_mtime
            event("new dev build: queuing regression captures")
            for s in dt.spots():
                add_job({"kind": "capture", "spot": s, "prio": 2, "note": "regression"})
        for k, p in list(busy.items()):
            if p.poll() is not None:
                del busy[k]; done += 1
        for k in range(slots):
            if k in busy:
                continue
            pend = sorted((JOBS / "pending").glob("*.json"))
            if not pend and rotation:
                names = list(dt.spots())
                add_job({"kind": "soak", "spot": names[rot % len(names)], "steps": 80, "seed": seed,
                         "prio": 9, "auto": True})
                rot += 1; seed += 1
                pend = sorted((JOBS / "pending").glob("*.json"))
            if not pend:
                continue
            f = JOBS / "running" / pend[0].name
            pend[0].rename(f)
            busy[k] = subprocess.Popen([sys.executable, __file__, "_job", str(f), str(k)],
                                       stdout=subprocess.DEVNULL, stderr=open(LAB / ("slot%d.err" % k), "a"))
            time.sleep(5)
        STATUS.write_text("%s  slots busy %d/%d  pending %d  finished %d\n%s\n" % (
            time.strftime("%H:%M:%S"), len(busy), slots, len(list((JOBS / "pending").glob("*.json"))), done,
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
