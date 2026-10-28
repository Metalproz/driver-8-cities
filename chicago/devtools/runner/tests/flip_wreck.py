"""C88: with Invincibility a car on its roof is not wrecked any more (Driver 1 sets damage = max after 180 flipped
frames, FUN_800230B0); without Invincibility Driver 1 is unchanged (wrecked within ~8 s)."""
import time
SESSION = dict(day="var_polish_specdmg2_day.lev", night="var_polish_specdmg2_night.lev", s4=True)
B, INV, DMG, MAXD, CNT = 0x8009B0A4, 0x8009681C, 0x8009B220, 0x80096E7C, 0x80096920


def flip(s):
    x, y, z = s.word(B + 0x18), s.word(B + 0x1C), s.word(B + 0x20)
    y = (y - 300) & 0xFFFFFFFF
    m = [0xF000, 0, 0, 0, 0xF000, 0, 0, 0, 0x1000]          # 180 deg about the forward axis
    for k, v in enumerate(m):
        for b in range(2):
            s.d.cmd("write_ram", addr="0x%08X" % (B + 4 + 2 * k + b), val=(v >> (8 * b)) & 0xFF)
    for k, v in enumerate([x, y, z, (x * 16) & 0xFFFFFFFF, (y * 16) & 0xFFFFFFFF, (z * 16) & 0xFFFFFFFF, 0, 0, 4096, 0, 0, 0, 0, 0, 0, 0]):
        s.poke32(B + 0x18 + 4 * k, v)


def run(s):
    s.menu("take_a_ride/miami"); s.wait_world(what="start")
    s.poke32(INV, 1); time.sleep(0.5)
    for attempt in range(4):                            # a half-tilted car can roll back: flip again until it lies on its roof
        s.d.cmd("pause"); flip(s); s.d.cmd("continue")  # flip between two frames (the physics raced the pokes)
        time.sleep(1.0)
        up = s.word(0x8009B0B0) & 0xFFFF
        up = up - 0x10000 if up & 0x8000 else up
        if up < -3000:
            break
    s.record("flipped", detail="up vector y %d (attempt %d)" % (up, attempt + 1))
    time.sleep(9.0)
    d, m = s.word(DMG) & 0xFFFF, s.word(MAXD) & 0xFFFF
    up2 = s.word(0x8009B0B0) & 0xFFFF; up2 = up2 - 0x10000 if up2 & 0x8000 else up2
    s.check("Invincibility: still on the roof, not wrecked after 10 s", up2 < 100 and d < m and s.word(CNT) == 0,
            "up %d, damage %d / %d, counter %d" % (up2, d, m, s.word(CNT)))
    s.screenshot("roof")
    s.poke32(INV, 0); time.sleep(8.0)
    d, m = s.word(DMG) & 0xFFFF, s.word(MAXD) & 0xFFFF
    s.check("without Invincibility Driver 1 wrecks it", d >= m, "damage %d / %d, counter %d" % (d, m, s.word(CNT)))
