"""C137 (user rule Q71): in a D2 city Driver 1's horns (bank 0 entries 6-8) point at the city's D2 civilian horns, the freed
block holds the city's D2 siren as entry 4 (Driver 1's siren dropped) and the siren's pitch / volume sweep code words are
constants; Driver 1 cities stay untouched.

CITY (default vegas): wait, cops chase (felony), drive SECS (default 12) sampling spu_voices; then quit to the menu and
start Miami (D1). Checks: entries 6/7/8 = D2 horns, entry 4 = the D2 siren (8000 Hz, size of car_sfx kind 3), the code
words, a voice played the siren's address at a fixed pitch during the chase; in Miami entry 4 / 6-8 and the words are
Driver 1's again."""
import json, os, struct, time

SESSION = dict(day="var_polish_cheats6_day.lev", night="var_polish_cheats6_night.lev", s4=True)
CITY = os.environ.get("CITY", "vegas")
SECS = float(os.environ.get("SECS", "12"))
SECOND = os.environ.get("SECOND", "miami")   # the Driver 1 city afterwards: miami | la
TAB = 0x800BCA74
WORDS = {0x8004CCB4: (0x00621823, 0x24031000), 0x8004CC84: (0x00473823, 0x2407F830)}   # (Driver 1, D2 siren)
D2ROWS = {"chicago": 0, "havana": 1, "vegas": 2, "rio": 3}


LUMP4 = 0x8008A985                                     # C137 step 2: Take a Ride's bank 4 lump byte (0xFF = skipped)


def bank4(s):
    """(lump byte, entries of the bank 4 table with an address, mission block base)"""
    t = s.ram(0x800BCA74 + 0x800, 16 * 32)
    n = sum(1 for k in range(32) if struct.unpack_from("<I", t, 16 * k)[0])
    return s.ram(LUMP4, 1)[0], n, s.word(0x800BD484 + 16)


def table(s):
    t = s.ram(TAB, 16 * 32)
    return [struct.unpack_from("<4I", t, 16 * k) for k in range(32)]


def siren_of(s):
    pk = s.copy_dir / "mods" / "packages" / "driver.chicago" / "0.1.0" / "assets"
    f = (pk / CITY / "car_sfx.bin") if CITY != "chicago" else (pk / "car_sfx.bin")
    d = f.read_bytes(); n = struct.unpack_from("<i", d, 4)[0]
    for i in range(n):
        bk, kd, sz, lp, rt = struct.unpack_from("<5i", d, 8 + 20 * i)
        if kd == 3:
            return bk, sz, rt
    return None


