"""c129_ref.py - Python reference model of Driver 2's civ-car route nodes (C129, Analyst 28.10.).

A line-by-line model of REDRIVER2 src_rebuild/Game/C/civ_ai.c on a D2 city's road lumps
(STRAIGHTS2 40, CURVES2 41, JUNCTIONS2_NEW 43):
  InitNodeList / InitCivState      first node from the spawn position, lane from the offset
  GetNodePos                       lane point on straights (sideShift) and curves (radius)
  CreateNewNode                    13-entry node ring: 1024-unit steps on straights, 128/64/32 angle
                                   steps on curves, segment ends, left-turn corner nodes
  GetNextRoadInfo                  straight <-> curve links (lane fit) and junctions (exit slots relative
                                   to the entry, lane rules, lights / yield control state)
  GetLeftBoundLane / GetRightBoundLane, ROAD_* macros (dr2roads.h)
  CivFindStation / CivFindPointOnPath / CivSteerAngle   look-ahead point and steering (+-512)
Not modelled: CheckChangeLanes (random, collision-gated; off = deterministic routes), parking, car
physics (a kinematic bicycle follower stands in, with a simple yield/brake ramp: path SHAPE reference, not
D2's exact tyre dynamics or CivAccel numbers),
other cars / lights timing (ctrlState is recorded, never waited on). rcossin_tbl = round(4096 sin) (checked:
identical to the PsyQ table in Driver 1's exe at 0x8008EAA8, 4096/4096); ratan2 = atan2 rounded (PsyQ's table
version may differ by 1 unit).

Junction exits: random as Random2(0) % 3 (seeded), or forced per junction with --force L,S,R...

usage (from chicago/devtools):
  python c129_ref.py [--city VEGAS] [--out DIR] [--frames 900] [--seed 1]
      auto cases (4 diagonal straights, 3 curves, junction L/S/R from a diagonal) -> DIR/cases.json,
      DIR/routes.csv (node rows), DIR/traj.csv (follower samples), DIR/sheet.png (one contact sheet)
  python c129_ref.py --road S12 --lane 1 --dist 0 [--force L,S] [--frames N]   one custom route
Default DIR: <app>/devtest/_out/c129/. Coordinates: D2 world units (x, z) plus D1 units (x1, z1) via
worldscale (the converted city's frame, CHI_CITY), for comparing in-game traces.
"""
from __future__ import annotations

import argparse
import copy
import csv
import json
import math
import os
import random
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
CHI = os.path.dirname(HERE)
APP = os.path.dirname(os.path.dirname(CHI))
sys.path.insert(0, CHI)

# ---- PSX maths ---------------------------------------------------------------------------------
SIN = [int(round(4096 * math.sin(2 * math.pi * i / 4096))) for i in range(4096)]


def RSIN(a):
    return SIN[a & 4095]


def RCOS(a):
    return SIN[(a + 1024) & 4095]


def FIXEDH(a):
    return (a + 2048) >> 12


def ratan2(y, x):
    return int(round(math.atan2(y, x) * 2048 / math.pi))


def DIFF(a, b):
    return (((b - a) + 2048) & 4095) - 2048


def cdiv(a, b):
    q = abs(a) // abs(b)
    return q if (a >= 0) == (b >= 0) else -q


def sqrt0(v):
    return math.isqrt(v) if v > 0 else 0


SPEED_LIMITS = (56, 97, 138)
EMPTY = 127

# ---- road data ------------------------------------------------------------------------------------


class Net:
    def __init__(self, path):
        from levfile import Lev
        lev = Lev.parse(open(path, "rb").read())
        L = {l.type: l.data for s in (lev.loadtime, lev.inmem) for l in s.lumps}

        def recs(d, size, fmt):
            n, = struct.unpack_from("<i", d, 0)
            return [struct.unpack_from(fmt, d, 4 + i * size) for i in range(n)]
        self.S = [dict(kind="S", i=i, x=r[0], z=r[1], length=r[2], angle=r[4], conn=list(r[5:9]),
                       nl=r[9], ld=r[10], ai=r[11]) for i, r in enumerate(recs(L[40], 28, "<iiHhh4hBBBB"))]
        self.C = [dict(kind="C", i=i, x=r[0], z=r[1], start=r[2], end=r[3], conn=list(r[4:8]),
                       nl=r[10] & 0xFF, ld=r[11] & 0xFF, inside=r[12], ai=r[13] & 0xFF)
                  for i, r in enumerate(recs(L[41], 28, "<iihh4hhhbbbb"))]
        self.J = [dict(kind="J", i=i, exits=list(r[:4]), flags=r[4])
                  for i, r in enumerate(recs(L[43] if 43 in L else L[42], 12, "<4hI"))]

    def is_S(self, s):
        return s > -1 and (s & 0xFFFFE000) == 0 and (s & 0x1FFF) < len(self.S)

    def is_C(self, s):
        return s > -1 and (s & 0xFFFFE000) == 0x4000 and (s & 0x1FFF) < len(self.C)

    def is_J(self, s):
        return s > -1 and (s & 0xFFFFE000) == 0x2000 and (s & 0x1FFF) < len(self.J)

    def info(self, s):
        """GetSurfaceRoadInfo: the straight / curve dict, or None (junction / nothing)."""
        if self.is_C(s):
            return self.C[s & 0x1FFF]
        if self.is_S(s):
            return self.S[s & 0x1FFF]
        return None


