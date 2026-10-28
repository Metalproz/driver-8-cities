"""xmrender.py - render a Driver 1 song (MUSIC.BIN: XM patterns + PS1 ADPCM sample bank) to WAV.

Minimal XM player (stdlib + array): patterns, notes, instruments mapped 1:1 to bank samples (DriverSoundTool
convention), volume, panning, speed/tempo, and the common effects (0xx arpeggio, 1xx/2xx slides, 3xx porta,
Axx volume slide, Bxx position jump, Cxx volume, Dxx pattern break, Fxx speed/tempo). Envelopes are ignored.
Output 16-bit stereo at 44100 Hz.

    python xmrender.py MUSIC.BIN SONG_INDEX OUT.wav [--seconds 60] [--start-order N]
"""
from __future__ import annotations

import array
import math
import struct
import sys
import wave

K0 = [0, 0.9375, 1.796875, 1.53125, 1.90625]
K1 = [0, 0, -0.8125, -0.859375, -0.9375]
RATE = 44100


def vag_decode(data: bytes):
    """SPU ADPCM (5 filters) -> int16 list, plus (loop_start, loop_len) in samples or None."""
    out = []
    p1 = p2 = 0.0
    loop_start = loop_end = None
    for fr in range(0, len(data) - 15, 16):
        hdr = data[fr]
        shift = hdr & 0x0F
        flt = (hdr >> 4) & 0x0F
        flags = data[fr + 1]
        if flags & 0x02 and loop_start is None:
            loop_start = len(out)
        if flags & 0x01:
            loop_end = len(out) + 28
            break
        for b in data[fr + 2:fr + 16]:
            for nib in (b & 0x0F, b >> 4):
                s = nib - 16 if nib >= 8 else nib
                v = (s << (12 - shift)) if shift <= 12 else (s << 12) >> 12 << 0
                v = float(v) + K0[flt] * p1 + K1[flt] * p2
                p2, p1 = p1, v
                out.append(max(-32768, min(32767, int(round(v)))))
    if loop_start is not None:
        return out, (loop_start, (loop_end or len(out)) - loop_start)
    return out, None


def load_bank(mus: bytes, bank_off: int, next_off: int):
    """Driver 1 bank: int count, count x (address, length, loop, samplerate), then samples."""
    b = mus[bank_off:next_off]
    count = struct.unpack_from("<i", b, 0)[0]
    descs = [struct.unpack_from("<4I", b, 4 + 16 * i) for i in range(count)]
    base = 4 + 16 * count
    samples = []
    for addr, length, loop, rate in descs:
        if length == 0:
            samples.append(([], None, rate))
            continue
        data = b[base + addr: base + addr + length]
        pcm, lp = vag_decode(data)
        samples.append((pcm, lp, rate))
    return samples


