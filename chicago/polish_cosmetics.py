"""polish_cosmetics.py - C42: Driver 1 car_cosmetics rows for Chicago (Polish, 14.10.). Switch CHI_POLISH_COSMETICS=1.

Driver 1 (Ghidra pass 2): car_cosmetics 0x8009AF04 = 4 runtime rows of 100 B, filled by LoadCosmetics 0x80052620 from
the exe table 0x800853D8: 8 rows of 100 B per CITY (base 0 Miami, 8 SF, 0x10 Interview, 0x18 LA + Chicago, 0x20 NY,
0x28 Newtown); runtime row 0 = base + player car choice (0..3), rows 1-3 = base + 5, 6, 7 (the AI models).
Row layout: 8 SVECTORs (headLight, frontInd, backInd, brakeLight, revLight, policeLight, exhaust, smoke; D2 order),
wheelDisp[4] at +0x40, then 2 shorts (4096, 8 in every Driver 1 row; kept).

Driver 2 (REDRIVER2 cosmetic.c / cars.c): CHICAGO.LCF = 13 offsets + CAR_COSMETICS (236 B) per model: 9 SVECTORs
(+ fire), wheelDisp[4], extraInfo, powerRatio, cbYoffset, susCoeff, traction, wheelSize, ...

Wheel placement: D2 x = +-17 - disp.vx, z = -disp.vz, y = -wheelSize - disp.vy - susCompression + 14;
D1 x = +-25 - disp.vx (wheels 0/1 +, 2/3 -), z = -disp.vz, y = -(suspension + 50) - disp.vy.
Same picture: vx' = vx + 8 (wheels 0/1) / vx - 8 (2/3), vz' = vz, vy' = vy + wheelSize - 64 (suspension
conventions assumed equal at rest; D1's StepOneCar also reads the wheel rows, so the ride height must be checked).
Wheel size: D1 draws the tread at a fixed radius 0x65 (= D2's sizeScale = wheelSize * 1.4142); see SIZE_TABLE.

Output (`python polish_cosmetics.py [OUTDIR]`): chicago_cosmetics_day.bin / _night.bin = 8 rows x 100 B to replace
the exe table rows at 0x800853D8 + 0x18 * 100 while Chicago is loaded: rows 0-4 from the D1 car set of that
time of day (day Miami base 0, night LA base 0x18: the player cars are the set's), rows 5-7 = D2 cop, civ 0, civ 1.
"""
from __future__ import annotations

import os
import struct
import sys

EXE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "disc", "SLUS_008.42.orig")   # the app's copy of the player's D1 exe
TABLE = 0x800853D8
ROW = 100
BASES = {"miami": 0, "sf": 8, "la": 0x18, "ny": 0x20}
D2_FOR_ROW = {5: 3, 6: 0, 7: 1}         # exe rows base+5..7 (AI models) <- D2 models (polish_cars slot map 0<-3, 1<-0, 2<-1)
D1_RADIUS = 0x65


def enabled():
    return os.environ.get("CHI_POLISH_COSMETICS", "") == "1"


def exe_rows(base: int):
    exe = open(EXE, "rb").read()
    t = struct.unpack_from("<I", exe, 0x18)[0]
    o = 0x800 + (TABLE & 0x1FFFFFFF) - (t & 0x1FFFFFFF) + base * ROW
    return [exe[o + k * ROW: o + (k + 1) * ROW] for k in range(8)]


def rows_needed() -> int:
    """8 exe cosmetics rows, 10 with six resident models (LoadCosmetics reads base + 5..9, exe_patches c42m)."""
    import polish_cars as pc
    return 10 if (pc.enabled() and pc.SIX) else 8


def d2_models(lcf: bytes):
    offs = struct.unpack_from("<13i", lcf, 0)
    out = {}
    for m, o in enumerate(offs):
        if 0 < o < len(lcf):
            sv = [struct.unpack_from("<4h", lcf, o + 8 * i) for i in range(13)]
            sh = struct.unpack_from("<6h", lcf, o + 104)
            cog = struct.unpack_from("<3h", lcf, o + 220)
            w = sv[9:13]
            dz = -int((w[0][2] + w[1][2] - 14) / 2)      # D2 FixCarCos (handling.c): wheels centred, C division
            out[m] = dict(lights=sv[:9], wheels=w, wheelSize=sh[5], susCoeff=sh[3], fix_dz=dz, powerRatio=sh[1],
                          cog=(cog[0], cog[1], cog[2] - dz))   # UpdateCarPoints: cog.vz -= delta.vz
    return out


