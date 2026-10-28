"""vag.py - PlayStation SPU ADPCM ("VAG" body) decode / encode and resampling (R36: Driver 2 car sounds resampled to fit
Driver 1's SPU RAM). A block = 16 bytes: (filter << 4 | shift), flags, 14 bytes = 28 4-bit samples (low nibble first).
Flags: bit 0 loop end (jump to the loop address), bit 1 repeat (with bit 0: loop; without: stop), bit 2 loop start."""
from __future__ import annotations

import os

import numpy as np

# C83 (23.10., user: engine 'slightly different', 'bugs out' on burnouts / braking): V2 = loops resampled to a whole number
# of 28-sample blocks (before: the last block padded with up to 27 zeros INSIDE the loop -> a 2.4 ms dropout every loop,
# more often the higher the revs), the loop's first block predicted from the loop's end (the SPU keeps the predictor history across the
# loop jump: a loop is encoded with the history its own end leaves) and a windowed-sinc low-pass before downsampling (linear interpolation aliased the
# engine harmonics above the new Nyquist); a source loop is decoded as played on its 2nd pass (Driver 2 encoded block 0
# with the loop end's history: decoded from silence, its first block jumped by up to 8000). CHI_VAG_V2=0: the R36 behaviour.
V2 = os.environ.get("CHI_VAG_V2", "1") != "0"

K0 = (0, 60, 115, 98, 122)
K1 = (0, 0, -52, -55, -60)


def decode(data: bytes):
    """-> (int16 samples, list of per-block flag bytes)."""
    n = len(data) // 16
    out = np.zeros(n * 28, dtype=np.int32)
    flags = []
    s1 = s2 = 0
    for b in range(n):
        hdr, fl = data[16 * b], data[16 * b + 1]
        flags.append(fl)
        shift, filt = hdr & 15, min(hdr >> 4, 4)
        k0, k1 = K0[filt], K1[filt]
        for i in range(28):
            byte = data[16 * b + 2 + i // 2]
            nib = (byte >> 4) if i & 1 else (byte & 15)
            if nib & 8:
                nib -= 16
            v = (nib << 12) >> shift
            v += (s1 * k0 + s2 * k1 + 32) >> 6
            v = max(-32768, min(32767, v))
            out[b * 28 + i] = v
            s2, s1 = s1, v
    return out.astype(np.int16), flags


def encode(pcm, loop: bool) -> bytes:
    """V2: a loop's first block is predicted from the history the loop's end leaves (iterated to a fixed point)."""
    if not (V2 and loop):
        return _encode(pcm, loop, 0, 0)[0]
    h = (0, 0)
    for _ in range(4):
        out, e1, e2 = _encode(pcm, loop, *h)
        if (e1, e2) == h:
            break
        h = (e1, e2)
    return out


def _encode(pcm, loop: bool, s1: int, s2: int):
    """int16 samples -> VAG body (blocks; the first gets loop start for a loop, the last loop end + repeat, or loop end
    alone = stop). Per block the filter / shift with the smallest error (quantised with the decoder's feedback)."""
    pcm = np.asarray(pcm, dtype=np.int32)
    n = (len(pcm) + 27) // 28
    pcm = np.concatenate([pcm, np.zeros(n * 28 - len(pcm), dtype=np.int32)])
    out = bytearray()
    for b in range(n):
        x = pcm[b * 28:(b + 1) * 28]
        best = None
        for filt in range(5):
            k0, k1 = K0[filt], K1[filt]
            # estimate the shift from the ideal (unquantised) prediction residual
            p1, p2, peak = s1, s2, 0
            for v in x:
                r = int(v) - ((p1 * k0 + p2 * k1 + 32) >> 6)
                peak = max(peak, abs(r))
                p2, p1 = p1, int(v)
            shift = 12
            while shift > 0 and (peak >> (12 - shift)) > 7:
                shift -= 1
            for sh in (shift, max(0, shift - 1)):
                q1, q2, err, nibs = s1, s2, 0, []
                for v in x:
                    pred = (q1 * k0 + q2 * k1 + 32) >> 6
                    r = int(v) - pred
                    nib = int(round(r * (1 << sh) / 4096.0))
                    nib = max(-8, min(7, nib))
                    d = max(-32768, min(32767, ((nib << 12) >> sh) + pred))
                    err += (d - int(v)) ** 2
                    nibs.append(nib & 15)
                    q2, q1 = q1, d
                if best is None or err < best[0]:
                    best = (err, filt, sh, nibs, q1, q2)
        _e, filt, sh, nibs, s1, s2 = best
        fl = 0
        if b == 0 and loop:
            fl |= 6                                    # loop start (+ repeat), as Driver 2's loops
        if b == n - 1:
            fl |= 3 if loop else 1
        out += bytes([(filt << 4) | sh, fl]) + bytes(nibs[2 * i] | (nibs[2 * i + 1] << 4) for i in range(14))
    return bytes(out), s1, s2


def lowpass(pcm, cutoff: float, loop: bool, taps: int = 63):
    """Hann-windowed sinc FIR, cutoff in cycles per sample (circular for a loop)."""
    k = np.arange(taps) - (taps - 1) / 2.0
    h = 2 * cutoff * np.sinc(2 * cutoff * k) * np.hanning(taps)
    h /= h.sum()
    m = taps // 2
    x = np.concatenate([pcm[-m:], pcm, pcm[:m]]) if loop else np.concatenate([np.zeros(m), pcm, np.zeros(m)])
    return np.convolve(x, h, mode="valid")


def resample(pcm, src_rate: int, dst_rate: int, loop: bool):
    """Linear interpolation (a loop wraps around its start); V2: low-pass first, loops cut to whole blocks."""
    pcm = np.asarray(pcm, dtype=np.float64)
    n = int(round(len(pcm) * dst_rate / float(src_rate)))
    t = np.arange(n) * (src_rate / float(dst_rate))
    if V2:
        if dst_rate < src_rate:
            pcm = lowpass(pcm, 0.45 * dst_rate / float(src_rate), loop)
        if loop:
            n = max(28, int(round(n / 28.0)) * 28)
            t = np.arange(n) * (len(pcm) / float(n))
    i0 = np.floor(t).astype(int)
    f = t - i0
    i1 = i0 + 1
    i1 = np.where(i1 >= len(pcm), 0 if loop else len(pcm) - 1, i1)
    y = pcm[np.minimum(i0, len(pcm) - 1)] * (1 - f) + pcm[i1] * f
    return np.clip(np.round(y), -32768, 32767).astype(np.int16)


def convert(data: bytes, src_rate: int, dst_rate: int, loop: bool) -> bytes:
    if V2 and loop:            # a loop as the SPU plays it from the 2nd pass on (Driver 2 predicts block 0 from the end)
        pcm = decode(data + data)[0][len(data) // 16 * 28:]
    else:
        pcm, _fl = decode(data)
    if dst_rate != src_rate:
        pcm = resample(pcm, src_rate, dst_rate, loop)
    return encode(pcm, loop)