def xm_parse(xm: bytes):
    if xm[:17] != b"Extended Module: ":
        raise ValueError("not an XM")
    hsize = struct.unpack_from("<I", xm, 60)[0]
    songlen, restart, nch, npat, ninst, flags, tempo, bpm = struct.unpack_from("<8H", xm, 64)
    orders = list(xm[80:80 + songlen])
    superpacked = struct.unpack_from("<H", xm, 58)[0] == 0xDDBA
    pos = 60 + hsize
    patterns = []
    for _ in range(npat):
        plen = struct.unpack_from("<I", xm, pos)[0]
        rows = struct.unpack_from("<H", xm, pos + 5)[0]
        psize = struct.unpack_from("<H", xm, pos + 7)[0]
        data = xm[pos + plen: pos + plen + psize]
        pos += plen + psize
        cells = []
        if psize == 0:
            cells = [[(0, 0, 0, 0, 0)] * nch for _ in range(rows)]
        elif superpacked:
            # XMPlay superpacking (DriverSoundTool DecompressAndRestoreXM): per row, entries
            # [channel, note-or-flags, fields...] until 0xFF
            p = 0
            for _r in range(rows):
                if p >= psize:
                    cells.append([(0, 0, 0, 0, 0)] * nch); continue
                rownotes = [[0, 0, 0, 0, 0] for _ in range(32)]   # DriverSoundTool: XM_MAX_CHANNELS
                while p < psize:
                    ch = data[p]; p += 1
                    if ch == 0xFF:
                        break
                    if ch >= 32:
                        p = psize   # desynchronised stream: drop the rest of this pattern
                        break
                    note = data[p]; p += 1
                    x = rownotes[ch]
                    if note & 0x80:
                        for k in range(5):
                            if note & (1 << k):
                                x[k] = data[p]; p += 1
                            else:
                                x[k] = 0
                    else:
                        x[0] = note; x[1] = data[p]; x[2] = data[p + 1]; x[3] = data[p + 2]; x[4] = data[p + 3]; p += 4
                cells.append([tuple(c) for c in rownotes[:nch]])
        else:
            p = 0
            for _r in range(rows):
                row = []
                for _c in range(nch):
                    b0 = data[p]; p += 1
                    if b0 & 0x80:
                        f = [0, 0, 0, 0, 0]
                        for k in range(5):
                            if b0 & (1 << k):
                                f[k] = data[p]; p += 1
                        row.append(tuple(f))
                    else:
                        row.append((b0, data[p], data[p + 1], data[p + 2], data[p + 3])); p += 4
                cells.append(row)
        patterns.append(cells)
    instruments = []
    for _ in range(ninst):
        ihsize = struct.unpack_from("<I", xm, pos)[0]
        nsamp = struct.unpack_from("<H", xm, pos + 27)[0]
        sample_hdr_size = struct.unpack_from("<I", xm, pos + 29)[0] if nsamp else 0
        ipos = pos + ihsize
        smp = []
        for _s in range(nsamp):
            ln, ls, ll = struct.unpack_from("<3I", xm, ipos)
            vol, ft = xm[ipos + 12], struct.unpack_from("<b", xm, ipos + 13)[0]
            typ, pan, rel = xm[ipos + 14], xm[ipos + 15], struct.unpack_from("<b", xm, ipos + 16)[0]
            smp.append({"len": ln, "ls": ls, "ll": ll, "vol": vol, "ft": ft, "typ": typ, "pan": pan, "rel": rel})
            ipos += 40
        keymap = list(xm[pos + 33: pos + 33 + 96]) if nsamp else []
        instruments.append({"samples": smp, "keymap": keymap})
        pos = ipos
    return {"orders": orders[:songlen], "restart": restart, "nch": nch, "patterns": patterns,
            "instruments": instruments, "tempo": tempo or 6, "bpm": bpm or 125}