def body_shift(lcf: bytes, m: int):
    """C42 r3 (17.10.): Driver 2 draws the body at where + R * cog (cars.c DrawCarObject) with FixCarCos's cog; Driver 1
    draws it at the car origin -> the converter moves the body vertices by (cog.x, cog.z) (D2 units; the height stays
    the ride-height rule's)."""
    d = d2_models(lcf).get(m)
    return (d["cog"][0], d["cog"][2]) if d else (0, 0)


RIDE = os.environ.get("CHI_POLISH_COSMETICS_RIDE", "body")     # "body": ride height from the body's depth (default)
CLEARANCE = int(os.environ.get("CHI_POLISH_COSMETICS_CLEAR", "34"))   # D1 cars: 164 ride - ~130 body depth


def wheel_vy(d2: dict) -> int:
    """wheelDisp.y for Driver 1. D1's StepOneCar sets the ride height from it (D1 cars: -165 -> y 164 with
    bodies ~130 deep, i.e. ~34 clearance). "body": -(body depth + CLEARANCE) so a D2 body (depth = lowest
    vertex below the origin) rides like a D1 car; "visual": the D2 wheel-centre match (vy + wheelSize - 64,
    first version: bodies sank, y ~77)."""
    if RIDE == "visual":
        return d2["wheels"][0][1] + d2["wheelSize"] - 64
    return -(d2["depth"] + CLEARANCE) + (wheel_road(d2) if WHEELROAD else 0)


# C144 (Analyst 30.10., NOTES "C144 wheel checkup"): Driver 1 draws every wheel centre D1_WHEEL_Y = 73 above the road
# (-(susp + 50) - disp.vy with the ride height -disp.vy - 1, rest susp ~24), so a tyre of radius R = round(wheelSize x 1.32)
# floats 73 - R (Havana mini +29) or sinks R - 73 (fire engine -46). Infrastructure draws the wheels dy = 73 - R lower
# (draw only, same R); CHI_POLISH_WHEELROAD=1 moves the body with them: ride row disp.vy += 73 - R (the drawn wheel stays
# where Driver 1 puts it, origin + body go down by 73 - R), and Driver 2's wheel-to-body relation for EVERY model (the
# d2wheel body extras, anchored on the civilians' mean like cheats 6, not only models 8-12). Data and engine go together:
# without the engine offset small-wheeled bodies sink onto their wheels.
WHEELROAD = os.environ.get("CHI_POLISH_WHEELROAD", "") == "1"
D1_WHEEL_Y = 73


def wheel_road(d2: dict) -> int:
    """C144: 73 - R (D1 units), R = the drawn tyre radius (= .whl.bin, LCF wheelSize x polish_cars.SCALE)."""
    import polish_cars as pc
    return D1_WHEEL_Y - int(round(d2["wheelSize"] * pc.SCALE))


RIDE_MODELS = os.environ.get("CHI_RIDE_MODELS", ",".join(str(m) for m in range(13)) if WHEELROAD else "8,9,10,11,12")   # R34: D2 ride relative to the civilians


_RIDE = {}
SPC_RIDE = os.environ.get("CHI_POLISH_SPCRIDE", "")   # "d2wheel": Driver 2 wheel-in-arch placement (cheats 6)


