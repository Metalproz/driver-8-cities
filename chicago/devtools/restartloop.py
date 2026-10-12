"""restartloop.py - drown/wreck -> Game Over -> Play Again loop at a spot; checks
liveness, kernel and the model table after every restart (C26).

    python restartloop.py NAME SPOT [--lev LEV] [--port P] [--loops N] [--dir DX,DZ]
"""
from __future__ import annotations
import sys, time, math
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import dt


def main(a):
    name, spot = a[0], a[1]
    opt = {a[i].lstrip("-"): a[i + 1] for i in range(2, len(a) - 1, 2) if a[i].startswith("--")}
    lev, port, loops = opt.get("lev"), int(opt.get("port", 4384)), int(opt.get("loops", 4))
    dx, dz = (float(v) for v in opt.get("dir", "0,1").split(","))
    dt.prepare(name, dt.spots()[spot]["d2"], lev)
    p, d = dt.launch(name, port)
    sig = dt.model_sigs(dt.copy_lev(name))
    try:
        dt.to_take_a_ride(d)
        for k in range(loops):
            t0 = d.pos()
            mask = 0xFFFF & ~(1 << dt.BTN["cross"])
            d.cmd("set_input", buttons="0x%04X" % mask)       # drive straight (into the water)
            time.sleep(7)
            d.cmd("clear_input")
            time.sleep(10)                                      # sinking, Game Over screen
            dt.play_again(d, wait=0.0)                          # Game Over -> Play Again (+ "Are You Sure?")
            time.sleep(8)
            bad = dt.table_check(d.ram_all(), d.ram(dt.MODEL_TABLE, dt.MODEL_ENTRIES * 4) + bytes(0x90000), sig)
            print("loop %d: pos %s -> %s  alive %s  kernel_ok %s  table_bad %d  city %d  area %d  loading %d" % (
                k + 1, t0, d.pos(), dt.alive(d), dt.kernel_ok(d), len(bad), d.word(dt.CITY), d.word(dt.AREA), d.word(dt.LOADING)))
            if not dt.alive(d) or d.word(dt.CITY) != dt.CHICAGO_CITY:
                r = d.cmd("get_registers"); print("  stopped: pc %s epc %s" % (r.get("pc"), r.get("cop0_epc")))
                break
    finally:
        p.kill()


if __name__ == "__main__":
    main(sys.argv[1:])
