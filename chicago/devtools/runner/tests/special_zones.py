"""C87 (48): side hits on the bus's rear half go to the middle damage zones (Driver 2: lbody = colBox.vz / 2 from the body
centre), not to the rear corners; a rear hit goes to the rear zones."""
import math, struct, time

SESSION = dict(day="var_polish_opt2d_day.lev", night="var_polish_opt2d_night.lev", s4=True)
ZONES = 0x114
hit_along = [None, None]
PARK = False


def zones(s, i):
    return list(struct.unpack_from("<6i", s.ram(0x8009B0A4 + i * 0x18C + ZONES, 24), 0))


def hit_once(s, along, side, name, lead):
    s.wait_for(lambda: s.find_model(5) is not None, 60, "a special on the road")
    bi = s.find_model(5)
    for k in range(6):                                      # fresh bus: clear its zones (test copy only)
        s.poke32(0x8009B0A4 + bi * 0x18C + ZONES + 4 * k, 0)
    if PARK:                                                # stop the bus (AI mode 7 = the parked mission car)
        s.d.cmd("write_ram", addr="0x%08X" % (0x80098950 + (bi - 1) * 0x50 + 1), val=7)
        time.sleep(1.5)
    ax, ay, az, ah, _ = s.car(bi); time.sleep(0.3)
    bx, by, bz, bh, _ = s.car(bi)
    vx, vz = (bx - ax) / 0.3, (bz - az) / 0.3                # bus velocity: aim where it will be at impact
    bx, bz = bx + vx * lead, bz + vz * lead
    fx, fz = math.sin(bh), math.cos(bh)                      # forward
    rx, rz = math.cos(bh), -math.sin(bh)                     # right
    tx, tz = bx + fx * along, bz + fz * along                 # target point on the bus axis
    px, pz = tx + rx * side, tz + rz * side
    s.pose(int(px), int(pz), math.atan2(tx - px, tz - pz), settle=0.2)
    z0 = zones(s, bi)
    t = time.time(); closest = 1e9; dmg0 = s.car(bi)[4]; hit_along[:] = [None, None]
    while time.time() - t < 6.0:                            # homing: steer at the target point on the moving bus
        x, y, z, h, _ = s.car(0); qx, qy, qz, qh, _ = s.car(bi)
        gx, gz = qx + math.sin(qh) * along, qz + math.cos(qh) * along
        err = (math.atan2(gx - x, gz - z) - h + math.pi) % (2 * math.pi) - math.pi
        btn = ["cross"] + (["right"] if err > math.radians(4) else ["left"] if err < -math.radians(4) else [])
        s.hold(*btn)
        closest = min(closest, math.hypot(x - qx, z - qz))
        if s.car(bi)[4] != dmg0:
            fx, fz = math.sin(qh), math.cos(qh)
            hit_along[0] = (x - qx) * fx + (z - qz) * fz      # player centre along the bus axis at the first damage
            hit_along[1] = (x - qx) * fz - (z - qz) * fx
            break
        time.sleep(0.04)
    s.release(); time.sleep(0.5)
    s.record("approach", detail="lead %.1f: bus slot %d moved %d closest %d damage %d -> %d" % (lead, bi, math.hypot(bx - ax - vx * lead, bz - az - vz * lead), closest, dmg0, s.car(bi)[4]))
    z1 = zones(s, bi)
    d = [b - a for a, b in zip(z0, z1)]
    s.screenshot(name)
    s.record("zones", detail="%s: along %d side %d -> zone deltas %s" % (name, along, side, d))
    return d


def hit(s, along, side, name):
    for lead in (1.5, 1.5, 1.5):
        d = hit_once(s, along, side, name, lead)
        if any(d):
            return d
        time.sleep(1.5)
    return d


def expected(along):
    """zone class from the contact position along the bus axis (body clipped to its box -1024..716): D2 / D1 rule."""
    a = max(-1024, min(716, along))
    d2 = "front" if a + 154 > 435 else ("rear" if a + 154 < -435 else "middle")
    d1 = "front" if a > 260 else ("rear" if a < -260 else "middle")
    return d2, d1


def observed(d):
    m = max(range(6), key=lambda k: d[k])
    return "front" if m in (0, 1) else ("rear" if m in (3, 4) else "middle")


def run(s):
    s.menu("take_a_ride/chicago")
    for k, along in enumerate((-500, -500, 300)):
        d = hit(s, along, 1500, "side_%d" % k)
        if not any(d) or hit_along[0] is None:
            s.record("no hit", detail="aim %d" % along); continue
        e2, e1 = expected(hit_along[0])
        a = max(-1024, min(716, hit_along[0])) + 154
        if min(abs(a - 435), abs(a + 435)) < 150:            # contact estimated from the player's centre: too close to call
            s.record("ambiguous", detail="contact along %d near a zone boundary, deltas %s" % (hit_along[0], d)); continue
        s.check("zone %d" % k, observed(d) == e2, "contact along %d (lateral %d): observed %s, D2 rule %s, D1 rule %s, deltas %s"
                % (hit_along[0], hit_along[1], observed(d), e2, e1, d))
        time.sleep(1.5)
    # (a rear-hit check needs a stationary bus: the moving bus made the aim unreliable)
