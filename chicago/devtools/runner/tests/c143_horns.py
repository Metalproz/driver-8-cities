"""C143: Driver 1's AI horn (0x800180D8) takes its bank 0 entry from HORN (0x80093648, [model * 4 + (id & 3)]) instead of
the slot id (exe c143_patches; table bytes = entry - 6, 256 B [model * 32 + id]). CITY (default vegas): the code words, the table (D2 city: per
model = the model bank's horn slot, special 28; the same 4 bytes per model), then the player parks in traffic for WAIT s
(default 45; civilians honk at a blocking car) with the C137 trace on: which entries the channels start. Checks: table =
expected per model, AI horn starts only on D2 horn slots (24-28) in a D2 city; in Miami (CITY=miami) the table is Driver
1's id rule (6 / 7 / 8 / 8) and horn starts only 6-8."""
import os, re, struct, time

SESSION = dict(day="var_polish_cheats6_day.lev", night="var_polish_cheats6_night.lev", s4=True,
               env={"CHI_C137_TRACE": "1"})
CITY = os.environ.get("CITY", "vegas")
WAIT = float(os.environ.get("WAIT", "45"))
CODE = [0x92220010, 0x92260000, 0x00021140, 0x00C23021, 0x00DC3021, 0x90C6CED8, 0x2404FFFF, 0x00002821, 0x24C60006]


def run(s):
    s.menu("take_a_ride/" + CITY); s.wait_world(what=CITY)
    code = [s.word(0x80018084 + 4 * k) for k in range(9)]
    s.check("AI horn code patched (9 words)", code == CODE, " ".join("%08X" % w for w in code))
    tab = s.ram(0x80093648, 256)
    per = [bytes(6 + b for b in tab[32 * m: 32 * m + 4]) for m in range(8)]   # entries of ids 0-3 per model
    s.record("table", detail=" | ".join("m%d %s" % (m, list(p)) for m, p in enumerate(per)))
    d1 = CITY in ("miami", "frisco", "la", "ny", "newtown", "desert")
    if d1:
        s.check("Driver 1 city: table = the id rule 6 / 7 / 8 / 8", all(list(p) == [6, 7, 8, 8] for p in per), str(per[:3]))
    else:
        ok = all(len(set(p)) == 1 and p[0] in (24, 25, 26, 28) for p in per[1:6])
        s.check("D2 city: one horn slot per model (24-26 / 28)", ok, " ".join("m%d=%d" % (m, per[m][0]) for m in range(1, 6)))
    # the AI horn (FUN_8001A1BC) fires for a car heading against the player within 9000 ahead: turn round and drive
    # against the traffic of the start lane
    x, y, z, h, _ = s.car(0)
    back = (int(h) + 2048) & 4095
    s.pose(x, z, back)
    t0 = time.time()
    while time.time() - t0 < WAIT:
        s.drive(3.0, back)
        time.sleep(1.0)
    s.screenshot("parked")
    txt = (s.dir / "game.log").read_text(encoding="utf-8", errors="replace") if (s.dir / "game.log").exists() else ""
    if not txt:
        import glob
        logs = sorted(glob.glob(str(s.copy_dir / "dev" / "logs" / "*.log")), key=os.path.getmtime)
        txt = open(logs[-1], encoding="utf-8", errors="replace").read() if logs else ""
    seen = sorted({int(k) for b, k in re.findall(r"C137 trace: first bank (\d+) sample (\d+)", txt) if b == "0"})
    horns = [k for k in seen if k in (6, 7, 8, 24, 25, 26, 27, 28)]
    s.record("horn entries started", detail="%s: %s (all bank 0 seen %s)" % (CITY, horns, seen))
    if d1:
        s.check("Driver 1 city: horn starts only on 6-8", all(k in (6, 7, 8) for k in horns), str(horns))
    else:
        s.check("D2 city: no Driver 1 horn entry (6-8) started", not any(k in (6, 7) for k in horns), str(horns))
    s.check("alive", s.alive())
