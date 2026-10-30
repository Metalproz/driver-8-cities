"""C137 step 2 usage check: which bank 0 / bank 4 samples Take a Ride actually starts (plugin trace CHI_C137_TRACE=1:
every logical channel's sample address per vblank). CITY (default vegas): DRIVE s (default 90) of driving with a
heading change every 6 s (crashes, smashable objects, traffic), horn presses, then a cop chase (felony) for CHASE s
(default 60) with more turns. Records the first-seen (bank, sample) list and whether any of the drop candidates bank 0
s5 / s9 / s14 / s15 or bank 4 played."""
import os, re, time

SESSION = dict(day="var_polish_cheats6_day.lev", night="var_polish_cheats6_night.lev", s4=True,
               env={"CHI_C137_TRACE": "1"})
CITY = os.environ.get("CITY", "vegas")
DRIVE = float(os.environ.get("DRIVE", "90"))
CHASE = float(os.environ.get("CHASE", "60"))


def run(s):
    s.menu("take_a_ride/" + CITY); s.wait_world(what=CITY)
    x, y, z, h, _ = s.car(0)
    h = int(h)
    t0, k = time.time(), 0
    slots = set()                                       # mission-script sound slots 0x800C6F04 + 0x14 (3 x 16 B):

    def tick(ss):                                       # flags +0xA (bit 0 armed, 6: 2 = plain, 4 = 3D, 0 = speech),
        b = ss.ram(0x800C6F18, 0x30)                    # sample +0xB, bank +0xC (FUN_0006a6c8)
        for i in range(3):
            if b[16 * i + 10] or b[16 * i + 11] or b[16 * i + 12]:
                slots.add((b[16 * i + 10], b[16 * i + 12], b[16 * i + 11]))
        return False
    while time.time() - t0 < DRIVE:
        s.drive(6.0, (h + 1024 * (k % 4) + (512 if k % 3 == 0 else 0)) & 4095, on_tick=tick)
        if k % 2 == 0:
            s.press("r1", hold=0.4, gap=0.2)
        k += 1
    s.poke32(0x80097708, 0x1000)                        # felony: cop chase (siren, radio)
    t0 = time.time()
    while time.time() - t0 < CHASE:
        s.drive(6.0, (h + 1024 * (k % 4)) & 4095, on_tick=tick)
        k += 1
    s.record("script slots", detail="%s: (flags, bank, sample) seen %s" % (CITY, sorted(slots) or "none"))
    time.sleep(2.0)
    s.screenshot("end")
    log = (s.dir / "game.log")
    txt = log.read_text(encoding="utf-8", errors="replace") if log.exists() else ""
    if not txt:
        import glob
        logs = sorted(glob.glob(str(s.copy_dir / "dev" / "logs" / "*.log")), key=os.path.getmtime)
        txt = open(logs[-1], encoding="utf-8", errors="replace").read() if logs else ""
    seen = sorted({(int(b), int(k_)) for b, k_ in re.findall(r"C137 trace: first bank (\d+) sample (\d+)", txt)})
    cand = [p for p in seen if p in {(0, 5), (0, 9), (0, 14), (0, 15)} or p[0] == 4]
    s.record("seen", detail="%s: %s" % (CITY, " ".join("%d/%d" % p for p in seen)))
    s.record("candidates", ok=True, detail="%s: drop candidates played: %s" % (CITY, cand or "none"))
    s.check("trace ran (samples seen)", len(seen) > 3, str(seen))
    s.check("alive", s.alive())
