"""M3 Havana drowning trace: pose at a harbour shore (posed one region away first so the target region's height map is
loaded), drive in, and log every 0.1 s: car x / y / z, the FindSurfaceD2 sea-wheel byte 0x800970F8, the drowning
countdown 0x80097004 (25) and timer 0x800970DC (100), the car's raw y 0x8009B170; then count hits of code addresses
(WATCH, cyc_watch) while the car is in the water. SPOT env 'x,z,heading4096,secs', CITY env (havana)."""
import math, os, re, socket, time
SESSION = dict(day="var_polish_cheats6_day.lev", night="var_polish_cheats6_night.lev", s4=True)


def hits(s, pc):
    s.d.cmd("cyc_watch", pc=pc, n=16)
    time.sleep(1.0)
    with socket.create_connection(("127.0.0.1", s.port), timeout=20) as so:
        so.sendall(b'{"id":1,"cmd":"cyc_watch_dump"}' + bytes([10]))
        buf = b""
        while b"]}" not in buf:
            c = so.recv(1 << 16)
            if not c:
                break
            buf += c
    m = re.search(rb'"hits":(\d+)', buf)
    return m.group(1).decode() if m else "?"


def run(s):
    sg = lambda v: v - (1 << 32) if v >> 31 else v
    s.poke32(0x8009681C, 1)
    city = os.environ.get("CITY", "havana")
    s.menu("take_a_ride/" + city); s.wait_world(what=city)
    x, z, h, secs = (float(v) for v in os.environ.get("SPOT", "367500,-196500,1024,12").split(","))
    x, z, h = int(x), int(z), int(h)
    s.pose(x, z, h * 2 * math.pi / 4096)
    s.pose(x - 90000, z, h * 2 * math.pi / 4096, ground=False)
    s.pose(x, z, h * 2 * math.pi / 4096)
    s.hold("cross")
    t0, rows, last = time.time(), [], None
    while time.time() - t0 < secs:
        p = s.pos()
        row = (int(p[0]), int(p[1]), int(p[2]), s.ram(0x800970F8, 1)[0], sg(s.word(0x80097004)), sg(s.word(0x800970DC)),
               sg(s.word(0x8009B170)))
        if last is None or row[3:6] != last[3:6] or abs(row[1] - last[1]) > 40:
            rows.append((round(time.time() - t0, 1),) + row)
        last = row
        time.sleep(0.1)
    for pc in os.environ.get("WATCH", "0x8003A698,0x8003ADC8,0x8005265C,0x8008A340").split(","):
        s.record("watch", detail="%s: hits %s" % (pc, hits(s, pc)))
    s.release()
    s.screenshot("end")
    s.record("words", detail="BANDW %d RANGE %d sea %d 9687C %d 96897 %d 9688C %d" % (sg(s.word(0x80093624)), sg(s.word(0x800978A8)),
             sg(s.word(0x80097888)), sg(s.word(0x8009687C)), s.ram(0x80096897, 1)[0], sg(s.word(0x8009688C))))
    for r in rows[:60]:
        s.record("trace", detail="t %.1f x %d y %d z %d seawheel %d countdown %d timer %d rawy %d" % r)
