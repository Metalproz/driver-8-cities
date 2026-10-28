"""C108: Nightmare pursuers over a long drive (user: every car chases). CITY (miami), DRIVE s (60), INV on. Every 2 s:
AI records present / pursuing (state 4) / traffic (2, 3) / other, chaser slots in use, spawn conversions counter."""
import collections, os, time
SESSION = dict(day="var_polish_specdmg2_day.lev", night="var_polish_specdmg2_night.lev", s4=True)


def sample(s):
    rec = s.ram(0x80098950, 0x50 * 24)
    st = collections.Counter(rec[i * 0x50 + 1] for i in range(24) if rec[i * 0x50 + 1])
    slots = s.word(0x800933D4)
    used = sum(1 for k in range(24) if s.word(slots + k * 0x7A8 + 0x78C))
    lane = sum(1 for i in range(24) if rec[i * 0x50 + 1] == 4 and rec[i * 0x50 + 8])
    import struct as _st
    st2 = [(rec[i * 0x50 + 5], _st.unpack("<h", s.ram(0x8009B230 + 0x18C * i + 0x17C, 2))[0]) for i in range(24) if rec[i * 0x50 + 1] in (2, 3)]
    return dict(st2=st2[:8], present=sum(st.values()), st=dict(st), slots=used, conv=s.word(0x800933E8), cops=s.word(0x80097764), lane4=lane)


def run(s):
    s.poke32(0x8009681C, 1); s.poke32(0x800933C8, 1)
    s.menu("take_a_ride/" + os.environ.get("CITY", "miami")); s.wait_world(what="start")
    out = []
    t0 = time.time(); want = s.car(0)[3]; k = 0
    while time.time() - t0 < float(os.environ.get("DRIVE", "60")):
        p0 = s.pos()
        s.drive(3.0, want if k % 3 else None); k += 1
        o = sample(s); p1 = s.pos(); o["moved"] = int(abs(p1[0] - p0[0]) + abs(p1[2] - p0[2]))
        out.append(o)
    s.record("series", detail="%s" % out)
    half = sorted(o["st"].get(4, 0) for o in out[len(out) // 2:])
    s.check("pursuers stay high (median of the second half >= 15)", half and half[len(half) // 2] >= 15, "%s" % [o["st"].get(4, 0) for o in out])
