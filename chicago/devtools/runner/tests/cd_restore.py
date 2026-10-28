"""C95: after a savestate restore the runtime's CD boost must not deliver a sector before the guest read the previous
one (cheats 5 crash: 330142 came 6833 cycles after 330141, the texture-page load parsed a shifted page). In Chicago:
save slot 7 while driving, then N times: restore, drive DRIVE s at once (area streaming reads during the 180-vblank
boost); checks: no sector gap < 20000 cycles after the restores (cdrom_timing_dump), alive, drives."""
import os, re, socket, time
SESSION = dict(day="var_polish_specdmg2_day.lev", night="var_polish_specdmg2_night.lev", s4=True)


def raw(port, line):
    s = socket.create_connection(("127.0.0.1", port), timeout=40)
    s.sendall(line.encode() + b"\n"); buf = b""
    while not buf.endswith(b"\n"):
        c = s.recv(1 << 20)
        if not c: break
        buf += c
    return buf.decode()


def records(port):
    t = raw(port, '{"id":4,"cmd":"cdrom_timing_dump","count":4096}')
    return [(int(m.group(1)), int(m.group(2)), int(m.group(3))) for m in
            re.finditer(r'"seq":(\d+),"lba":(\d+),"frame":\d+,"due":(\d+)', t)]


def run(s):
    # Take a Ride -> Chicago up to the last confirm (session.menu's steps), save there; then N times: restore + confirm,
    # so the whole level load runs inside the 180-vblank post-restore CD boost
    s.press("triangle"); time.sleep(2)
    for b in ["right"] * 5 + ["cross"]:
        s.press(b)
    time.sleep(1.5)
    for _ in range(7):
        s.press("down", gap=0.6)
    s.press("cross", gap=1.0); time.sleep(1); s.press("cross"); time.sleep(3)
    raw(s.port, '{"id":2,"cmd":"savestate","op":"save","slot":7}'); time.sleep(1.5)
    seq0 = max((q for q, _, _ in records(s.port)), default=0)
    allrec = {}
    for k in range(int(os.environ.get("N", "3"))):
        raw(s.port, '{"id":3,"cmd":"savestate","op":"load","slot":7}'); time.sleep(0.3)
        s.press("cross")
        got = {}
        t0 = time.time()
        while time.time() - t0 < 20:                     # collect while the load runs (the ring keeps 1024 sectors)
            for x in records(s.port):
                if x[0] > seq0: got[x[0]] = x
            if s.in_level() and time.time() - t0 > 4: break
            time.sleep(0.5)
        allrec.update(got)
    recs = [allrec[q] for q in sorted(allrec)]
    gaps = [(b[2] - a[2], b[1]) for a, b in zip(recs, recs[1:]) if b[1] == a[1] + 1 and b[2] > a[2]]
    short = sorted(g for g in gaps if g[0] < 200000)   # 2x period 225792; the old boost cut it to <= 4096 after a vblank
    lvl = [g for g in short if g[1] >= 330000]
    s.check("sector cadence intact after restores (no level-file gap < 200000)", not lvl,
            "%d sectors after the restores, %d gaps; short level %d %s; short other %d lbas %s" % (
                len(recs), len(gaps), len(lvl), lvl[:6], len(short) - len(lvl), sorted(set(g[1] for g in short if g[1] < 330000))[:12]))
    s.wait_world(what="start")
    p0 = s.pos(); s.hold("cross"); time.sleep(3); s.release(); p1 = s.pos()
    s.check("drives", abs(p1[0] - p0[0]) + abs(p1[2] - p0[2]) > 1000, "moved %d" % (abs(p1[0] - p0[0]) + abs(p1[2] - p0[2])))
    s.check("alive", s.alive(2.0))