def name(s):
    if s is None or s < 0:
        return str(s)
    return {0: "S", 0x2000: "J", 0x4000: "C"}.get(s & 0xE000, "?") + str(s & 0x1FFF)


def parse_name(t):
    return {"S": 0, "J": 0x2000, "C": 0x4000}[t[0].upper()] | int(t[1:])


# ROAD_* macros (dr2roads.h); lane = sub-lane index (2 per NumLanes unit)
def lanes_count(r):
    return r["nl"] & 15


def width_lanes(r):
    return lanes_count(r) * 2


def _bit(v, lane):
    k = cdiv(lane, 2)
    return (v >> k) & 1 if k >= 0 else 0


def is_ai_lane(r, lane):
    return _bit(r["ai"] & 0xFF, lane)


def lane_dir(r, lane):
    if (r["ld"] & 0xFF) == 0xFF and r["nl"] == 1:
        return lane & 1
    return _bit(r["ld"] & 0xFF, lane)


def parking_at(r, lane):
    return bool((r["nl"] & 0x40) and lane == 0) or bool((r["nl"] & 0x80) and lane == width_lanes(r) - 1)


def speed_limit(r):
    return SPEED_LIMITS[min(2, (r["nl"] >> 4) & 3)]


def left_bound(r, opp):
    n = width_lanes(r)
    lane = n
    for i in range(n - 1, -1, -1):
        if is_ai_lane(r, i) and not parking_at(r, i):
            t = lane_dir(r, i) ^ 1
            lane = i
            if (t == 0 and opp != 0) or (t != 0 and opp == 0):
                break
    return lane


def right_bound(r, opp):
    n = width_lanes(r)
    lane = 1 if (r["nl"] & 0x40) else 0
    for i in range(lane, n):
        if is_ai_lane(r, i) and not parking_at(r, i):
            t = lane_dir(r, i) ^ 1
            lane = i
            if (t == 0 and opp != 0) or (t != 0 and opp == 0):
                break
    return lane


def node_pos(r, dist, lane, clc=0, old_lane=0):
    """GetNodePos -> (x, z) or None (confused: straight angle >= 2048)."""
    if r["kind"] == "S":
        a = r["angle"]
        dfc = dist - r["length"] // 2
        if a >= 2048:
            return None
        t = -clc * 128 if lane <= old_lane else clc * 128
        side = (lanes_count(r) * 512 - (lane * 512 + 256)) + t
        return (r["x"] + FIXEDH(dfc * RSIN(a)) + FIXEDH(side * RCOS(a)),
                r["z"] + FIXEDH(dfc * RCOS(a)) - FIXEDH(side * RSIN(a)))
    a = dist + r["start"]
    t = -clc * 128 if old_lane <= lane else clc * 128
    rad = r["inside"] * 1024 + lane * 512 + 256 + t
    return r["x"] + FIXEDH(rad * RSIN(a)), r["z"] + FIXEDH(rad * RCOS(a))


def curve_step(r):
    return 128 if r["inside"] < 10 else 64 if r["inside"] < 20 else 32


class Confused(Exception):
    pass

# ---- one civ car --------------------------------------------------------------------------------


