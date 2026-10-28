"""C97 (cheats 5: 'Quick Replay ends early with cheats on, the car takes damage in the replay'): Miami with
INVINCIBILITY (+ NIGHTMARE unless NM=0), drive DRIVE s into traffic, then Quick Replay; during the replay: the cheat
words, the player damage, the last game frame reached vs the recorded one."""
import os, time
SESSION = dict(day="var_polish_specdmg2_day.lev", night="var_polish_specdmg2_night.lev", s4=True)
INV, NGHT, DMG, FC = 0x8009681C, 0x800933C8, 0x8009B220, 0x800970D8


def run(s):
    s.poke32(INV, 1)
    if os.environ.get("NM", "1") == "1": s.poke32(NGHT, 1)
    if os.environ.get("HELL") == "1": s.poke32(0x8009342C, 1)
    s.menu("take_a_ride/miami"); s.wait_world(what="start")
    dmax = [0]
    def tick(ss):
        dmax[0] = max(dmax[0], ss.word(DMG) & 0xFFFF)
    s.drive(float(os.environ.get("DRIVE", "40")), s.car(0)[3], on_tick=tick)
    f_rec = s.word(FC)
    s.record("flags play", detail="74 %x 6F80 %x 67E8 %x 6874 %x" % (s.word(0x80097074), s.word(0x80096F80), s.word(0x800967E8), s.word(0x80096874)))
    s.record("recorded", detail="frames %d, inv %d ngt %d, max damage %d" % (f_rec, s.word(INV), s.word(NGHT), dmax[0]))
    s.press("start", gap=1.0)
    for _ in range(5): s.press("down", gap=0.4)
    s.press("cross", gap=0.8)
    s.press("left", gap=0.4); s.press("cross", gap=0.3)        # "Are You Sure?" -> Yes
    s.wait_for(lambda: s.word(FC) < 100, 40, "replay restarted")
    t = time.time(); last = 0; still = 0; d2 = 0; inv_seen = set(); ngt_seen = set()
    while time.time() - t < 120:
        f = s.word(FC); d2 = max(d2, s.word(DMG) & 0xFFFF)
        inv_seen.add(s.word(INV)); ngt_seen.add(s.word(NGHT))
        if f > 100 and not getattr(s, "_dbg", None):
            s._dbg = 1
            s.record("flags", detail="74 %x 6F80 %x 67E8 %x 6874 %x" % (s.word(0x80097074), s.word(0x80096F80), s.word(0x800967E8), s.word(0x80096874)))
        if f == last:
            still += 1
            if still > 40: break                                  # ~2 s without a game frame: replay over
        else:
            still = 0; last = f
        time.sleep(0.05)
    s.screenshot("replay_end")
    s.record("replay", detail="last frame %d of %d, inv %s ngt %s, max damage %d" % (last, f_rec, inv_seen, ngt_seen, d2))
    s.check("replay reaches the recorded end", last >= f_rec - 30, "last %d recorded %d" % (last, f_rec))
    s.check("replay car never near a wreck (invincible)", d2 < 10000, "max damage seen %d (play max %d; values are sampled mid-frame)" % (d2, dmax[0]))
