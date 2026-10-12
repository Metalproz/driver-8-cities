"""freezeprobe.py - drive a direction at a spot and, when the game stops (freeze),
keep it and dump what the CPU was doing: registers, the stack's code addresses, the
model-table entries near any pointer registers, area / loading / spool state.

    python freezeprobe.py NAME SPOT DIRX DIRZ [--secs N] [--lev LEV] [--port P]
"""
from __future__ import annotations
import sys, time, math, struct
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import dt

NAMES = "zero at v0 v1 a0 a1 a2 a3 t0 t1 t2 t3 t4 t5 t6 t7 s0 s1 s2 s3 s4 s5 s6 s7 t8 t9 k0 k1 gp sp fp ra".split()


def main(a):
    name, spot, dx, dz = a[0], a[1], float(a[2]), float(a[3])
    opt = {a[i].lstrip("-"): a[i + 1] for i in range(4, len(a) - 1, 2) if a[i].startswith("--")}
    secs, port, lev = float(opt.get("secs", 25)), int(opt.get("port", 4386)), opt.get("lev")
    dt.prepare(name, dt.spots()[spot]["d2"], lev)
    p, d = dt.launch(name, port)
    try:
        dt.to_take_a_ride(d)
        want = math.atan2(dx, dz)
        t0, last, reversing = time.time(), d.pos(), 0
        mask_cross = 0xFFFF & ~(1 << dt.BTN["cross"])
        d.cmd("set_input", buttons="0x%04X" % mask_cross)
        froze = False
        while time.time() - t0 < secs:
            time.sleep(0.25)
            if not dt.alive(d, 0.6) and not dt.alive(d, 2.0):
                froze = True
                break
            pos = d.pos(); mvx, mvz = pos[0] - last[0], pos[2] - last[2]
            mask = mask_cross
            spd = math.hypot(mvx, mvz)
            if spd > 60:
                err = (math.atan2(mvx, mvz) - want + math.pi) % (2 * math.pi) - math.pi
                if reversing:
                    mask = 0xFFFF & ~(1 << dt.BTN["square"]) & ~(1 << dt.BTN["right" if err > 0 else "left"]); reversing -= 1
                elif abs(err) > math.radians(8):
                    mask &= ~(1 << dt.BTN["left" if err > 0 else "right"])
            elif time.time() - t0 > 2 and not reversing:
                reversing = 6; mask = 0xFFFF & ~(1 << dt.BTN["square"])
            d.cmd("set_input", buttons="0x%04X" % mask)
            last = pos
        d.cmd("clear_input")
        print("froze" if froze else "no freeze", "at", d.pos(), "t=%.1f" % (time.time() - t0),
              "area", d.word(dt.AREA), "region", d.word(dt.REGION), "loading", d.word(dt.LOADING), "spool left", d.word(dt.SPOOL_LEFT))
        if froze:
            r = d.cmd("get_registers")
            g = r.get("gpr") or r.get("regs")
            regs = {n: int(v, 16) if isinstance(v, str) else v for n, v in zip(NAMES, g)} if isinstance(g, list) else {}
            print("pc", r.get("pc"), "epc", r.get("cop0_epc") or r.get("epc"), {n: "%08X" % regs[n] for n in ("a0", "a1", "a2", "t7", "s0", "s1", "s2", "s3", "s4", "s5", "s6", "s7", "ra", "sp") if n in regs})
            sp = regs.get("sp", 0) & 0x1FFFFF
            words = struct.unpack("<%dI" % 48, d.ram(0x80000000 + sp, 192))
            print("stack code addrs:", ["%08X" % w for w in words if 0x80010000 <= w < 0x80090000][:12])
            table = struct.unpack("<2048I", d.ram(dt.MODEL_TABLE, 2048 * 4))
            spool = d.word(0x80097238) & 0x1FFFFFFF
            print("spool buffer %08X, models end %08X" % (spool, d.word(0x8009723C)))
            cands = [w for w in list(regs.values()) + list(words) if 0x80010000 <= (w | 0x80000000) < 0x80200000]
            seen = set()
            for v in cands:
                v &= 0x1FFFFFFF
                for i, pt in enumerate(table):
                    q = pt & 0x1FFFFFFF
                    if pt and 0 <= v - q < 0x1000 and (i, q) not in seen:
                        seen.add((i, q)); print("  pointer %08X -> model %d at %08X (+%X)%s" % (v, i, q, v - q, " IN SPOOL" if spool <= q < spool + 0x40000 else ""))
            car = d.ram(0x8009B0A4, 0x40)
            print("player car struct +0..+0x3C:", car.hex())
            d.shot(Path(dt.run_dir("freeze")) / "freeze.png")
    finally:
        p.kill()


if __name__ == "__main__":
    main(sys.argv[1:])
