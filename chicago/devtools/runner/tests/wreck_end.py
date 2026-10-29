"""C135 follow-up (flip_wreck crashed once on build-wip: FAIL-FAST 0x000000B0, ra 0x80077AC8, a CD read ran from
0x801852BC over 0x80200000 a few seconds after the wreck): wreck the player car in CITY (default miami) and let the game
go on for WAIT s (default 30) after the wreck; record the CD reads (dma_cdrom_history) as they happen. Check: alive."""
import json, os, time
import importlib.util as _iu

_sp = _iu.spec_from_file_location("fw_", os.path.join(os.path.dirname(os.path.abspath(__file__)), "flip_wreck.py"))
_fw = _iu.module_from_spec(_sp); _sp.loader.exec_module(_fw)
SESSION = _fw.SESSION
CITY = os.environ.get("CITY", "miami")
WAIT = float(os.environ.get("WAIT", "30"))


def run(s):
    s.menu("take_a_ride/" + CITY); s.wait_world(what="start")
    inv = float(os.environ.get("INV", "10"))           # flip_wreck's order: Invincibility on the roof first, then off
    if inv: s.poke32(_fw.INV, 1); time.sleep(0.5)
    for attempt in range(4):
        s.d.cmd("pause"); _fw.flip(s); s.d.cmd("continue")
        time.sleep(1.0)
        up = s.word(0x8009B0B0) & 0xFFFF
        up = up - 0x10000 if up & 0x8000 else up
        if up < -3000:
            break
    s.record("flipped", detail="up vector y %d (attempt %d)" % (up, attempt + 1))
    if inv:
        time.sleep(inv); s.screenshot("roof"); s.poke32(_fw.INV, 0)
    log = open(os.path.join(str(s.dir), "cd_reads.jsonl"), "w", encoding="utf-8")
    t0 = time.time(); last = None; wrecked = None
    while time.time() - t0 < 8.0 + WAIT:
        try:
            h = s.d.cmd("dma_cdrom_history")
        except Exception as e:
            s.record("tcp", ok=False, detail=str(e)[:120]); break
        txt = json.dumps(h)
        if txt != last:
            log.write(json.dumps({"t": round(time.time() - t0, 2), "h": h}) + "\n"); log.flush(); last = txt
        if wrecked is None and (s.word(_fw.DMG) & 0xFFFF) >= (s.word(_fw.MAXD) & 0xFFFF) > 0:
            wrecked = time.time() - t0
            s.record("wrecked", detail="after %.1f s" % wrecked)
        time.sleep(0.3)
    s.screenshot("after")
    s.check("alive %d s after the flip (wrecked at %s)" % (8 + WAIT, "%.1f s" % wrecked if wrecked else "never"), s.alive())