class Car:
    def __init__(self, net, surf, x, z, seed=1, force=None, wheel_speed=None, lbody=450):
        self.net, self.road = net, surf
        self.x, self.z = x, z
        self.rng = random.Random(seed)
        self.force = list(force or [])
        self.events, self.emitted = [], []
        self.lbody = lbody
        self.turnNode, self.changeLaneCount, self.oldLane = -1, 0, 0
        self.ctrlState = "DRIVE"
        self.ctrl = None
        self.nodes = [dict(pathType=EMPTY, x=0, z=0, dir=0, dist=0) for _ in range(13)]
        r = net.info(surf)
        if r is None:
            raise Confused("spawn not on a straight/curve")
        self.maxSpeed = speed_limit(r)
        self.speed = self.maxSpeed if wheel_speed is None else wheel_speed
        n0 = self.nodes[0]
        n0.update(pathType=1, x=x, z=z)
        if r["kind"] == "S":                                   # InitNodeList
            dx, dz = x - r["x"], z - r["z"]
            theta = r["angle"] - ratan2(dx, dz)
            n0["dist"] = r["length"] // 2 + FIXEDH(RCOS(theta) * sqrt0(dx * dx + dz * dz))
            lane_dist = lanes_count(r) * 512 + FIXEDH(-dx * RCOS(r["angle"]) + dz * RSIN(r["angle"]))
            self.lane = cdiv(lane_dist, 512)
            n0["dir"] = (r["angle"] + 2048) & 0xFFF if lane_dir(r, self.lane) else r["angle"]
        else:
            n0["dist"] = (ratan2(x - r["x"], z - r["z"]) & 0xFFF) - r["start"]
            n0["dist"] &= {128: 0xF80, 64: 0xFC0, 32: 0xFE0}[curve_step(r)]
            dx, dz = x - r["x"], z - r["z"]                     # lane as RemapLaneChange (spawn has none)
            self.lane = (sqrt0(dx * dx + dz * dz) >> 9) - r["inside"] * 2
            n0["dir"] = (n0["dist"] + r["start"] + (1024 if lane_dir(r, self.lane) == 0 else -1024))
        self.pnode, self.currentNode = 0, 0
        self.dir = n0["dir"] & 0xFFF
        self.emit(0)

    # ring helpers (GET_NEXT_NODE on an index that may run past 12, as the C pointer arithmetic)
    @staticmethod
    def nxt(i):
        return i - 12 if i + 1 > 12 else i + 1

    def emit(self, i):
        n = self.nodes[i]
        self.emitted.append(dict(slot=i, x=n["x"], z=n["z"], dir=n["dir"] & 0xFFF, dist=n["dist"],
                                 road=name(self.road), lane=self.lane, corner=n.get("corner", 0)))

    # ---- GetNextRoadInfo
    def next_road(self, old):
        net = self.net
        cur = net.info(self.road)
        if cur is None:
            raise Confused("next_road on a non-road")
        cld = lane_dir(cur, self.lane)
        if cur["kind"] == "S":
            old_opp = ((cur["angle"] - old["dir"]) + 1024) & 2048
        else:
            old_opp = (DIFF(ratan2(old["x"] - cur["x"], old["z"] - cur["z"]), old["dir"]) < 1) * 2048
        tmp_road = [cur["conn"][(old_opp > 0) * 2], cur["conn"][3 if cld > 0 else 1]]
        lane_no = left_bound(cur, cld)
        left_lane = right_lane = None
        if old_opp == 0:
            left_lane = lane_no
        else:
            right_lane = lane_no
        lane_no = right_bound(cur, cld)
        if old_opp != 0:
            left_lane = lane_no
        else:
            right_lane = lane_no
        new_lane, turn, ev = -1, 0, dict(frm=name(self.road), at=(old["x"], old["z"]))
        if net.is_J(tmp_road[0]):
            self.changeLaneCount = 0
            jn = net.J[tmp_road[0] & 0x1FFF]
            exit_from = next((k for k in range(4) if jn["exits"][k] == self.road), -1)
            if exit_from == -1:
                raise Confused("junction %s has no exit back to %s" % (name(tmp_road[0]), name(self.road)))
            valid = [42, 42, 42]
            num = 0
            for cnt in range(3):
                idx = (exit_from + cnt + 1) % 4
                ok = 0
                sid = jn["exits"][idx]
                if sid != -1:
                    ed = ((idx + 4) - exit_from) % 4
                    ta = -1024 if ed == 1 else 1024 if ed == 3 else 0
                    tdir = old["dir"] + ta
                    r = net.info(sid)
                    if r is not None:
                        nlw = width_lanes(r)
                        if r["kind"] == "S":
                            opp = ((r["angle"] - tdir) + 1024) & 2048
                        else:
                            opp = (DIFF(ratan2(old["x"] - r["x"], old["z"] - r["z"]), tdir) < 1) * 2048
                        if ta == 0:
                            nl = (nlw - (self.lane + 1)) if opp != old_opp else self.lane
                        elif ta == -1024:
                            nl = right_bound(r, opp)
                        else:
                            nl = left_bound(r, opp)
                        if 0 <= nl < nlw:
                            ok = int(bool(is_ai_lane(r, nl)) and not parking_at(r, nl))
                        if opp != old_opp:
                            if cld == lane_dir(r, nl):
                                ok = 0
                        elif cld != lane_dir(r, nl):
                            ok = 0
                if ok:
                    valid[cnt] = idx
                    num += 1
            if left_lane != right_lane and num != 1 and lanes_count(cur) > 1:
                if self.lane == left_lane:
                    num -= valid[2] != 42
                    valid[2] = 42
                elif self.lane == right_lane:
                    num -= valid[0] != 42
                    valid[0] = 42
                elif valid[1] != 42:
                    num -= (valid[0] != 42) + (valid[2] != 42)
                    valid[0] = valid[2] = 42
            ev.update(junction=name(tmp_road[0]), exit_from=exit_from,
                      valid={"LSR"[k]: name(jn["exits"][valid[k]]) for k in range(3) if valid[k] != 42})
            if num == 0:
                raise Confused("no valid exit at %s" % name(tmp_road[0]))
            want = self.force.pop(0).upper() if self.force else None
            if want and "LSR".index(want) < 3 and valid["LSR".index(want)] != 42:
                best = valid["LSR".index(want)]
                ev["forced"] = want
            else:
                if want:
                    ev["forced_invalid"] = want
                rnd = self.rng.randrange(0x8000) % 3
                while valid[rnd % 3] == 42:
                    rnd += 1
                best = valid[rnd % 3]
            new_road = jn["exits"][best]
            inv = (best + 4 - exit_from) % 4
            turn = -1024 if inv == 1 else 1024 if inv == 3 else 0
            fl = jn["flags"]
            self.ctrl = (old["x"], old["z"])                     # ctrlNode = oldNode (cleared for YIELD_STRAIGHT)
            if fl & 1:
                self.ctrlState = "WAIT_TRAFFIC_LIGHT(phase %d)" % (exit_from & 1)
            else:
                yld = exit_from in (0, 2)
                if fl & 2:
                    self.ctrlState = "YIELD_TURN" if (yld or turn != 0) else "YIELD_STRAIGHT"
                else:
                    self.ctrlState = "YIELD_TURN" if (not yld or turn != 0) else "YIELD_STRAIGHT"
            r = net.info(new_road)
            if r is None:
                raise Confused("exit %s is no road" % name(new_road))
            tdir = old["dir"] + turn
            nlw = width_lanes(r)
            if r["kind"] == "S":
                opp = ((tdir - r["angle"]) + 1024) & 2048
            else:
                opp = (DIFF(ratan2(old["x"] - r["x"], old["z"] - r["z"]), tdir) < 1) * 2048
            if turn == 0:
                new_lane = self.lane if opp == old_opp else nlw - (self.lane + 1)
                if lane_dir(r, new_lane):
                    if opp == 0:
                        new_lane = -1
                elif opp != 0:
                    new_lane = -1
                if not is_ai_lane(r, new_lane):
                    new_lane = -1
            elif turn == -1024:
                new_lane = right_bound(r, opp)
            else:
                new_lane = left_bound(r, opp)
            if turn != 0:
                if nlw - 1 == new_lane:
                    if lane_dir(r, new_lane) == lane_dir(r, new_lane - 1):
                        new_lane -= 1
                elif new_lane == 0:
                    if lane_dir(r, 0) == lane_dir(r, 1):
                        new_lane += 1
            if self.ctrlState == "YIELD_STRAIGHT":
                self.ctrl = None
            ev.update(turn={-1024: "L", 0: "S", 1024: "R"}[turn], ctrl=self.ctrlState)
        else:
            num = sum(1 for t in tmp_road if t != -1)
            new_exit, fit, tl = -1, [666, 666], [0, 0]
            for k in range(2):
                if tmp_road[k] == -1:
                    continue
                px, pz = old["x"], old["z"]                       # changeLaneCount is 0 here
                nlw = 0
                r = net.info(tmp_road[k])
                if r is not None:
                    nlw = width_lanes(r)
                    if r["kind"] == "S":
                        dx, dz = px - r["x"], pz - r["z"]
                        tl[k] = lanes_count(r) - ((FIXEDH(dx * RCOS(r["angle"]) - dz * RSIN(r["angle"])) + 512) >> 9)
                    else:
                        dx, dz = px - r["x"], pz - r["z"]
                        tl[k] = (sqrt0(dx * dx + dz * dz) >> 9) - r["inside"] * 2
                if num > 1 and (tl[k] < 0 or tl[k] >= nlw):
                    fit[k] = 666
                    num -= 1
                    continue
                nl = tl[k]
                fit[k] = 0 if nl < 0 or nl <= nlw - 1 else nl - nlw - 1
                tl[k] = max(0, min(tl[k], nlw - 1))
                new_exit = k
            if new_exit == -1 or fit[new_exit] == 666:
                raise Confused("no link from %s (%s)" % (name(self.road), [name(t) for t in tmp_road]))
            new_exit = int(abs(fit[0]) < abs(fit[1])) ^ 1
            new_road, new_lane = tmp_road[new_exit], tl[new_exit]
            ev.update(link=name(new_road), fit=fit)
        if new_lane < 0:
            raise Confused("no lane on %s" % name(new_road))
        r = self.net.info(new_road)
        if r["kind"] == "S":
            start_dist = r["length"] if lane_dir(r, new_lane) else 0
        else:
            start_dist = ((r["end"] - r["start"]) & 0xFFF) if lane_dir(r, new_lane) else 0
        self.maxSpeed = speed_limit(r)
        if new_road < 0:
            raise Confused("negative road")
        ev.update(to=name(new_road), lane=new_lane, start_dist=start_dist)
        self.events.append(ev)
        self.lane = new_lane
        return new_road, turn, start_dist

    # ---- CreateNewNode
    def create_node(self):
        net, N = self.net, self.nodes
        start = self.pnode
        turn = 0
        guard = 0
        while True:
            guard += 1
            if guard > 13:
                raise Confused("node ring full")
            new = ret = self.nxt(start)
            if N[ret]["pathType"] == EMPTY:
                old_road = self.road
                r = net.info(old_road)
                if r is None:
                    raise Confused("road lost")
                td = 1 if lane_dir(r, self.lane) == 0 else -1
                st = N[start]
                if r["kind"] == "S":
                    seg_end = r["length"]
                    N[new]["dist"] = st["dist"] + td * 1024
                    N[new]["dir"] = st["dir"]
                else:
                    seg_end = (r["end"] - r["start"]) & 0xFFF
                    N[new]["dist"] = st["dist"] + td * curve_step(r)
                    N[new]["dir"] = (N[new]["dist"] + r["start"] + td * 1024) & 0xFFF
                if (td > 0 and seg_end < N[new]["dist"]) or (td < 0 and N[new]["dist"] < 0):
                    if (td > 0 and seg_end <= st["dist"]) or (td < 0 and st["dist"] < 1):
                        self.road, turn, sd = self.next_road(st)
                        N[new]["dir"] = (st["dir"] + turn) & 0xFFF
                        N[new]["dist"] = sd
                    else:
                        N[new]["dist"] = 0 if td < 1 else seg_end
                r = net.info(self.road)
                if r is None:
                    raise Confused("road lost")
                if old_road != self.road and turn == 0:
                    td = 1 if lane_dir(r, self.lane) == 0 else -1
                    N[new]["dist"] += td * (curve_step(r) if r["kind"] == "C" else 1024)
                tmp = dict(N[new])
                p = node_pos(r, N[new]["dist"], self.lane, self.changeLaneCount, self.oldLane)
                if p is None:
                    raise Confused("straight angle >= 2048")
                tmp["x"], tmp["z"] = p
                if turn == -1024:                              # left turn: corner nodes
                    dx, dz = tmp["x"] - st["x"], tmp["z"] - st["z"]
                    seg = sqrt0(dx * dx + dz * dz) - (self.speed * 4096) // 170
                    ca = DIFF(st["dir"], ratan2(dx, dz))
                    t = FIXEDH(seg * RCOS(ca))
                    ret = new
                    if t > 0:
                        N[new].update(x=st["x"] + FIXEDH(t * RSIN(st["dir"])), z=st["z"] + FIXEDH(t * RCOS(st["dir"])),
                                      pathType=1, dir=st["dir"], corner=1)
                        self.emit(new)
                        ret = self.nxt(new)
                    t = FIXEDH(seg * RSIN(ca))
                    new = ret
                    if t < 0:
                        N[ret].update(x=tmp["x"] + FIXEDH(t * RSIN(tmp["dir"])), z=tmp["z"] + FIXEDH(t * RCOS(tmp["dir"])),
                                      pathType=1, dir=tmp["dir"], corner=2, dist=tmp["dist"])
                        self.emit(ret)
                        new = self.nxt(ret)
                if N[new]["pathType"] == EMPTY:
                    N[new].update(x=tmp["x"], z=tmp["z"], dir=tmp["dir"], dist=tmp["dist"], corner=0)
                    if abs(tmp["x"]) < 600000:
                        if turn:
                            self.turnNode = new
                        N[new]["pathType"] = 1
                        self.emit(new)
                        return True
                raise Confused("CreateNewNode fell through")
            start = new
            if new == self.pnode:
                raise Confused("ring wrapped")

    # ---- CivFindStation / CivFindPointOnPath / CivSteerAngle
    def find_station(self):
        N = self.nodes
        cur = 0
        for _ in range(self.currentNode):
            cur = self.nxt(cur)
        for _ in range(64):
            ret = self.nxt(cur)
            sx, sz = N[cur]["x"], N[cur]["z"]
            dx, dz = N[ret]["x"] - sx, N[ret]["z"] - sz
            sq = sqrt0(dx * dx + dz * dz)
            if sq > 0:
                step = cdiv((self.x - sx) * dx + (self.z - sz) * dz, sq)
                if step < sq:
                    self.pnode = cur
                    return step
            cur = ret
            self.currentNode = cur
            for i in range(1, 4):
                if N[self.nxt(ret + i)]["pathType"] == EMPTY:
                    self.create_node()
        raise Confused("station not found")

    def point_on_path(self, station):
        N = self.nodes
        cur = start = self.pnode
        while True:
            ret = cur + 1
            if ret >= 13:
                ret = cur - 12
            if N[ret]["pathType"] == EMPTY:
                return N[cur]["x"], N[cur]["z"]
            sx, sz = N[cur]["x"], N[cur]["z"]
            dx, dz = N[ret]["x"] - sx, N[ret]["z"] - sz
            step = sqrt0(dx * dx + dz * dz)
            if station < step:
                station = max(station, 0)
                if step < 4096:
                    return sx + cdiv(dx * station, step), sz + cdiv(dz * station, step)
                step //= 16
                return sx + FIXEDH(cdiv(dx * 256, step) * station), sz + FIXEDH(cdiv(dz * 256, step) * station)
            station -= step
            cur = ret
            if ret == start:
                raise Confused("path loop")

    def steer(self):
        N = self.nodes
        s = self.pnode
        for i in range(4):
            if N[self.nxt(s + i)]["pathType"] == EMPTY:
                self.create_node()
        station = self.find_station()
        px, pz = self.point_on_path(station + self.speed * 20 + self.lbody)
        ang = max(-512, min(512, DIFF(self.dir, ratan2(px - self.x, pz - self.z))))
        cr = s
        while cr != self.pnode:                                # consumed nodes are freed
            N[cr]["pathType"] = EMPTY
            if self.turnNode == cr:
                self.turnNode = -1
            cr = self.nxt(cr)
        return ang, (px, pz)

    def thrust(self):
        """Stand-in for CivAccel/CivAccelTrafficRules without other cars: cruise at maxSpeed; with a ctrl node
        (YIELD_TURN / WAIT_TRAFFIC_LIGHT) brake towards it and release within 3 car lengths (the yield finds
        nobody, lights are treated as green), as D2's properVel ramp. Accel +2 / brake -4 units per frame."""
        want = self.maxSpeed
        if self.ctrl is not None:
            d = math.hypot(self.x - self.ctrl[0], self.z - self.ctrl[1])
            if d < self.lbody * 3 + 32:
                self.ctrl, self.ctrlState = None, "DRIVE"
            else:
                want = min(want, max(8, int((d - self.lbody * 3) / 12) + 8))
        self.speed = min(want, self.speed + 2) if self.speed < want else max(want, self.speed - 4)

    def step(self, wheelbase=700):
        """One 30 fps frame of the kinematic stand-in: bicycle model at self.speed units/frame."""
        self.thrust()
        ang, target = self.steer()
        self.dir = (self.dir + int(round(self.speed / wheelbase * math.tan(ang * math.pi / 2048) * 2048 / math.pi))) & 0xFFF
        self.x += FIXEDH(self.speed * RSIN(self.dir))
        self.z += FIXEDH(self.speed * RCOS(self.dir))
        return ang, target


