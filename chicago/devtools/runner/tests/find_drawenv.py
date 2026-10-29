"""C134 helper: find Driver 1's DRAWENV structs in RAM (clip rects 0,0,512,h / 0,256,512,h) and print their fields."""
import struct, time
SESSION = dict(day="var_polish_cheats6_day.lev", night="var_polish_cheats6_night.lev", s4=True)


def run(s):
    s.menu("take_a_ride/miami"); s.wait_world(what="miami")
    time.sleep(1)
    hits = []
    for base in range(0x80010000, 0x80200000, 0x10000):
        blk = s.ram(base, 0x10000)
        for h in (240, 256, 224):
            for y in (0, 256, 240):
                pat = struct.pack("<4h", 0, y, 512, h)
                i = blk.find(pat)
                while i >= 0:
                    hits.append((base + i, y, h, blk[i:i + 32].hex()))
                    i = blk.find(pat, i + 2)
    s.record("drawenv", detail=str(hits[:20]))
