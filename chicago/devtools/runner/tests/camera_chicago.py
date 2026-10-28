"""Build-dev regression 47 (2): the chase camera in Chicago must stay behind the car (no jumps); Miami as reference."""
import math, os, statistics, time

SESSION = dict(day=os.environ.get("CAM_DAY", "var_polish_opt2d_day.lev"), night=os.environ.get("CAM_NIGHT", "var_polish_opt2d_night.lev"),
               s4=True)
CAM = 0x8009D768
ROUTE = ((-101562, 106946), (0, 1))


def sample(s, secs, want):
    rows = []

    def tick(ss):
        x, y, z, h, _ = ss.car(0)
        raw = ss.ram(CAM, 12)
        cx, cy, cz = [int.from_bytes(raw[4 * k:4 * k + 4], "little", signed=True) for k in range(3)]
        dist = math.hypot(x - cx, z - cz)
        behind = math.degrees((math.atan2(x - cx, z - cz) - h + math.pi) % (2 * math.pi) - math.pi)
        rows.append((dist, cy - y, behind))
        return False
    s.drive(secs, want, tick)
    return rows


def summary(rows):
    d = [r[0] for r in rows]; dy = [r[1] for r in rows]; b = [abs(r[2]) for r in rows]
    return {"n": len(rows), "dist": (round(min(d)), round(statistics.median(d)), round(max(d))),
            "dy": (min(dy), round(statistics.median(dy)), max(dy)), "angle_p90": round(sorted(b)[int(0.9 * len(b))]),
            "jumps": sum(1 for a, c in zip(rows, rows[1:]) if abs(a[1] - c[1]) > 250 or abs(a[0] - c[0]) > 400)}


def run(s):
    city = os.environ.get("CAM_CITY", "chicago")
    s.menu("take_a_ride/" + city)
    want = None
    if city == "chicago":
        (x2, z2), (dx, dz) = ROUTE
        want = math.atan2(dx, dz)
        s.pose(int(x2 * 1.32 + 157724), int(z2 * 1.32 - 87099), want)
    rows = sample(s, 40, want)
    sm = summary(rows)
    s.screenshot(city + "_drive")
    s.check(city + " camera steady", sm["dy"][2] - sm["dy"][0] < 400, str(sm))