def ride_extras() -> dict:
    """R34/R35: D2 model -> extra clearance (D1 units) of the listed models: their Driver 2 clearance minus the civilians'
    mean (models 0-3), x the car scale. R35 (user: buses spawned high and bounced): applied as a BODY shift upwards
    (polish_cars.cog_shift dy), not to the wheel y: the wheels / ride height (and so the spawn height) stay the
    civilians', only the body sits higher above its wheels, like Driver 2's bus."""
    if _RIDE:
        return _RIDE
    import inputs, polish_cars as pc
    from levfile import Lev
    import models as M
    from cityprofile import P as _CITY
    d2 = d2_models(inputs.read(_CITY.lcf))
    cm = Lev.parse(inputs.read(_CITY.lev_day)).loadtime.get(28).data
    ents = pc._entries(cm)
    ymax = {}
    for m in d2:
        if ents[m][0] != -1:
            mod = M.Model.parse(-1, pc._model_bytes(cm, ents[m][0]))
            ymax[m] = max(struct.unpack_from("<h", mod.data, mod.vertices + 8 * i + 2)[0] for i in range(mod.num_vertices))
    # cheats 6 (user, 25.10.: bus tyres look too small = a gap above them in the arch): CHI_POLISH_SPCRIDE=d2wheel raises
    # the body only by the difference of Driver 2's wheel-centre-to-body-bottom relation (clearance - wheelSize) to the
    # civilians', so the arch sits round the bigger wheel like in Driver 2 (bus +28 instead of +59); default: R34 rule.
    rel = (lambda m: d2_clearance(d2[m], ymax[m]) - d2[m]["wheelSize"]) if SPC_RIDE == "d2wheel" else           (lambda m: d2_clearance(d2[m], ymax[m]))
    ref = [rel(m) for m in (0, 1, 2, 3) if m in ymax]
    ref = sum(ref) / len(ref) if ref else 0.0
    for m in (int(v) for v in RIDE_MODELS.split(",") if v.strip()):
        if m in ymax:
            _RIDE[m] = int(round(pc.SCALE * (rel(m) - ref)))
    _RIDE.setdefault(-1, 0)
    return _RIDE


def d2_clearance(d2: dict, ymax: float) -> float:
    """R34: Driver 2's ground clearance (D2 units): cars.c DrawCarWheels puts the wheel centre at -wheelSize - wheelDisp.y
    + 14 (no suspension load) in the body frame, the body origin at cog -> wheel bottom 14 - wheelDisp.y, body bottom
    cog.y + lowest vertex. Civilians 41-51, van 56, special 9 74, bus 92, fire engine 98."""
    return 14 - d2["wheels"][0][1] - d2["cog"][1] - ymax


THRUST = os.environ.get("CHI_R35_THRUST_ROWS", "1") != "0"


def thrust_scale(d2: dict) -> int:
    """R35 (user: the player car is faster than in Driver 2): Driver 2's accelerating thrust FIXEDH(powerRatio * 4915) x the
    world scale over Driver 1's 7200, in 1/4096 (exe C35T: thrust = thrust * THRS >> 12): 3691 for powerRatio 4096. The
    player choice's cosmetics row keeps it in its unused tail short (+96; Driver 1's rows hold 4096 there, never read)."""
    import polish_cars as pc
    pr = d2.get("powerRatio") or 4096
    return max(1024, min(8192, int(round(pr * 4915 * pc.SCALE / 7200.0))))


# C145 (user 30.10.: the Chicago bus's tail lights sunk into the body, headlights in front of it): Driver 2 draws the
# body at where + R (cog + v) and every light at where + R (light + cog) (cosmetic.c), so a light sits where the model
# says. Our body vertices carry the cog (x, z) and the ride raise (polish_cars.cog_shift); the light rows did not -> off
# by -cog (bus cog.vz 117 x 1.32). CHI_POLISH_LIGHTCOG=1: the 8 light / exhaust / smoke points get the body's shift too.
LIGHTCOG = os.environ.get("CHI_POLISH_LIGHTCOG", "") == "1"


def light_shift(m: int):
    """(dx, dy, dz) D1 units added to model m's light points = its body shift (0 without CHI_POLISH_LIGHTCOG=1)."""
    if not LIGHTCOG:
        return (0, 0, 0)
    import polish_cars as pc
    sh = pc.cog_shift(m)
    return (sh[0], sh[2] if len(sh) > 2 else 0, sh[1])


def d1_row(d2: dict, tail: bytes, f: float = 1.0, sh=(0, 0, 0)) -> bytes:
    """f: model scale (C57, polish_cars.SCALE): positions scale with the body; the wheel x keeps D1's own
    +-25 offset (D2 x = +-17 - vx -> D1 x = +-25 - vx' with x' = f * x). sh: light_shift (C145)."""
    out = bytearray()
    r = lambda v: max(-32768, min(32767, int(round(v))))
    for vx, vy, vz, pad in d2["lights"][:8]:           # D2 order = D1 order; 'fire' has no D1 slot
        out += struct.pack("<4h", r(vx * f + sh[0]), r(vy * f + sh[1]), r(vz * f + sh[2]), 0)
    for i, (vx, vy, vz, pad) in enumerate(d2["wheels"]):
        sg = 1 if i < 2 else -1
        vz = vz + d2.get("fix_dz", 0)                 # C42 r3: D2's FixCarCos wheel centring
        out += struct.pack("<4h", r(f * vx + sg * (25 - 17 * f)), wheel_vy(d2), r(vz * f), 0)
    return bytes(out) + tail


