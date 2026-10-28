"""Chase music cue (C60 / havana 1 user report): in Take a Ride (CITY=chicago|havana|miami, NIGHT=1) the felony is set to
0x400; Driver 1's chase switch 0x8004CF50 must set copmusic 0x80096C70 = 1 and jump the XM song (Song_ID 0x80096C88) to
xm_coptrackpos[*0x80097298] (order position = song struct *(0x800C7888 + 4 x Song_ID) + 0x1C). Records song / index /
table entry / order position before and after."""
import os, time
CITY = os.environ.get("CITY", "havana")
NIGHT = os.environ.get("NIGHT") == "1"
SESSION = dict(day="var_polish_cheats6_day.lev", night="var_polish_cheats6_night.lev", s4=True)
CHASE_TAB = 0x8001188C


def state(s):
    sid, idx = s.word(0x80096C88), s.word(0x80097298)
    tab = s.word(0x8004CF84) & 0xFFFF, s.word(0x8004CF88) & 0xFFFF
    base = ((tab[0] << 16) + (tab[1] - 0x10000 if tab[1] & 0x8000 else tab[1])) & 0xFFFFFFFF
    entry = s.word(base + 4 * idx) & 0xFFFF if idx < 64 else -1
    song = s.word(0x800C7888 + 4 * sid) if sid < 32 else 0
    song = song | 0x80000000 if 0 < song < 0x200000 else song
    pos = s.word(song + 0x1C) & 0xFFFF if song >> 24 == 0x80 else -1
    return dict(copmusic=s.word(0x80096C70), song_id=sid, index=idx, table=hex(base), entry=entry, order_pos=pos, song=hex(song),
                song_word=hex(s.word(0x800977A0)))


def run(s):
    s.menu("take_a_ride/%s%s" % (CITY, "/night" if NIGHT else "")); s.wait_world(what=CITY)
    time.sleep(3)
    a = state(s)
    s.record("before", detail=str(a))
    s.poke32(0x80097708, 0x400)
    time.sleep(4)
    b = state(s)
    s.record("after", detail=str(b))
    s.poke32(0x80097708, 0)
    s.check("%s: chase switch fired (copmusic 1)" % CITY, b["copmusic"] == 1, str(b))
    s.check("%s: song jumped to the chase position (entry .. entry + 3 after 4 s of play)" % CITY,
            0 < b["entry"] < 64 and b["entry"] <= b["order_pos"] <= b["entry"] + 3,
            "pos %s entry %s" % (b["order_pos"], b["entry"]))
