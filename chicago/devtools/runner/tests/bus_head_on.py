"""C82: ram the special (bus) head-on at speed; the player must not be spun away, the bus must stay aligned.
Single rams vary with the moving bus (off-axis hits, 4..42 deg on any exe): the checks use the median of 4 rams."""
import math, statistics, time

SESSION = dict(day="var_polish_opt2d_day.lev", night="var_polish_opt2d_night.lev", s4=True)


def run(s):
    s.menu("take_a_ride/chicago")
    yaws, byaws = [], []
    for attempt in range(4):
        bi = None
        s.wait_for(lambda: s.find_model(5) is not None, 60, "a special (model 5) on the road")
        bi = s.find_model(5)
        bx, by, bz, bh, _ = s.car(bi)
        fx, fz = math.sin(bh), math.cos(bh)
        px, pz = bx + fx * 2600, bz + fz * 2600
        s.pose(int(px), int(pz), math.atan2(bx - px, bz - pz), settle=0.3)
        h0, b0 = s.car(0)[3], s.car(bi)[3]
        yaw, byaw, closest = 0.0, 0.0, 1e9
        s.hold("cross"); t = time.time()
        while time.time() - t < 3.0:
            x, y, z, h, _ = s.car(0); qx, qy, qz, qh, _ = s.car(bi)
            yaw = max(yaw, abs(math.degrees((h - h0 + math.pi) % (2 * math.pi) - math.pi)))
            byaw = max(byaw, abs(math.degrees((qh - b0 + math.pi) % (2 * math.pi) - math.pi)))
            closest = min(closest, math.hypot(x - qx, z - qz))
            time.sleep(0.05)
        s.release()
        s.screenshot("ram%d" % attempt)
        s.record("ram", detail="ram %d: player yaw %.0f deg, bus yaw %.0f deg, closest %d" % (attempt, yaw, byaw, closest))
        yaws.append(yaw); byaws.append(byaw)
        time.sleep(2)
    s.check("player yaw median", statistics.median(yaws) < 20, "player yaws %s" % [round(y) for y in yaws])
    s.check("bus yaw median", statistics.median(byaws) < 25, "bus yaws %s" % [round(y) for y in byaws])
