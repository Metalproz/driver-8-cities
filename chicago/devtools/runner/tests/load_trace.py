"""C135: trace the CD reads (cd_read_log, dma_cdrom_history) while Take a Ride CITY loads; saves the newest snapshots into
the run dir (the load may crash: the poller keeps the last good copy)."""
import json, os, threading, time
CITY = os.environ.get("CITY", "newtown")
SESSION = dict(day="var_polish_cheats6_day.lev", night="var_polish_cheats6_night.lev", s4=True)


def run(s):
    import sys
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
    import dt
    stop = threading.Event(); last = {}
    def poll():
        d2 = dt.Dbg(s.port)
        while not stop.is_set():
            for c in ("cd_read_log", "dma_cdrom_history"):
                try:
                    last[c] = d2.cmd(c, newest=1, count=4096) if c == "dma_cdrom_history" else d2.cmd(c, tail=4096)
                except Exception:
                    pass
            time.sleep(0.15)
    th = threading.Thread(target=poll, daemon=True); th.start()
    try:
        s.menu("take_a_ride/" + CITY)
    except Exception as e:
        s.record("menu", ok=False, detail=str(e)[:200])
    time.sleep(3)
    stop.set(); th.join(timeout=3)
    for c, v in last.items():
        (s.dir / (c + ".json")).write_text(json.dumps(v), encoding="utf-8")
    s.record("saved", detail=str(list(last)))