def row_map() -> dict:
    """exe cosmetics row -> D2 model. CHI_POLISH_D2CARS=1 (all Driver 2, C42 engine step): rows 0-3 = the player
    choices (slots 5-8), rows 5-7 = AI resident models 1-3 (slots 0-2); else the mixed set's rows 5-7."""
    import polish_cars as pc
    m = pc.slot_map()
    if pc.enabled():
        out = {r: m[5 + r] for r in range(4) if m.get(5 + r) is not None}
        out.update({5 + k: m[k] for k in pc.AI_SLOTS if m.get(k) is not None})   # C42 r3 (b): rows 8-9 = models 4-5
        return out
    return dict(D2_FOR_ROW)


def scale() -> float:
    """C57: the D2 bodies are scaled by polish_cars.SCALE in CHI_POLISH_D2CARS=1 (and mixed) builds."""
    import polish_cars as pc
    return pc.SCALE if (pc.enabled() or os.environ.get("CHI_POLISH_D2CARS") == "mixed") else 1.0


def body_depths(lev_path: str, models=None) -> dict:
    """D2 model -> lowest body vertex below the origin (clean model)."""
    import polish_cars as pc
    from levfile import Lev
    import models as M
    cm = Lev.parse(open(lev_path, "rb").read()).loadtime.get(28).data
    ents = pc._entries(cm)
    out = {}
    for m in (set(row_map().values()) if models is None else set(models)):
        mod = M.Model.parse(-1, pc.scale_model(pc._model_bytes(cm, ents[m][0]), scale()))
        out[m] = max(struct.unpack_from("<h", mod.data, mod.vertices + 8 * i + 2)[0] for i in range(mod.num_vertices))
    return out


def build(lcf_path: str, outdir: str, lev_path: str = None, suffix: str = ""):
    import inputs
    lev_path = lev_path or inputs.path(__import__("cityprofile").P.lev_day)
    d2 = d2_models(open(lcf_path, "rb").read())
    for m, dep in body_depths(lev_path).items():
        d2[m]["depth"] = dep
    files = {}
    for tod, cset in (("day", "miami"), ("night", "la")):
        rows = exe_rows(BASES[cset])
        rows += [rows[5]] * (rows_needed() - len(rows))   # rows 8-9 (models 4-5): a civilian row's tail as the template
        new = list(rows)
        for r, m in row_map().items():
            tail = rows[r][96:100]
            if r < 4 and THRUST:                   # R35: player choices carry their thrust scale (exe C35T, plugin THRS)
                tail = struct.pack("<h", thrust_scale(d2[m])) + tail[2:]
            new[r] = d1_row(d2[m], tail, scale(), light_shift(m))
        path = os.path.join(outdir, "var_polish_cosmetics_chicago_%s%s.bin" % (tod, suffix))
        open(path, "wb").write(b"".join(new))
        files[tod] = path
    size = [(m, d2[m]["wheelSize"], round(d2[m]["wheelSize"] * 1.4142), D1_RADIUS) for m in (3, 0, 1)]
    return files, size


def special_row(lcf_path: str, lev_path: str, m: int, tail: bytes) -> bytes:
    """M3 (Havana): the 100-B cosmetics row of a special that is not a player choice (Chicago's four specials are the
    four player cars; Havana's model 11 is not): built like a player row, tail (+ thrust scale) from a player row."""
    d2 = d2_models(open(lcf_path, "rb").read())
    for mm, dep in body_depths(lev_path, {m}).items():
        d2[mm]["depth"] = dep
    if THRUST:
        tail = struct.pack("<h", thrust_scale(d2[m])) + tail[2:]
    return d1_row(d2[m], tail, scale(), light_shift(m))


if __name__ == "__main__":
    outdir = sys.argv[1] if len(sys.argv) > 1 else "work"
    import inputs
    files, size = build(inputs.path(__import__("cityprofile").P.lcf), outdir, suffix=sys.argv[2] if len(sys.argv) > 2 else "")
    print(files)
    print("D2 model, wheelSize, D2 tread radius (wheelSize*1.4142), D1 fixed radius:")
    for row in size:
        print("  ", row, "-> D1 draws %.0f%% too big" % (100.0 * (row[3] / row[2] - 1)))