# ---- case set -----------------------------------------------------------------------------------
def spawn_on(net, surf, lane=None, dist=None, along=True):
    """(x, z, lane) of a sub-lane point on a straight/curve; lane None = first AI lane going `along`."""
    r = net.info(surf)
    n = width_lanes(r)
    cands = [k for k in range(n) if is_ai_lane(r, k) and not parking_at(r, k)]
    if lane is None:
        pref = [k for k in cands if lane_dir(r, k) == (0 if along else 1)]
        if not (pref or cands):
            return None
        lane = (pref or cands)[0]
    end = r["length"] if r["kind"] == "S" else (r["end"] - r["start"]) & 0xFFF
    if dist is None:
        dist = 0 if lane_dir(r, lane) == 0 else end
        dist = dist + (1 if dist == 0 else -1) * min(end // 4, 1024 if r["kind"] == "S" else curve_step(r))
    p = node_pos(r, dist, lane)
    return (p[0], p[1], lane) if p else None


def axdev(a):
    m = a % 1024
    return min(m, 1024 - m)


def auto_cases(net):
    cases = []
    diag = sorted((s for s in net.S if axdev(s["angle"]) >= 400 and s["ai"] & ((1 << lanes_count(s)) - 1)),
                  key=lambda s: -s["length"])
    for s in diag[:4]:
        cases.append(dict(id="diag_S%d" % s["i"], surf=s["i"], force=[], why="diagonal straight, angle %d, length %d"
                          % (s["angle"], s["length"])))
    cv = [c for c in net.C if c["ai"] & ((1 << lanes_count(c)) - 1)]
    span = lambda c: (c["end"] - c["start"]) & 0xFFF
    picks = [max(cv, key=lambda c: c["inside"] * span(c)),
             min((c for c in cv if 900 <= span(c) <= 1150), key=lambda c: c["inside"], default=None),
             max((c for c in cv if span(c) > 1150), key=lambda c: span(c), default=None)]
    seen = set()
    for c in picks:
        if c and c["i"] not in seen:
            seen.add(c["i"])
            cases.append(dict(id="curve_C%d" % c["i"], surf=0x4000 | c["i"], force=[],
                              why="curve span %d, inside %d" % (span(c), c["inside"])))
    return cases


def junction_cases(net, seed, limit=3):
    """Diagonal straights ending at a junction with >= 3 exits: for each sub-lane travelling towards it, probe
    which forced turn (L / S / R) D2's lane rules allow; one case per turn, each from the first (longest)
    diagonal whose junction allows it, up to `limit` cases."""
    diag = sorted((s for s in net.S if axdev(s["angle"]) >= 400 and s["ai"] & ((1 << lanes_count(s)) - 1)),
                  key=lambda s: -s["length"])
    ident = lambda x, z: (x, z)
    got = {}
    for s in diag:
        for end_idx in (0, 2):
            c = s["conn"][end_idx]
            if not (net.is_J(c) and sum(e != -1 for e in net.J[c & 0x1FFF]["exits"]) >= 3):
                continue
            along = end_idx == 0
            dist = max(512, s["length"] - 8000) if along else min(s["length"] - 512, 8000)   # room to brake
            found = {}
            for lane in range(width_lanes(s)):
                if not is_ai_lane(s, lane) or parking_at(s, lane) or lane_dir(s, lane) != (0 if along else 1):
                    continue
                for t in "LSR":
                    if t in found:
                        continue
                    case = dict(id="junc_S%d_%s" % (s["i"], t), surf=s["i"], lane=lane, dist=dist, along=along,
                                force=[t], why="diagonal S%d (angle %d) into %s, sub-lane %d, forced %s"
                                % (s["i"], s["angle"], name(c), lane, t))
                    res = run_case(net, case, 400, seed, ident)
                    ev = next((e for e in res["events"] if "junction" in e), None)
                    if ev and ev.get("forced") == t:
                        found[t] = case
            for t, case in found.items():
                got.setdefault(t, case)
            if len(got) == 3:
                break
        if len(got) == 3:
            break
    return [got[t] for t in "LSR" if t in got][:limit]


def run_case(net, c, frames, seed, to_d1):
    out = dict(case=c, nodes=[], traj=[], events=[], error=None)
    sp = None
    sp = spawn_on(net, c["surf"], c.get("lane"), c.get("dist"), c.get("along", True))
    if not sp:
        out["error"] = "no AI lane to spawn on"
        return out
    try:
        car = Car(net, c["surf"], sp[0], sp[1], seed=seed, force=c.get("force"))
    except Confused as e:
        out["error"] = "spawn: %s" % e
        return out
    try:
        for f in range(frames):
            ang, tgt = car.step()
            if f % 3 == 0:
                out["traj"].append(dict(f=f, x=car.x, z=car.z, dir=car.dir, steer=ang, tx=tgt[0], tz=tgt[1], v=car.speed,
                                        road=name(car.road), lane=car.lane))
    except Confused as e:
        out["error"] = "frame %d: %s" % (f, e)
    out["nodes"], out["events"] = car.emitted, car.events
    poly = [(n["x"], n["z"]) for n in out["nodes"]]

    def seg_d(px, pz):
        best = 1e18
        for (ax, az), (bx, bz) in zip(poly, poly[1:]):
            dx, dz = bx - ax, bz - az
            L2 = dx * dx + dz * dz or 1
            t = max(0.0, min(1.0, ((px - ax) * dx + (pz - az) * dz) / L2))
            best = min(best, math.hypot(px - ax - t * dx, pz - az - t * dz))
        return best
    out["max_dev"] = round(max((seg_d(t["x"], t["z"]) for t in out["traj"]), default=0))
    for n in out["nodes"] + out["traj"]:
        n["x1"], n["z1"] = to_d1(n["x"], n["z"])
    return out


def sheet(results, net, path):
    from PIL import Image, ImageDraw
    W = 360
    cols = 4
    rows = (len(results) + cols - 1) // cols
    im = Image.new("RGB", (cols * W, rows * W), (20, 20, 24))
    dr = ImageDraw.Draw(im)
    for k, res in enumerate(results):
        ox, oy = (k % cols) * W, (k // cols) * W
        pts = [(n["x"], n["z"]) for n in res["nodes"]] + [(t["x"], t["z"]) for t in res["traj"]]
        if not pts:
            continue
        x0, x1 = min(p[0] for p in pts), max(p[0] for p in pts)
        z0, z1 = min(p[1] for p in pts), max(p[1] for p in pts)
        sc = (W - 40) / max(x1 - x0, z1 - z0, 1)
        P = lambda x, z: (ox + 20 + (x - x0) * sc, oy + W - 20 - (z - z0) * sc)
        for s in net.S:                                         # road centre lines in view
            dx, dz = s["length"] / 2 * math.sin(s["angle"] * math.pi / 2048), s["length"] / 2 * math.cos(s["angle"] * math.pi / 2048)
            a, b = (s["x"] - dx, s["z"] - dz), (s["x"] + dx, s["z"] + dz)
            if max(a[0], b[0]) < x0 or min(a[0], b[0]) > x1 or max(a[1], b[1]) < z0 or min(a[1], b[1]) > z1:
                continue
            dr.line([P(*a), P(*b)], fill=(70, 70, 80), width=1)
        for c in net.C:
            sp = (c["end"] - c["start"]) & 0xFFF
            rad = c["inside"] * 1024 + lanes_count(c) * 512
            arc = [P(c["x"] + rad * math.sin((c["start"] + sp * i / 16) * math.pi / 2048),
                     c["z"] + rad * math.cos((c["start"] + sp * i / 16) * math.pi / 2048)) for i in range(17)]
            if any(ox <= p[0] <= ox + W and oy <= p[1] <= oy + W for p in arc):
                dr.line(arc, fill=(70, 70, 80), width=1)
        dr.line([P(t["x"], t["z"]) for t in res["traj"]] or [P(*pts[0])], fill=(80, 200, 255), width=2)
        for n in res["nodes"]:
            p = P(n["x"], n["z"])
            col = (255, 120, 60) if n["corner"] else (255, 230, 80)
            dr.rectangle([p[0] - 2, p[1] - 2, p[0] + 2, p[1] + 2], fill=col)
        dr.rectangle([ox, oy, ox + W - 1, oy + W - 1], outline=(90, 90, 90))
        dr.text((ox + 4, oy + 4), res["case"]["id"] + (" ERR" if res["error"] else ""), fill=(255, 255, 255))
    im.save(path)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--city", default=os.environ.get("CHI_CITY", "VEGAS"))
    ap.add_argument("--out", default=os.path.join(APP, "devtest", "_out", "c129"))
    ap.add_argument("--frames", type=int, default=900)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--road")
    ap.add_argument("--lane", type=int)
    ap.add_argument("--dist", type=int)
    ap.add_argument("--force", default="")
    a = ap.parse_args()
    os.environ["CHI_CITY"] = a.city.upper()
    import inputs
    import worldscale as ws
    lev = "d2_%s.LEV" % ("VEGAS" if a.city.upper() == "LASVEGAS" else a.city.upper())
    try:
        path = inputs.path(lev)
    except BaseException:
        path = os.path.join(APP, "setup_cache", "inputs", "d2_usa_v11", lev)
    net = Net(path)
    bad = sum(1 for s in net.S if s["angle"] >= 2048)
    print("%s: %d straights (%d with angle >= 2048 = D2 'confused'), %d curves, %d junctions"
          % (a.city, len(net.S), bad, len(net.C), len(net.J)))
    to_d1 = lambda x, z: ws.to_d1(int(x), int(z))
    if a.road:
        cases = [dict(id="custom_" + a.road, surf=parse_name(a.road), lane=a.lane, dist=a.dist,
                      force=[t for t in a.force.split(",") if t], why="command line")]
    else:
        cases = auto_cases(net) + junction_cases(net, a.seed)
    os.makedirs(a.out, exist_ok=True)
    results = [run_case(net, c, a.frames, a.seed, to_d1) for c in cases]
    with open(os.path.join(a.out, "cases.json"), "w") as f:
        json.dump(dict(city=a.city, source=os.path.basename(path), frames=a.frames, seed=a.seed,
                       results=[dict(case=r["case"], error=r["error"], events=r["events"], max_dev=r.get("max_dev"),
                                     n_nodes=len(r["nodes"])) for r in results]), f, indent=1)
    with open(os.path.join(a.out, "routes.csv"), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["case", "k", "road", "lane", "slot", "dist", "dir", "corner", "x", "z", "x1", "z1"])
        for r in results:
            for k, n in enumerate(r["nodes"]):
                w.writerow([r["case"]["id"], k, n["road"], n["lane"], n["slot"], n["dist"], n["dir"], n["corner"],
                            n["x"], n["z"], n["x1"], n["z1"]])
    with open(os.path.join(a.out, "traj.csv"), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["case", "frame", "road", "lane", "x", "z", "dir", "steer", "speed", "tx", "tz", "x1", "z1"])
        for r in results:
            for t in r["traj"]:
                w.writerow([r["case"]["id"], t["f"], t["road"], t["lane"], t["x"], t["z"], t["dir"], t["steer"], t["v"],
                            t["tx"], t["tz"], t["x1"], t["z1"]])
    sheet(results, net, os.path.join(a.out, "sheet.png"))
    print("%-16s %5s %5s %6s %-34s %s" % ("case", "nodes", "roads", "maxdev", "junction turns (L/S/R) / links (~)", "error"))
    for r in results:
        roads = []
        for n in r["nodes"]:
            if not roads or roads[-1] != n["road"]:
                roads.append(n["road"])
        ev = " ".join((e.get("turn", "") + e["to"]) if "junction" in e else ("~" + e["to"]) for e in r["events"])
        print("%-16s %5d %5d %6d %-34s %s" % (r["case"]["id"], len(r["nodes"]), len(roads), r.get("max_dev", 0), ev[:34],
                                            r["error"] or ""))
    print("out:", a.out)


if __name__ == "__main__":
    main()
