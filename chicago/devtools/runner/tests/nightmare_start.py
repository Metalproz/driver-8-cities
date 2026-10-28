"""C90: Nightmare on before the level: felony full at the start, nothing written before the game runs, at most 12
chasers from their spawn, no cap on PC, pause = quiet (no key-ons, low audio)."""
import os, time
CITY = os.environ.get("CITY", "chicago")
SESSION = dict(day="var_polish_specdmg2_day.lev", night="var_polish_specdmg2_night.lev", s4=True)


def run(s):
    s.poke32(0x8009681C, 1); s.poke32(0x800933C8, 1)
    s.menu("take_a_ride/" + CITY)
    fel0 = s.word(0x80097708)
    s.wait_world(what="start")
    s.check("felony full at the start", fel0 >= 0xF00 or s.word(0x80097708) >= 0xF00, "felony %#x at entry, %#x now" % (fel0, s.word(0x80097708)))
    counts, spc, cops = [], set(), set()
    for _ in range(24):
        raw = s.ram(0x80098950, 0x50 * 24)
        cops |= {i for i in range(24) if raw[i * 0x50 + 1] == 4 and 1 <= raw[i * 0x50 + 5] <= 4}
        pur = [i for i in range(24) if raw[i * 0x50 + 1] == 4 and raw[i * 0x50 + 5] > 4]
        spc |= {i for i in pur if raw[i * 0x50 + 0x10] == 5}
        counts.append(len(pur)); time.sleep(0.5)
    spawned = s.word(0x800933E8)
    s.record("chasers", detail="over 12 s %s, spawned as chasers %d, specials among them %s" % (counts, spawned, sorted(spc)))
    s.check("chasers (no cap on PC)", max(counts) >= 8, "%s" % counts)
    s.check("traffic spawns as chasers (spawn hook)", spawned >= 3, "%d spawned as chasers" % spawned)
    s.check("Driver 1's police cars spawn and chase too", len(cops) >= 1, "police records in pursuit %s" % sorted(cops))
    s.press("start", gap=1.0); time.sleep(1.5)
    s.d.cmd("mmio_clear"); time.sleep(5.0)
    ents = s.d.cmd("mmio_dump", count=20000, newest=True).get("entries", [])
    kon = sum(1 for e in ents if e["addr"].lower() in ("0x1f801d88", "0x1f801d8a") and int(e["val"], 16))
    time.sleep(2.0); _, m = s.audio("paused", 2.0)          # the last 2 s (the audio tap lags the pause by ~0.7 s)
    s.check("pause quiet", kon == 0 and m.get("rms", 0) < 500, "key-ons %d, rms %s" % (kon, m.get("rms")))
    s.screenshot("paused")
