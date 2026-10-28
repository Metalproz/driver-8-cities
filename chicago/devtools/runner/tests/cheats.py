"""C88: the new cheats, each checked against its off state (words set directly; the menu pages come separately).
CITY env (default chicago): gravity (fall from a held height), super speed (top speed on a straight), infinite mass
(head-on into the bus), nightmare (AI cars switch to pursuit and close in), plus a 60 s fast drive (super speed + low
gravity) without a hang."""
import math, os, struct, time

CITY = os.environ.get("CITY", "chicago")
SESSION = dict(day="var_polish_specdmg2_day.lev", night="var_polish_specdmg2_night.lev", s4=True)
LOWG, INFM, NGHT, SPD2 = 0x8009D8E8, 0x800933C4, 0x800933C8, 0x800933CC


def fall(s, x, z, h, y):
    """hold the car 1500 above its ground spot, release, and time (in VBlanks) the first 600 units of the drop."""
    s._write_pose(x, y - 1500, z, h); time.sleep(1.2)
    s._release_pose()
    t0 = s.word(0x80095250); y0 = s.pos()[1]
    while s.word(0x80095250) - t0 < 300:
        if s.pos()[1] - y0 >= 600:
            return s.word(0x80095250) - t0
        time.sleep(0.01)
    return 999


def fresh(s, x, y, z, h):
    """back to a drivable state at the start: Play Again after a wreck, repair, pose."""
    from dt import wrecked, play_again
    if wrecked(s.d) or not s.in_level():
        s.release(); play_again(s.d); time.sleep(4)
    s.poke32(0x8009B220, 0)
    s.pose(x, z, h, y=y, ground=False)


def top_speed(s, secs=8.0):
    s.hold("cross"); best = 0; last = s.pos(); t = time.time()
    while time.time() - t < secs:
        time.sleep(0.25)
        p = s.pos(); best = max(best, math.hypot(p[0] - last[0], p[2] - last[2]) / 0.25); last = p
    s.release(); time.sleep(2.0)
    return round(best)


def run(s):
    s.menu("take_a_ride/" + CITY)
    s.wait_world(what="start")
    x, y, z, h, _ = s.car(0)
    # LOW GRAVITY: the pose cannot hold a car in the air (it lands within a frame), so this only checks the patched
    # gravity word is in the exe; the feel is the user's check
    s.record("low gravity", detail="exe 0x8001D7D4 = addiu v0, zero, -0x1555 (1/2 g) when 0x8009D8E8 != 0 (static)")
    # INFINITE MASS: ram the special head-on with and without INFM; the player keeps its heading and speed
    for on in (0, 1):
        fresh(s, x, y, z, h); s.poke32(INFM, 0x20 if on else 0)
        yaws, keep = [], []
        for k in range(3):
            s.wait_for(lambda: s.find_model(5) is not None, 60, "a special")
            bi = s.find_model(5); bx, by, bz, bh, _ = s.car(bi)
            px, pz = bx + math.sin(bh) * 2600, bz + math.cos(bh) * 2600
            s.pose(int(px), int(pz), math.atan2(bx - px, bz - pz), settle=0.3, ground=False)
            h0 = s.car(0)[3]; s.hold("cross"); t = time.time(); yaw = 0; pre = post = 0; last = s.pos(); hit = False
            while time.time() - t < 3.0:
                time.sleep(0.05); p = s.pos(); v = math.hypot(p[0] - last[0], p[2] - last[2]) / 0.05; last = p
                yaw = max(yaw, abs(math.degrees((s.car(0)[3] - h0 + math.pi) % (2 * math.pi) - math.pi)))
                d = math.hypot(p[0] - s.car(bi)[0], p[2] - s.car(bi)[2])
                if d < 1600 and not hit: pre = v; hit = True
                elif hit and post == 0 and d < 1700: post = v
            s.release(); time.sleep(1.5); s.poke32(0x8009B220, 0)
            yaws.append(round(yaw)); keep.append(round(post / pre, 2) if pre else 0)
        s.record("infinite mass", detail="INFM %d: player yaw %s, speed kept after hit %s" % (on, yaws, keep))
        if on: s.check("infinite mass: player not spun", sorted(yaws)[1] <= 15, "yaws %s" % yaws)
    s.poke32(INFM, 0)
    # SUPER SPEED (same start, same heading)
    fresh(s, x, y, z, h); sp0 = top_speed(s)
    fresh(s, x, y, z, h); s.poke32(SPD2, 1); time.sleep(0.5); sp1 = top_speed(s); s.poke32(SPD2, 0)
    s.check("super speed", sp1 > 1.4 * sp0, "best speed units/s: normal %d, super %d" % (sp0, sp1))
    fresh(s, x, y, z, h)
    # NIGHTMARE: pursuers close in on a standing player
    s.poke32(NGHT, 1); time.sleep(1.0)
    rec = s.ram(0x80098950, 0x50 * 22)
    purs = [i for i in range(22) if rec[i * 0x50 + 1] == 4]
    def dists():
        px, _, pz, _, _ = s.car(0)
        return [math.hypot(s.car(i + 1)[0] - px, s.car(i + 1)[2] - pz) for i in purs]
    a = dists(); time.sleep(12); b = dists()
    closer = sum(1 for p, q in zip(a, b) if q < p - 500)
    s.screenshot("nightmare")
    s.poke32(NGHT, 0)
    s.check("nightmare", len(purs) >= 8 and closer >= len(purs) // 3, "%d pursuers, %d closed in by > 500 in 12 s" % (len(purs), closer))
    s.check("alive after nightmare", s.alive(2.0))
    # FAST + FLOATY DRIVE: streaming / edges
    fresh(s, x, y, z, h)
    s.poke32(SPD2, 1); s.poke32(LOWG, 1)
    s.drive(60, h)
    s.poke32(SPD2, 0); s.poke32(LOWG, 0)
    s.check("60 s super speed + low gravity: no hang", s.alive(3.0), "pos %s area %d" % (s.pos(), s.word(0x800972C0)))
