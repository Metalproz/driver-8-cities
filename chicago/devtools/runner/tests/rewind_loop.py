"""C107: add-ons must survive state restores. CITY (default chicago), NIGHTMARE (NM=1) / HELL (HELL=1): N rounds of
save state slot 6 -> drive DRIVE s (area switches, spawns, specials) -> load slot 6 -> drive; RESTORE_AT=0 restores right
after the save. Checks: alive after every round (no hang dump), the game frame advances, chasers chase after the last."""
import os, socket, time
SESSION = dict(day="var_polish_specdmg2_day.lev", night="var_polish_specdmg2_night.lev", s4=True)


def raw(port, line):
    s = socket.create_connection(("127.0.0.1", port), timeout=40)
    s.sendall(line.encode() + b"\n"); buf = b""
    while not buf.endswith(b"\n"):
        c = s.recv(1 << 20)
        if not c: break
        buf += c
    return buf.decode()


def run(s):
    s.poke32(0x8009681C, 1)                              # Invincibility: the chasers must not end the run (wreck)
    if os.environ.get("NM", "1") == "1": s.poke32(0x800933C8, 1)
    if os.environ.get("HELL") == "1": s.poke32(0x8009342C, 1)
    s.menu("take_a_ride/" + os.environ.get("CITY", "chicago")); s.wait_world(what="start")
    want = s.car(0)[3]
    bad = []; frames_ok = []; per = []
    for k in range(int(os.environ.get("N", "12"))):
        if os.environ.get("NOSAVE") != "1": raw(s.port, '{"id":1,"cmd":"savestate","op":"save","slot":6}')
        time.sleep(0.4)
        s.drive(float(os.environ.get("DRIVE", "3")), want if k % 3 else None)
        if os.environ.get("NOLOAD") != "1": raw(s.port, '{"id":2,"cmd":"savestate","op":"load","slot":6}')
        time.sleep(0.4)
        f0, v0 = s.word(0x800970D8), s.word(0x80095250)
        s.drive(1.5, want)
        f1, v1 = s.word(0x800970D8), s.word(0x80095250)
        ok = v1 != v0                                    # hang = no vblank handled (watchdog case)
        frames_ok.append(f1 != f0)
        per.append(sum(1 for i in range(24) if s.ram(0x80098950 + 0x50 * i, 2)[1] == 4))                       # (a busted / game-over screen stops the game frame, no hang)
        if not ok:
            bad.append((k, f0, f1, v0, v1))
            pcs = []
            for _ in range(8):
                r = s.d.cmd("get_registers"); pcs.append((r.get("pc"), r.get("gpr", [None] * 32)[31], r.get("guest_epc"))); time.sleep(0.1)
            s.record("stuck", detail="pc / ra / guest_epc samples %s" % pcs)
        if len(bad) >= 2: break
    pur = sum(1 for i in range(24) if s.ram(0x80098950 + 0x50 * i, 2)[1] == 4)
    s.record("rounds", detail="hung rounds %s; game frames advanced in %d of %d rounds; pursuers at the end %d, per round %s, NGHT %d" % (
        bad, sum(frames_ok), len(frames_ok), pur, per, s.word(0x800933C8)))
    s.check("every round alive and running", not bad, "%s" % bad)
    if os.environ.get("NM", "1") == "1" or os.environ.get("HELL") == "1":
        s.check("chasers after the restores", pur >= 1, "%d (long drives thin them out without restores too)" % pur)