def render(xm, bank, seconds, start_order=0):
    S = xm
    tick_len = None
    speed, bpm = S["tempo"], S["bpm"]
    nch = S["nch"]
    chans = [{"smp": None, "pos": 0.0, "step": 0.0, "vol": 0, "pan": 128, "inst": 0, "note": 0, "rel": 0, "ft": 0,
              "period_note": 0, "on": False, "loop": None, "eff": 0, "param": 0, "cur_note": 0, "last_vol_slide": 0} for _ in range(nch)]
    out = array.array("h")
    total = int(seconds * RATE)
    order_i = start_order
    row = 0
    done = 0
    while done < total and order_i < len(S["orders"]):
        pat = S["patterns"][S["orders"][order_i]]
        jump_order = None
        jump_row = None
        for r in range(row, len(pat)):
            row_cells = pat[r]
            # row effects on tick 0
            for c, (note, ins, vol, eff, par) in enumerate(row_cells):
                ch = chans[c]
                if note == 97:
                    ch["on"] = False
                elif 1 <= note <= 96:
                    ch["note"] = note
                    if ins:
                        ch["inst"] = ins - 1
                    inst = S["instruments"][ch["inst"]] if S["instruments"] else None
                    if inst and inst["samples"] and inst["keymap"]:
                        si = inst["keymap"][note - 1] if note - 1 < len(inst["keymap"]) else 0
                        si = si if si < len(inst["samples"]) else 0
                        ch["si"] = si
                        sm = inst["samples"][si]
                        ch["vol"] = sm["vol"] if vol == 0 else 0
                        ch["pan"] = sm["pan"]
                        ch["rel"] = sm["rel"]
                        ch["ft"] = sm["ft"]
                        bidx = ch["inst"]
                        if bidx >= len(bank):
                            bidx = len(bank) - 1 if bank else 0
                        bs = bank[bidx] if bidx < len(bank) else None
                        if bs and bs[0]:
                            ch["smp"] = bs[0]
                            ch["loop"] = bs[1]
                            ch["rate"] = bs[2] or 8363
                            ch["pos"] = 0.0
                            ch["on"] = True
                            ch["cur_note"] = note + sm["rel"] - 1
                            ch["step"] = (ch["rate"] / RATE) * (2 ** ((note + sm["rel"] - 1 - 48) / 12.0 + sm["ft"] / 1536.0))
                elif note == 0 and ins:
                    ch["inst"] = ins - 1
                if 0x10 <= vol <= 0x50:
                    ch["vol"] = vol - 0x10
                elif 0xC0 <= vol <= 0xCF:
                    ch["pan"] = (vol - 0xC0) * 17
                ch["eff"], ch["param"] = eff, par
                if eff == 0x0F:
                    if par < 0x20 and par: speed = par
                    elif par >= 0x20: bpm = par
                elif eff == 0x0C:
                    ch["vol"] = min(64, par)
                elif eff == 0x0B:
                    jump_order = par
                elif eff == 0x0D:
                    jump_row = (par >> 4) * 10 + (par & 0x0F)
            tick_len = int(RATE * 2.5 / bpm)
            for tick in range(speed):
                for c, ch in enumerate(chans):
                    if tick > 0:
                        note, ins, vol, eff, par = row_cells[c]
                        if eff == 0x0A:
                            up, dn = par >> 4, par & 0x0F
                            ch["vol"] = max(0, min(64, ch["vol"] + up - dn))
                        elif eff == 0x01 and ch["step"]:
                            pass
                    st = ch["step"]
                    if not ch["on"] or not ch["smp"]:
                        continue
                    ch["vol"] = ch["vol"]
                if tick == 0:
                    pass
                for k in range(tick_len):
                    l = r_ = 0.0
                    for ch in chans:
                        if not ch["on"] or not ch["smp"]:
                            continue
                        i = int(ch["pos"])
                        if ch["loop"]:
                            ls, ll = ch["loop"]
                            if i >= ls + ll:
                                ch["pos"] = ls + (ch["pos"] - (ls + ll)) % ll
                                i = int(ch["pos"])
                        if i >= len(ch["smp"]):
                            ch["on"] = False; continue
                        v = ch["smp"][i] * ch["vol"] / 64.0 / 2.0
                        pan = ch["pan"] / 255.0
                        l += v * (1 - pan); r_ += v * pan
                        ch["pos"] += ch["step"]
                    out.append(max(-32768, min(32767, int(l)))); out.append(max(-32768, min(32767, int(r_))))
                    done += 1
                    if done >= total:
                        break
                if done >= total:
                    break
            if done >= total or jump_order is not None or jump_row is not None:
                break
        if done >= total:
            break
        if jump_order is not None:
            order_i = jump_order; row = 0
        elif jump_row is not None:
            order_i += 1; row = jump_row
        else:
            order_i += 1; row = 0
        if order_i >= len(S["orders"]):
            order_i = S["restart"] if S["restart"] < len(S["orders"]) else 0
    return out


def main():
    mus = open(sys.argv[1], "rb").read()
    k = int(sys.argv[2]); outp = sys.argv[3]
    secs = float(sys.argv[sys.argv.index("--seconds") + 1]) if "--seconds" in sys.argv else 60.0
    ints = struct.unpack_from("<17I", mus, 0)
    xm_bytes = mus[ints[2 * k]:ints[2 * k + 1]]
    bank = load_bank(mus, ints[2 * k + 1], ints[2 * k + 2])
    S = xm_parse(xm_bytes)
    pcm = render(S, bank, secs)
    with wave.open(outp, "wb") as w:
        w.setnchannels(2); w.setsampwidth(2); w.setframerate(RATE)
        w.writeframes(pcm.tobytes())
    print("wrote", outp, len(pcm) // 2, "frames", "instruments", len(S["instruments"]), "bank", len(bank))


if __name__ == "__main__":
    main()