def run(s):
    s.menu("take_a_ride/" + CITY); s.wait_world(what=CITY)
    sir = siren_of(s)
    t = table(s)
    s.record("bank0", detail=" ".join("%d:%05X/%d/%d" % (k, a, z, r) for k, (a, z, l, r) in enumerate(t) if a))
    horns_ok = all(t[6 + k][0] == t[src][0] and t[src][0] for k, src in enumerate((25, 24, 26)) if t[src][0]) and \
        t[8][0] not in (0,) and t[6][3] < 11025
    s.check("entries 6/7/8 = the D2 civilian horns", horns_ok, "6 %05X 7 %05X 8 %05X / 25 %05X 24 %05X 26 %05X"
            % (t[6][0], t[7][0], t[8][0], t[25][0], t[24][0], t[26][0]))
    s.check("entry 4 = the D2 siren (car_sfx kind 3)", sir is not None and t[4][1] == sir[1] and t[4][3] == sir[2],
            "entry 4 %05X/%d/%d, siren %s" % (t[4][0], t[4][1], t[4][3], sir))
    lb, n4, b4 = bank4(s)
    sp = t[22]                                          # the special's engine slot (when a special is loaded)
    s.check("bank 4 not loaded in the D2 city (lump byte 0xFF, table empty)", lb == 0xFF and n4 == 0,
            "lump byte %02X, bank 4 entries %d" % (lb, n4))
    s.record("special engine", detail="slot 22 %05X/%d, mission block %05X..%05X" % (sp[0], sp[1], b4, b4 + 0x21800))
    if sp[0]:
        s.check("special engine inside the freed mission block", b4 <= sp[0] < b4 + 0x21800, "%05X" % sp[0])
    w = {a: s.word(a) for a in WORDS}
    s.check("siren code words = D2 constants", all(w[a] == WORDS[a][1] for a in WORDS), str({hex(a): hex(v) for a, v in w.items()}))
    # the player's horn (R1 -> entry 8 on channel 4; the plugin retargets it to the player's D2 horn, slot 27 / 25)
    t = table(s)
    ph = t[27][0] if t[27][1] else t[25][0]
    starts = set()
    for btn in ("r1", "r3"):
        s.hold(btn)
        for _ in range(8):
            r = s.d.cmd("spu_voices")
            for v in r.get("voices", []) if isinstance(r, dict) else []:
                if v.get("v") == 4 and v.get("active") and v.get("start"):
                    starts.add(int(v["start"], 16))
            time.sleep(0.1)
        s.release(); time.sleep(0.5)
    s.check("player horn plays the D2 player horn on voice 4", ph in starts,
            "voice 4 starts %s, player horn %05X, entry 8 %05X" % (sorted("%05X" % a for a in starts), ph, t[8][0]))
    s.poke32(0x80097708, 0x1000)                        # felony: cops chase with sirens
    x, y, z, h, _ = s.car(0)
    seen = {}

    def tick(ss):
        r = ss.d.cmd("spu_voices")
        for v in r.get("voices", []) if isinstance(r, dict) else []:
            if v.get("active") and v.get("start") and int(v["start"], 16) == t[4][0]:
                seen.setdefault(v.get("v"), set()).add(v.get("pitch"))
        return False
    t0 = time.time()
    drive_s = float(os.environ.get("DRIVE", "0" if CITY == "rio" else str(SECS)))   # Rio's start faces the sea
    while time.time() - t0 < SECS:
        if time.time() - t0 < drive_s:
            s.drive(2.0, h, on_tick=tick)
        else:
            tick(s); time.sleep(0.5)
        tick(s)
    s.record("siren voices", detail=json.dumps({k: sorted(map(str, p)) for k, p in seen.items()}))
    want = t[4][3] * 4096 // 44100                     # 8000 Hz -> 0x2E7; Driver 1's sweep went down to ~6 % of it,
    ok = bool(seen) and all(want * 3 // 4 <= int(str(q), 16) <= want * 13 // 10 for p in seen.values() for q in p)   # Doppler (scale +0x52) +-; D1's sweep went to ~7 %
    s.check("the D2 siren sounded at its own pitch (no Driver 1 sweep, Doppler only)", ok,
            json.dumps({k: sorted(map(str, p)) for k, p in seen.items()}))
    s.screenshot(CITY)
    import importlib.util as iu
    sp = iu.spec_from_file_location("cs_", os.path.join(os.path.dirname(os.path.abspath(__file__)), "city_switch.py"))
    cs_ = iu.module_from_spec(sp); sp.loader.exec_module(cs_)
    cs_.quit_to_menu(s)
    s.screenshot("after_quit")
    s.press("triangle"); time.sleep(2)
    s.press("cross"); time.sleep(1.5)                  # Take a Ride list, page 2 remembered (cursor on Chicago)
    for _ in range(4):
        s.press("down", gap=0.8)                        # "Driver 1 cities" page row
    s.press("cross", gap=1.5)                           # page 1, cursor on Miami
    if SECOND == "la":                                  # LA: the same CITY slot (3) as the D2 cities
        s.press("down", gap=0.8); s.press("down", gap=0.8)
    s.press("cross"); time.sleep(3)
    s.press("cross")                                    # Day / Night screen (LA without a day level: none)
    time.sleep(4)
    s.wait_for(s.in_level, 120, "in level (%s)" % SECOND)
    s.wait_world(what=SECOND)
    s.screenshot(SECOND)
    t2 = table(s)
    lb2, n42, _ = bank4(s)
    s.check("%s: bank 4 loaded again (lump byte 00)" % SECOND, lb2 == 0 and n42 > 0, "lump byte %02X, entries %d" % (lb2, n42))
    w2 = {a: s.word(a) for a in WORDS}
    s.record(SECOND, detail="CITY %d bank0 4:%05X/%d 6:%05X/%d 8:%05X/%d words %s" % (s.word(0x80096834), t2[4][0], t2[4][1],
             t2[6][0], t2[6][1], t2[8][0], t2[8][1], {hex(a): hex(v) for a, v in w2.items()}))
    s.check("%s: Driver 1's siren / horns / code words" % SECOND, s.word(0x80096834) == (0 if SECOND == "miami" else 3) and t2[4][1] == 1920 and
            (t2[6][1], t2[7][1], t2[8][1]) == (9648, 4560, 4144) and all(w2[a] == WORDS[a][0] for a in WORDS),
            "4 size %d, 6-8 sizes %d/%d/%d" % (t2[4][1], t2[6][1], t2[7][1], t2[8][1]))
    # C138: Driver 1's light sizes and no car-0 shadow offsets in the Driver 1 city
    d1_lights = {0x80043970: 0x24070014, 0x80043BB0: 0x2407001E, 0x80043DF4: 0x24070019, 0x80046398: 0x2407001E,
                 0x800465A8: 0x24070019}
    if s.word(0x80043970) == 0x8787CFE0:          # C148 exe: sizes come from the LSZ table (Driver 1's in a D1 city)
        lsz = struct.unpack("<5h", s.ram(0x80093750, 10))
        bad = {} if lsz == (20, 30, 25, 30, 25) else {"LSZ": lsz}
    else:
        bad = {hex(a): hex(s.word(a)) for a, v in d1_lights.items() if s.word(a) != v}
    shd0 = [s.word(0x80093480 + 4 * k) for k in range(4)]
    s.check("%s: Driver 1's light sizes, no player shadow offsets (C138)" % SECOND, not bad and not any(shd0),
            "words %s, SHD0 %s" % (bad, [hex(w) for w in shd0]))
    s.check("alive", s.alive())
