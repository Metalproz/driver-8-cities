"""cityprofile.py - Milestone 3 (user 54/55): one profile per Driver 2 city for the converter and the package.

Everything city-specific that used to be hard-wired for Chicago lives here; the converter modules read it from P.
Chicago's profile holds exactly the old values, so a Chicago conversion stays byte-identical (checked with
setup_chicago --auto against var_polish_specdmg2 day / night: .lev + all sidecars).

Select the city with CHI_CITY (default CHICAGO). Pure data: no imports of the converter modules (inputs.py,
worldscale.py, convert.py ... import this one).

HAVANA (M3 Havana pass, 24.10.): values from D2 disc 1 / REDRIVER2 (start, sky, sea level, cars, specials, banks,
landmarks); Chicago-only fix lists (quays, rail cuts) stay empty (Havana has no Chicago river walk).
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field


@dataclass(frozen=True)
class CityProfile:
    name: str                                   # upper case, as Driver 2 names the level files
    label: str                                  # for reports
    # inputs (inputs.INPUTS keys)
    lev_day: str
    lev_night: str | None
    den: str | None                             # damage zones (D2 cars)
    lcf: str | None                             # car cosmetics (D2 cars)
    sky_raw: str | None                         # Driver 2 sky (polish_sky)
    # placement (worldscale)
    centre_d2: tuple                            # centre of the Driver 2 object extents (x, z)
    cells: tuple = (480, 630)                   # Driver 1 grid (16 x 21 regions, a ring of empty regions)
    start_d2: tuple | None = None               # Take a Ride start (build_package)
    start_rot: int = 0                          # its heading (4096 = full turn; build_package -> plugin, M3)
    # car sets without D2 cars: day / night -> Driver 1 car set
    car_sets: dict = field(default_factory=lambda: {"day": "miami", "night": "la"})
    # water / shore (convert.py)
    area_tex_limit: int = 220                   # textures one area may need (convert AREA_TEXTURE_LIMIT, CHI_AREA_TEX)
    area_single_over_ok: bool = False           # a one-region area over the limit: accept (more halving) instead of failing
    water_level: int = 1084
    map_water: tuple = (1, 12)                  # overhead-map palette indices of water (sea_kinds: water vs building block)
    inside_follow: bool = False                 # building-block cells (no surface) take the nearest street's level, not 0
    sea_tiles_water: bool = False               # 'void' cells under Driver 2's own sea tiles (tile models with the sea flag 0x80) are water
    night_tiles_third: bool = False             # night: textures of ground tiles x 1/3 (D2 DrawTILES: colour = combointensity / 3)
    night_models_d2: bool = False               # night: other model textures as in D2's NLEVELS (D2 draws buildings at ambient 0x80 = 1.0); sprites x 1/3
    raised_ground: tuple = ()                   # D1 road-map levels (y down) that are ground, not decks (C17 deck fix skips them)
    wall_depth: int | None = None               # generated shore walls' depth (None: 2000 + water_level - 1084)
    light_turn: dict = field(default_factory=lambda: {"TLIGHT01": 48})        # model name -> yang steps (of 64)
    light_rename: dict = field(default_factory=lambda: {"TLIGHT02": "TLIGHT00"})   # -> Driver 1's glow-table names
    water_model: int = 683                      # free in-memory model slot < 900 for the water tile
    water_relocate: bool = False                # the Driver 2 model at water_model moves to a new last index first (no free slot)
    resident_models: tuple = ()                 # Driver 2 AREA models (by name) made in-memory (glow models Driver 1 resolves by name at load)
    water_tex: tuple = ()                       # a basin's own rim / water textures (C75)
    wall_texture: tuple | None = None           # (source, page, detail) of the quay wall texture
    quay_models: tuple = ()
    quay_rail_src: tuple = ()
    quay_drop: tuple = ()
    quay_ghost_2: tuple = ()                    # QUAYFILL mode 2
    quay_ghost_34: tuple = ()                   # QUAYFILL modes 3 / 4
    quay_spot: tuple | None = None              # quay_wall (D1)
    rail_inclines: frozenset = frozenset()
    rail_cuts: tuple = ()
    rail_floor: int = 1352
    hidden_engine_models: frozenset = frozenset({"BOEING"})
    # textures (polish_tex)
    landmark_prefix: tuple = ()
    # Driver 2 cars (polish_cars / polish_specials / build_package)
    d1_from_d2: dict = field(default_factory=dict)
    special_by_area: tuple = ()
    specials: tuple = ()
    special_default: int | None = None
    special_slot_entries: int = 16              # texture entries reserved for the specials slot (most textures of one special)
    car_banks: dict = field(default_factory=dict)  # Driver 2 model -> VOICES2 bank (REDRIVER2 car_banks[city])
    # music (build_package / plugin, Infrastructure): Driver 2 MUSIC.BIN songs of Take a Ride day / night (REDRIVER2
    # main.c musicType, retail branch) and their chase-cue order positions (gamesnd.c xm_coptrackpos_d2)
    songs: tuple = ()
    chase_pos: tuple = ()

    def is_day_lev(self, path: str) -> bool:
        import inputs
        return inputs.is_input(path, self.lev_day)

    def is_lev(self, path: str) -> bool:
        import inputs
        return inputs.is_input(path, self.lev_day) or bool(self.lev_night and inputs.is_input(path, self.lev_night))


CHICAGO = CityProfile(
    name="CHICAGO", label="Chicago",
    lev_day="d2_CHICAGO.LEV", lev_night="d2_CHICAGO_night.lev", den="d2_CHICAGO.DEN", lcf="d2_CHICAGO.LCF",
    sky_raw="d2_SKY0.RAW",
    centre_d2=(-119488, 65984),                 # D2 object extents x -461056..222080, z -570880..702848
    start_d2=(9216, 106496),
    car_sets={"day": "miami", "night": "la"},
    water_level=1084, water_model=683,
    water_tex=("RIVER", "BUKFON", "FOUNT", "POOL", "WATER"),
    wall_texture=("C", 1, 3),                   # Driver 2's RIVER3A
    quay_models=(1113, 1114, 1115),
    quay_rail_src=(1113, 1114),
    quay_drop=(1000, 1115, 117, 119, 122),
    quay_ghost_2=(1000, 117, 119, 122),
    quay_ghost_34=(1000,),
    quay_spot=(-82020, -219317),
    rail_inclines=frozenset((369, r) for r in list(range(860, 867)) + list(range(873, 880))),
    rail_cuts=((602, 796),),
    rail_floor=1352,
    hidden_engine_models=frozenset({"BOEING"}),
    landmark_prefix=("NAVPIR", "ARTINST", "MRCHMRT", "WRGLY", "WRGFLD", "WRIG", "FMNH", "ADDLER", "ADLER", "CHINAL",
                     "CHINAU", "CHINA", "SDRFLD", "MEGFLD", "JOHNH", "STOLHA", "333NW", "CHISTR", "SDTL", "CABGRN",
                     "WICKL", "STNICH", "ELTRAIN", "ELTRK", "EL_", "SEARS", "PICASS", "BUCKING", "TRIB"),
    d1_from_d2={0: 0, 1: 1, 2: 2, 5: 12, 6: 9, 7: 10, 8: 8},
    special_by_area=(5, 1, 3, 3, 2, 2, 2, 3, 3, 3, 3, 1, 1, 1, 2, 3, 2, 2, 3, 0),   # spool.c SpecialByRegion[0]
    specials=(8, 9, 10, 12),
    special_default=10,
    car_banks={0: 4, 1: 12, 2: 4, 3: 13, 4: 5, 5: 16, 6: 9, 7: 2, 8: 16, 9: 9, 10: 2, 11: 15, 12: 10},
    songs=(2, 6), chase_pos=(7, 8),
    night_tiles_third=True,                     # Q73 = A (user 30.10.): Chicago night = the D2 night rules (C125 + C128),
    night_models_d2=True,                       # = var_polish_q73_night (CHI_POLISH_NIGHT_D2=0: the old Chicago night)
)

HAVANA = CityProfile(
    name="HAVANA", label="Havana",
    lev_day="d2_HAVANA.LEV", lev_night="d2_HAVANA_night.lev", den="d2_HAVANA.DEN", lcf="d2_HAVANA.LCF",
    sky_raw="d2_SKY1.RAW",                      # REDRIVER2 sky.c: GameLevel 1 -> SKY1.RAW (day 0, night +0x10000)
    centre_d2=(-11158, -90171),                 # D2 object extents x -494387..472071, z -388789..208446
    start_d2=(-238668, -235595),                # D2's own Take a Drive start (MISSIONS.BLK 52 / 53, rotation 1025)
    start_rot=1025,
    car_sets={"day": "miami", "night": "la"},   # without D2 cars
    area_single_over_ok=True,                   # one harbour-side region alone sees 253 textures (limit 220): accepted;
                                                # a higher limit (260) merged areas into a 266 KB model spool (> 256 KB)
    # hav4 (27.10.): Driver 2's surface heights are y-up (levels() h = -object y): the "2048" quarter is RAISED 2048 above
    # the main level 0 (its objects sit at y -2048), not a harbour basin. The harbour water sits just under the main
    # level: SEAWALLN quay walls reach 111 below it and the three static FERRY objects float at y 111 -> water D1 ~150
    # (hav2 / hav3 had 2750 from the wrong reading = 2600 too deep). (hav5: the 'cliffs to the sea' were building
    # blocks read as water, see map_water; no raised quarter touches the sea.)
    water_level=160,
    # hav5 (27.10.): Havana's overhead map draws the sea in palette 4 (+ 5 coast shading, 1 sea labels); 12 is a grey
    # building colour there (Chicago: 12 = lake). With Chicago's (1, 12) most building blocks read as water (the raised
    # quarter looked like an island over 'sea', cars were lifted 2880 at the fake shores). Blocks follow their streets'
    # level (0 inside the raised quarter dropped cars 2700 at every block edge).
    map_water=(1, 4, 5),
    inside_follow=True,
    raised_ground=(-2703, -2726),
    # (raised_ground: the raised quarters (D2 h 2048 / 2065) are ground, not Lake-Shore-style decks)
    night_tiles_third=True,                     # C125 (hav7 night): see RIO
    night_models_d2=True,                       # hav8 (C128 rule, Strategy 28.10.): night textures as D2's (lamp heads BLAMP2 lit)
    wall_depth=3200,                            # (hav4; deep enough for any shore level, kept: hav5 no longer needs it)
    light_turn={"TLIGHT1": 32, "SLIGHT2": 32},  # arms to +x like Driver 1's / Chicago's lights
    light_rename={"TLIGHT1": "TLIGHT00", "SLIGHT1": "SLIGHT01", "SLIGHT2": "SLIGHT02", "DLIGHT1": "SLIGHT00"},
    water_model=124,                            # hav6: D2 Havana uses 683 (an area model, 2 objects): it replaced the water tile in the
                                                # runtime model table (no sea flag 0x80, no drowning). 124 = BUILDING0018, in-memory, never placed
    wall_texture=("C", 0, 16),                  # Havana's SEAWALLN (24 x 80) for the generated shore walls
    hidden_engine_models=frozenset({"BOEING"}),
    landmark_prefix=("CPTLIO", "CATHDR", "TEATRO", "STADIU", "CFUERZ", "PALCOR", "MONUME", "MINIS", "BIGHOT",
                     "PRTHTR", "PRMRTI", "LCHAPE", "CASWPT"),   # Capitolio, cathedral, Gran Teatro, stadium, La Fuerza ...
    d1_from_d2={0: 0, 1: 1, 2: 2, 5: 12, 6: 9, 7: 10, 8: 8},   # D2 missions: residentModels {1, 2, 3, 0} as in Chicago
    special_by_area=(2, 4, 1, 1, 4, 4, 3, 3, 3, 3, 5, 0, 0, 0, 0, 0, 0, 0, 0, 0),   # spool.c SpecialByRegion[1]
    specials=(8, 9, 10, 11, 12),                # values 1..5 + 7
    special_default=11,                         # D2 Take a Drive residentModels[4]
    special_slot_entries=17,                    # model 10 uses 17 textures
    # REDRIVER2 gamesnd.c MapCarIndexToBank, car_banks[1] = {10, 11, 7, 6, 17, 17, 2, 5, 4}
    car_banks={0: 11, 1: 10, 2: 11, 3: 7, 4: 6, 5: 17, 6: 17, 7: 2, 8: 17, 9: 17, 10: 2, 11: 5, 12: 4},   # 8: model 8 ->
                                                # index 7 > 6 -> 4 -> 17 (was 6 until 28.10., Strategy item 5)
    songs=(1, 5), chase_pos=(0xB, 9),
)

# M3 Las Vegas / Rio (Strategy 27.10., user request; Driver 2 disc 2): values from the discs / REDRIVER2 with Havana's lessons
# (map water palette, building blocks follow their streets, a water slot no area list writes). NOTES "Las Vegas / Rio".
VEGAS = CityProfile(
    name="VEGAS", label="Las Vegas",
    lev_day="d2_VEGAS.LEV", lev_night="d2_VEGAS_night.lev", den="d2_VEGAS.DEN", lcf="d2_VEGAS.LCF",
    sky_raw="d2_SKY2.RAW",                      # sky.c: GameLevel 2 -> SKY2.RAW
    centre_d2=(-74208, 380413),                 # D2 object extents x -436672..288256, z -220934..981760
    start_d2=(143285, 621193),                  # Take a Drive (MISSIONS.BLK 54 day; 55 night 142533, 621049), rotation 2050
    start_rot=2050,
    car_sets={"day": "miami", "night": "la"},
    area_single_over_ok=True,
    # the Lakeside lake: D2 draws its water at street level (flat tiles, model 172, surface y 0) over banks sloping to
    # 830 below; water just under the street like Havana's (C28 turns the drowned banks into water)
    water_level=40,
    map_water=(7,),                             # overhead map: 7 = the lake (216, 240, 240); 11 = desert
    inside_follow=True,
    # freeway interchanges (768..1408 up) stay decks (C17 rule as Chicago's)
    # vegas4 (C128): TLIGHT02 is D2's pole traffic light (objanim.c GameLevel 2 case 1: lenses (-4, -537 / -466 / -395, -41),
    # facing -z like Chicago's TLIGHT01 pole) -> Driver 1's pole kind TLIGHT01, turned 48 like Chicago's
    light_turn={"TLIGHT01": 32, "SLIGHT01": 32, "SLIGHT02": 32, "TLIGHT02": 48},   # arms point -x (2198 / 929 / 688): to +x
    # vegas2 (Infrastructure 28.10.): Driver 1 draws ONE glow for SLIGHT00 and two for SLIGHT01: the double-headed DLIGHT01
    # becomes SLIGHT01, the single-headed SLIGHT01 SLIGHT00 (vegas1: DLIGHT01 -> SLIGHT00, one glow on a double lamp)
    light_rename={"TLIGHT01": "TLIGHT00", "DLIGHT01": "SLIGHT01", "SLIGHT01": "SLIGHT00", "TLIGHT02": "TLIGHT01"},
    night_tiles_third=True,                     # C125: see RIO
    # vegas4 (C128): D2 draws its buildings at night at ambient 0x80 (= 1.0, draw.c SetupPlaneColours(combointensity),
    # NightAmbient 128) with the NLEVELS textures as they are: the casino signs (FLAMINGO, IMP01-05, WSIGN, NEWY, EXC,
    # MONTENT, DTSYN, MISCSNS ...) are as bright as (or brighter than) by day = lit neon; the converter's x0.3 'as bright as
    # by day' rule (Chicago's look) dimmed 79 of them. Sprites (trees) x 1/3 as D2's lightLevel / 3
    night_models_d2=True,
    # vegas5 (C132 c, Infrastructure): glow kind 4 = SLIGHT02; Driver 1 resolves glow models by name at level load
    # (FUN_80052A78): D2's SLIGHT02 is an area model -> made in-memory
    resident_models=("SLIGHT02",),
    water_model=426,                            # unnamed in-memory model, never placed, no instance / LOD use (683 exists here)
    hidden_engine_models=frozenset({"BOEING"}),
    landmark_prefix=(),
    # player choice 0 = D2's Take a Drive car (MISSIONS.BLK 54 / 55 playerCarModel 1), not the secret car 12 (C124, 28.10.)
    d1_from_d2={0: 0, 1: 1, 2: 2, 5: 1, 6: 9, 7: 10, 8: 8},
    special_by_area=(2, 4, 1, 1, 1, 1, 1, 1, 4, 2, 3, 3, 5, 0, 0, 0, 0, 0, 0, 0),   # spool.c SpecialByRegion[2]
    specials=(8, 9, 10, 11, 12),
    special_default=9,                          # MISSIONS.BLK 54 residentModels[4]
    special_slot_entries=18,                    # special 8 uses 18 textures
    car_banks={0: 3, 1: 14, 2: 3, 3: 4, 4: 6, 5: 11, 6: 9, 7: 2, 8: 11, 9: 9, 10: 2, 11: 17, 12: 10},   # car_banks[2]
    songs=(3, 0), chase_pos=(0x12, 0x10),
)

RIO = CityProfile(
    name="RIO", label="Rio de Janeiro",
    lev_day="d2_RIO.LEV", lev_night="d2_RIO_night.lev", den="d2_RIO.DEN", lcf="d2_RIO.LCF",
    sky_raw="d2_SKY3.RAW",                      # sky.c: GameLevel 3 -> SKY3.RAW
    centre_d2=(-21067, -62344),                 # D2 object extents x -324246..282112, z -539136..414448
    start_d2=(24453, -497793),                  # Take a Drive (MISSIONS.BLK 56 day; 57 night 24441, -497800), rotation 1025
    start_rot=1025,
    car_sets={"day": "miami", "night": "la"},
    area_tex_limit=int(os.environ.get("CHI_POLISH_RIO_TEX", "200" if os.environ.get("CHI_POLISH_XDRAW") == "1" else "190")),
                                                # (_xd: 190 gives > 31 areas: the specials' area mask is an int32)   # rio2: 190 -> 30 areas, 68.6 % (200: 27, 71.5 %);   # 220: 13 areas, 272 KB spool (> 256 KB), 78.9 %; 170: 43 areas (> 31: specials mask)
    area_single_over_ok=True,
    # the sea (and the Lagoa) is drawn at street level (sea tiles 783 / 51 at y 0, flags 0x80), beaches at 0
    water_level=40,
    map_water=(4,),                             # overhead map: 4 = sea and lagoon (208, 240, 240)
    # rio2 (28.10.): the coast strips between the beaches and the map's sea are land colour (15) without a D2 surface ->
    # 'void' (drowning, but no water drawn: a grey gap). Driver 2 covers them with its own sea tiles (51 / 777 / 783, sea
    # flag 0x80, surface at y 0): those cells become water (our tiles + drowning), as in Driver 2
    sea_tiles_water=True,
    # rio3 / vegas3 / hav7 (C125, 28.10.): D2 draws every ground tile at night with colour combointensity / 3 (tile.c
    # DrawTILES, NightAmbient 128 -> 42); its NLEVELS road textures are only 0.6-0.8 of the day ones here (Chicago's: 1.0,
    # darkened by the converter's 'as bright as by day' rule), so the roads stayed day-bright under the night sky
    night_tiles_third=True,
    night_models_d2=True,                       # rio4 (C128 rule, Strategy 28.10.)
    inside_follow=True,
    light_turn={"TLIGHT01": 32, "SLIGHT01": 32},  # arms point -x (770 / 580)
    light_rename={"TLIGHT01": "TLIGHT00"},
    # no model slot < 900 is free (every one is placed, an instance source or a LOD target): the in-memory model 723
    # (unnamed, one object) moves to a new last index and its slot takes the water tile
    water_model=723, water_relocate=True,
    hidden_engine_models=frozenset({"BOEING"}),
    landmark_prefix=(),
    # player choice 0 = D2's Take a Drive car (MISSIONS.BLK 56 / 57 playerCarModel 1; FEmain carNumLookup[3][0] = 1), not
    # model 12 = D2's secret car (pause.c 'make our current car the secret car'; Rio's is a box truck): Strategy 28.10. (C124)
    d1_from_d2={0: 0, 1: 1, 2: 2, 5: 1, 6: 9, 7: 10, 8: 8},
    special_by_area=(2, 5, 4, 1, 2, 1, 4, 3, 2, 2, 2, 2, 3, 3, 3, 0, 0, 0, 0, 0),   # spool.c SpecialByRegion[3]
    # specials 10 and 12 need 21 slot entries each: the slot page (8) has 12 own entries, a page holds <= 31 -> at most 19:
    # left out for now (their areas get no special), see NOTES
    specials=(8, 9, 11),
    special_default=8,                          # MISSIONS.BLK 56 residentModels[4]
    special_slot_entries=18,                    # special 8 uses 18 textures
    car_banks={0: 7, 1: 8, 2: 7, 3: 13, 4: 9, 5: 2, 6: 17, 7: 17, 8: 2, 9: 17, 10: 17, 11: 11, 12: 16},   # car_banks[3]
    songs=(4, 7), chase_pos=(0xC, 0xA),
)

PROFILES = {p.name: p for p in (CHICAGO, HAVANA, VEGAS, RIO)}
PROFILES["LASVEGAS"] = VEGAS
# test packages only (Polish runner checks): CHI_START_<CITY>="x,z[,rot]" (Driver 2 units) moves that city's Take a Ride
# start (teleports far from the start leave stale road-map barrels). Never set for a conversion: polish_areas lays the
# areas out from the start.
for _k, _p in list(PROFILES.items()):
    _v = os.environ.get("CHI_START_" + _k)
    if _v and _k == _p.name:
        import dataclasses as _dc
        _f = [int(t) for t in _v.split(",")]
        PROFILES[_k] = _dc.replace(_p, start_d2=(_f[0], _f[1]), start_rot=_f[2] if len(_f) > 2 else _p.start_rot)
        if _k == "VEGAS":
            PROFILES["LASVEGAS"] = PROFILES[_k]
# C143 (Analyst 30.10., NOTES "C143 horn mapping"): Driver 2's Take a Drive banks: the cop (slot 3) shares the slot-2
# civilian's bank (gamesnd.c MapCarIndexToBank: model < 3 ? model : model - 1), the special slot 4 and special / secret
# player choices take SpecialVehicleKludge by ResidentModelsBodge (3 = special 1, 4 = special 2, 5 = secret car).
# CHI_POLISH_D2BANKS=1 (test switch until Infrastructure adopts it): these entries replace the profile's car_banks.
C143_BANKS = {
    "CHICAGO": {0: 13, 8: 2, 9: 18, 10: 2, 11: 18, 12: 10},     # cop = model 3's 13; kludge {2, 18, 10}
    "HAVANA": {0: 7, 8: 17, 9: 17, 10: 2, 11: 2, 12: 4},       # cop = model 3's 7; kludge {2, 17, 4}
    "VEGAS": {0: 6, 8: 11, 9: 9, 10: 9, 11: 9, 12: 13},        # cop = model 4's 6 (D2 slot 2 = 4); kludge {9, 11, 13}
    "RIO": {0: 13, 8: 17, 9: 17, 10: 17, 11: 11, 12: 15},      # cop = model 3's 13; kludge {17, 11, 15}
}
# C143 side find (Analyst) / Strategy 30.10. (exact D2 replica): Driver 2's Take a Drive civilians per time of day
# (MISSIONS.BLK 50-57 residentModels[0..2]); our AI slots 1-3 = D2 models 1-3 everywhere, Las Vegas differs:
# day {1, 3, 4}, night {1, 2, 4}. CHI_POLISH_D2TRAFFIC=1: AI slots 1-3 follow (polish_cars, by CHI_D2_LEV).
C146_TRAFFIC = {"VEGAS": {"day": {1: 1, 2: 3, 3: 4}, "night": {1: 1, 2: 2, 3: 4}}}
if os.environ.get("CHI_POLISH_D2BANKS") == "1":
    import dataclasses as _dc
    for _k, _p in list(PROFILES.items()):
        if _p.name in C143_BANKS:
            PROFILES[_k] = _dc.replace(_p, car_banks={**_p.car_banks, **C143_BANKS[_p.name]})
    PROFILES["LASVEGAS"] = PROFILES["VEGAS"]
CITY = os.environ.get("CHI_CITY", "CHICAGO").upper()
if CITY not in PROFILES:
    raise SystemExit("CHI_CITY=%s: unknown city (known: %s)" % (CITY, ", ".join(PROFILES)))
P = PROFILES[CITY]
