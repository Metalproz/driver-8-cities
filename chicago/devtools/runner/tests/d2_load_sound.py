"""C127 (user R65: a sound at the start of loading a D2 map after a map with car sounds was played): Take a Ride FIRST
(default chicago), drive a bit, quit to the menu, Take a Ride CITY (default havana; page 2 remembered); SPU key-ons
(MMIO 0x1F801D88 / 8A) between the second menu confirm and the second level's first game frame, with the voices' start
addresses (spu_voices) at the first key-on."""
import os, threading, time
FIRST = os.environ.get("FIRST", "chicago")
CITY = os.environ.get("CITY", "havana")
SESSION = dict(day="var_polish_cheats6_day.lev", night="var_polish_cheats6_night.lev", s4=True)


def run(s):
    import importlib.util as iu
    sp = iu.spec_from_file_location("cs_", os.path.join(os.path.dirname(os.path.abspath(__file__)), "city_switch.py"))
    cs = iu.module_from_spec(sp); sp.loader.exec_module(cs)
    if FIRST != "none":
        s.menu("take_a_ride/" + FIRST); s.wait_world(what=FIRST)
        s.drive(6.0, s.car(0)[3])
        cs.quit_to_menu(s)
        s.press("triangle"); time.sleep(2)
        s.press("cross"); time.sleep(1.5)
        if FIRST not in ("chicago", "havana", "vegas", "rio"):   # page 1 remembered: turn to page 2
            for _ in range(7):
                s.press("down", gap=0.6)
            s.press("cross", gap=1.0); time.sleep(1)
    else:                                                 # the first load of the session (reference)
        s.press("triangle"); time.sleep(2)
        for b_ in ["right"] * 5 + ["cross"]:
            s.press(b_)
        time.sleep(1.5)
        for _ in range(7):
            s.press("down", gap=0.6)
        s.press("cross", gap=1.0); time.sleep(1)
    for _ in range({"chicago": 0, "havana": 1, "vegas": 2, "rio": 3}[CITY]):
        s.press("down", gap=0.8)
    s.press("cross"); time.sleep(3)
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
            if "vb" not in first and fc != fc0 and fc < 50: first["vb"] = vb
            time.sleep(0.02)
    s.d.cmd("mmio_clear"); s.d.cmd("spu_events_reset")
    vb0 = s.word(0x80095250)
    af0 = int(s.d.cmd("audio_stats")["taps"][0]["frames"])
    th = threading.Thread(target=watch, daemon=True); th.start()
    s.press("cross", gap=0.1)                             # Day confirm: the load starts
    snaps = []
    for _ in range(6):
        time.sleep(0.15)
        r = s.d.cmd("spu_voices")
        snaps.append([(v["v"], v["start"], v["vol_l"], v["pitch"]) for v in r.get("voices", []) if v.get("active")])
    s.record("voices_at_load", detail=str(snaps)[:1500])
    s.wait_for(s.in_level, 120, "in level (%s)" % CITY)
    s.wait_world(what=CITY)
    stop[0] = 1
    af1 = int(s.d.cmd("audio_stats")["taps"][0]["frames"])
    for tap in (0, 3):                                    # SPU out / voices only
        path = s.dir / ("load_tap%d.wav" % tap)
        s.d.cmd("audio_wav", path=str(path), tap=tap, start=str(af0), count=str(max(1, af1 - af0)))
        if path.exists():
            import wave, numpy as np
            with wave.open(str(path)) as w:
                ch, n = w.getnchannels(), w.getnframes()
                a_ = np.frombuffer(w.readframes(n), dtype=np.int16).reshape(-1, ch).astype(np.int32).mean(axis=1)
            seg = 4410
            rms = [int(np.sqrt((a_[i:i + seg] ** 2).mean())) for i in range(0, len(a_) - seg + 1, seg)]
            s.record("audio_tap%d" % tap, detail="%.1f s from the confirm, RMS per 0.1 s: %s" % (len(a_) / 44100, rms[:80]))
    ev = s.d.cmd("spu_events", count=4096).get("events", [])
    ko = [e for e in ev if e.get("kind") == "KEYON"]
    s.record("spu_keyons", detail="%d key-ons in the ring; first 16: %s" % (len(ko), [(e["frame"], e["v"], e["addr"], e["vol_l"]) for e in ko[:16]]))
    ents = s.d.cmd("mmio_dump", count=200000, newest=True).get("entries", [])
    kon = [e for e in ents if e["addr"].lower() in ("0x1f801d88", "0x1f801d8a") and int(e["val"], 16)]
    vb = first.get("vb", 0)
    before = [e for e in kon if vb0 <= e["frame"] < vb - 2]
    s.record("keyons", detail="confirm at vblank %d, first game frame at %d; key-ons between: %d %s" % (
        vb0, vb, len(before), [(e["frame"], e["addr"][-2:], e["val"], e.get("pc", "")) for e in before[:12]]))
    s.check("%s -> %s: loading silent" % (FIRST, CITY), len(before) == 0, "%d key-ons" % len(before))
