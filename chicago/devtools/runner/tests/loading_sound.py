"""cheats 5 'sound plays in Chicago's loading screen': Take a Ride Chicago with NIGHTMARE (NM=1) and whatever
RUNNER_UNCAP / RUNNER_XDRAW; SPU key-ons (MMIO 0x1F801D88/8A) between the menu confirm and the first game frame."""
import os, threading, time
SESSION = dict(day="var_polish_specdmg2_day.lev", night="var_polish_specdmg2_night.lev", s4=True)


def run(s):
    if os.environ.get("NM", "1") == "1": s.poke32(0x800933C8, 1)
    first = {}
    stop = [0]
    def watch():
        fc0 = None
        while not stop[0]:
            try:
                fc, vb = s.word(0x800970D8), s.word(0x80095250)
            except Exception:
                time.sleep(0.05); continue
            if fc0 is None: fc0 = fc
            if "vb" not in first and fc0 is not None and fc != fc0 and fc < 50: first["vb"] = vb
            time.sleep(0.02)
    th = threading.Thread(target=watch, daemon=True)
    s.d.cmd("mmio_clear")
    th.start()
    s.menu("take_a_ride/chicago"); s.wait_world(what="start")
    stop[0] = 1
    ents = s.d.cmd("mmio_dump", count=200000, newest=True).get("entries", [])
    kon = [e for e in ents if e["addr"].lower() in ("0x1f801d88", "0x1f801d8a") and int(e["val"], 16)]
    vb = first.get("vb", 0)
    before = [e for e in kon if e["frame"] < vb - 2]
    frames = sorted(set(e["frame"] for e in before))
    s.record("keyons", detail="first game frame at vblank %d; key-ons before it: %d at vblanks %s (of %d MMIO entries)" % (
        vb, len(before), frames[-12:], len(ents)))
    s.check("loading screen silent", len(before) == 0 or (frames and frames[-1] < vb - 400), "%d key-ons, last at %s" % (len(before), frames[-1:] if frames else None))
