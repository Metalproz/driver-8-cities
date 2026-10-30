"""D2 car sounds check (R36 / user 'havana 1': D2 cities use Driver 1's engine / traffic / horn sounds?): Take a Ride in
CITY (chicago|havana), drive SECS (default 20) with a horn press, sample spu_voices every 0.5 s and record which SPU sample
start addresses play on the car channels (0 engine, 1 idle, 4 horn, 7 / 8 AI engines) + the plugin's R36 log lines."""
import glob, json, os, time
CITY = os.environ.get("CITY", "havana")
SECS = float(os.environ.get("SECS", "20"))
SESSION = dict(day="var_polish_cheats6_day.lev", night="var_polish_cheats6_night.lev", s4=True)


def run(s):
    first = os.environ.get("FIRST")                     # e.g. FIRST=havana: play that city first, quit, then CITY
    if first:
        import importlib.util as iu
        sp = iu.spec_from_file_location("cs_", os.path.join(os.path.dirname(os.path.abspath(__file__)), "city_switch.py"))
        cs_ = iu.module_from_spec(sp); sp.loader.exec_module(cs_); quit_to_menu = cs_.quit_to_menu
        s.menu("take_a_ride/" + first); s.wait_world(what=first); time.sleep(5)
        quit_to_menu(s)
        # the Take a Ride list remembers page 2 (cursor on Chicago): the row directly
        s.press("triangle"); time.sleep(2)
        s.press("cross")                                    # the carousel is still on Take a Ride
        time.sleep(1.5)
        s.screenshot("page2_again")                         # page 2 still shown, cursor on its first row (Chicago)
        if CITY == "havana":
            s.press("down", gap=0.8)
        s.press("cross"); time.sleep(3); s.press("cross")
        s.wait_for(s.in_level, 120, "in level (second)")
        time.sleep(3)
    else:
        s.menu("take_a_ride/" + CITY)
    s.wait_world(what=CITY)
    x, y, z, h, _ = s.car(0)
    if os.environ.get("FELONY"):
        s.poke32(0x80097708, int(os.environ["FELONY"], 0))     # cops chase (siren)
    seen = {}

    def tick(ss):
        r = ss.d.cmd("spu_voices")
        for v in r.get("voices", []) if isinstance(r, dict) else []:
            ch = v.get("v")
            if ch is not None and v.get("active"):
                k = v.get("start")
                seen.setdefault(ch, {}).setdefault(k, 0)
                seen[ch][k] += 1
        return False
    t0 = time.time()
    while time.time() - t0 < SECS:
        s.drive(2.0, h, on_tick=tick)
        if not seen.get(4):
            s.d.press("r3", hold=0.3, gap=0.2)                # the player's horn (R3)
        tick(s)
    s.record("voices", detail=json.dumps(seen)[:1500])
    # which sample each car channel plays: SPU bytes at the voice start vs the set's car_sfx.bin samples (D2) / else D1
    import struct as st_
    pk = s.copy_dir / "mods" / "packages" / "driver.chicago" / "0.1.0" / "assets"
    sfx = (pk / CITY / "car_sfx.bin") if CITY in ("havana", "vegas", "rio") else (pk / "car_sfx.bin")
    smp = {}
    if sfx.exists():
        d = sfx.read_bytes(); n = st_.unpack_from("<i", d, 4)[0]; dp = 8 + 20 * n + 28
        for i in range(n):
            bk, kd, sz, lp, rt = st_.unpack_from("<5i", d, 8 + 20 * i)
            smp[d[dp + 16: dp + 48]] = "D2 bank %d %s" % (bk, ("engine", "idle", "horn", "siren")[kd])
            dp += (sz + 15) & ~15
    what = {}
    for ch in (0, 1, 4, 7, 8):
        for addr in (seen.get(ch) or {}):
            r = s.d.cmd("spu_ram", addr=int(addr, 16), len=48)
            b_ = bytes.fromhex(r.get("hex", ""))[16:48]
            what["%d@%s" % (ch, addr)] = smp.get(b_, "not D2 (Driver 1 / other)")
    s.record("samples", detail=json.dumps(what))
    tab = s.ram(0x800BCA74, 16 * 32)
    import struct
    ent = [struct.unpack_from("<4I", tab, 16 * k) for k in range(32)]
    s.record("bank0", detail=" ".join("%d:%05X/%d/%d" % (k, a, z, r) for k, (a, z, l, r) in enumerate(ent) if a))
    logs = sorted(glob.glob(str(s.copy_dir / "dev" / "logs" / "*.log")), key=os.path.getmtime)
    if logs:
        lines = [l.strip() for l in open(logs[-1], encoding="utf-8", errors="replace") if "R36" in l or "sound" in l.lower()]
        s.record("log", detail=" | ".join(lines)[:1200])
