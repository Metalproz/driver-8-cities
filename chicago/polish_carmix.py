"""polish_carmix.py - C42 step 1: a MIXED car set (Polish, 14.10.).

Switch CHI_POLISH_D2CARS=mixed: Driver 2's own Chicago traffic and cop in Driver 1's slots 0-2 (slot map
of polish_cars: 0 <- D2 3, 1 <- D2 0, 2 <- D2 1), the Driver 1 car set's own player cars (slots 5-8, its
special pages; Miami by day, LA by night as convert.car_set picks).

- Textures: the D2 civilian cars' textures come from the Chicago level itself as texrepack source "D"
  (no night darkening, own damage twins at u+128 via polish_cars.attach_twins); the player cars'
  textures and special pages from the car set (source "K", as before).
- Lump 28: slots 0-2 = D2 models (remapped from "D"), 5-8 = the car set's (remapped from "K").
- Palettes: D2's for the civilian pages (remapped from "D") + the base city's pedestrian palettes.
- Damage: <lev>.dmg.bin = civ vertex rows (3 x 300 B) + civ polygon rows (3 x 420 B) for slots 0-2
  (Infrastructure feeds it into entry 4 of the civ tables via build_package).
"""
from __future__ import annotations

import os
import struct

import polish_cars as pc


def enabled():
    return os.environ.get("CHI_POLISH_D2CARS", "") == "mixed"


HALF = int(os.environ.get("CHI_POLISH_CARMIX_HALF", "0"))   # mix2: halve the D2 car textures N times (twins alike)
COP_FULL = os.environ.get("CHI_POLISH_CARMIX_COPFULL", "") == "1"   # mix4: the cop keeps full-size textures
CIV_SLOTS = (0, 1, 2)


def cop_pages(chi_lev):
    """Texture pages of the cop model (slot 0) that no civilian model uses."""
    from models import Model
    from texrepack import model_texrefs
    cm = chi_lev.loadtime.get(28).data
    ents = pc._entries(cm)
    m = pc.slot_map()
    pages = lambda d2: {p for off in (ents[d2][0], ents[d2][2]) if off != -1
                        for p, _k in model_texrefs(Model.parse(-1, pc._model_bytes(cm, off)), {})}
    cop = pages(m[0]) if m.get(0) is not None else set()
    civ = set().union(*(pages(m[s]) for s in (1, 2) if m.get(s) is not None))
    return cop - civ


def slot_pages(chi_lev, slot):
    """Texture pages of the D2 model mapped to a Driver 1 slot (clean + low)."""
    from models import Model
    from texrepack import model_texrefs
    cm = chi_lev.loadtime.get(28).data
    ents = pc._entries(cm)
    d2 = pc.slot_map().get(slot)
    if d2 is None:
        return set()
    return {p for off in (ents[d2][0], ents[d2][2]) if off != -1
            for p, _k in model_texrefs(Model.parse(-1, pc._model_bytes(cm, off)), {})}
PLAYER_SLOTS = (5, 6, 7, 8)


def civ_models(chi_lev):
    """Model objects of the mapped D2 civilian / cop cars (clean, damage, low)."""
    from models import Model
    cm = chi_lev.loadtime.get(28).data
    ents = pc._entries(cm)
    m = pc.slot_map()
    out = []
    for s in CIV_SLOTS:
        d2 = m.get(s)
        if d2 is None:
            continue
        off = ents[d2][0]                    # the clean model has the textures (damage = vertices only)
        if off != -1:
            out.append(Model.parse(-1, pc._model_bytes(cm, off)))
        off = ents[d2][2]
        if off != -1:
            out.append(Model.parse(-1, pc._model_bytes(cm, off)))
    return out


def player_models(cars_lev):
    from models import Model
    cm = cars_lev.loadtime.get(28).data
    ents = pc._entries(cm)
    out = []
    for s in PLAYER_SLOTS:
        for k in (0, 2):
            off = ents[s][k]
            if off != -1:
                out.append(Model.parse(-1, pc._model_bytes(cm, off)))
    return out


def lump28(chi_cm: bytes, cars_cm: bytes):
    """Lump 28 bytes and the per-slot texture source ("D" / "K") for the remap."""
    d2 = pc._entries(chi_cm)
    d1 = pc._entries(cars_cm)
    m = pc.slot_map()
    body = bytearray()
    table, srcs, count = [], {}, 0
    for slot in range(13):
        row = []
        if slot in CIV_SLOTS and m.get(slot) is not None:
            cm, offs, src = chi_cm, d2[m[slot]], "D"
        elif slot in PLAYER_SLOTS:
            cm, offs, src = cars_cm, d1[slot], "K"
        else:
            cm, offs, src = None, (-1, -1, -1), None
        for off in offs:
            if off == -1:
                row.append(-1)
                continue
            data = pc._model_bytes(cm, off)
            if src == "D":                         # C57: Driver 2 units -> Driver 1 (x1.32)
                data = pc.scale_model(data)
            row.append(len(body))
            body += struct.pack("<i", len(data)) + data
            while len(body) % 4:
                body.append(0)
            count += 1
        table.append(row)
        srcs[slot] = src
    return struct.pack("<i", count) + b"".join(struct.pack("<3i", *r) for r in table) + bytes(body), srcs


def damage_civ(den_path: str) -> bytes:
    """Civ vertex rows + civ polygon rows (slots 0-2) from Driver 2's DEN file: 900 + 1260 bytes."""
    t = pc.damage_tables(open(den_path, "rb").read())
    return t["civ_verts"] + t["civ_polys"]
