"""C109 hang hunt (cheats 7 hang / nightmare_vs_cop 26.10.: ISR spinning in libgpu's GPU-timeout loop 0x800764C4 with
interrupts masked). CITY (miami), NM / HELL / RUNNER_XDRAW as wanted, player standing (Invincibility) up to SECS;
run with PSX_STARVATION_TIMEOUT_US=0 so a hung instance stays up: then GPU / DMA / IRQ state + rings go to files."""
import json, os, time
SESSION = dict(day="var_polish_specdmg2_day.lev", night="var_polish_specdmg2_night.lev", s4=True)


def save(s, name, obj):
    (s.dir / name).write_text(json.dumps(obj, indent=0)[:4000000], encoding="utf-8")


def run(s):
    s.poke32(0x8009681C, 1)
    s.menu("take_a_ride/" + os.environ.get("CITY", "miami")); s.wait_world(what="start")
    if os.environ.get("NM", "1") == "1": s.poke32(0x800933C8, 1)
    if os.environ.get("HELL") == "1": s.poke32(0x8009342C, 1)
    t0 = time.time(); last, still = s.word(0x80095250), 0
    while time.time() - t0 < float(os.environ.get("SECS", "240")):
        time.sleep(0.5)
        v = s.word(0x80095250)
        still = still + 1 if v == last else 0
        last = v
        if still >= 6:
            break
    if still < 6:
        s.record("no hang", detail="%.0f s" % (time.time() - t0)); return
    s.record("hang", ok=False, detail="vblank counter stuck at %d after %.0f s" % (last, time.time() - t0))
    for c, kw in (("get_registers", {}), ("gpu_state", {}), ("dma_state", {}), ("irq_state", {}), ("imask_trace", {}), ("irqctx_ring", {}), ("dirty_ram_stats", {}), ("gpu_ring_stats", {}),
                  ("mmio_dump", {"count": 3000, "newest": True}), ("event_ring_tail", {"count": 400})):
        try: save(s, c + ".json", s.d.cmd(c, **kw))
        except Exception as e: save(s, c + ".json", {"err": str(e)})
    try:
        st = s.d.cmd("gpu_ring_stats"); f = int(st["newest_frame"])
        save(s, "gp0_frames.json", [s.d.cmd("gpu_frame_dump", frame=ff, count=65536) for ff in (f, f - 1, f - 2)])
    except Exception as e:
        save(s, "gp0_frames.json", {"err": str(e)})
    open(s.dir / "ram.bin", "wb").write(s.d.ram_all())
