# D2 cars round 3 (EXP, 2026-10-17, offline; sources REDRIVER2 src_rebuild/Game, forum thread t=5469)

## 1. Resident car models and loading
- dr2limits.h: MAX_CAR_RESIDENT_MODELS = 6 on PC, 5 on PSX (#ifndef PSX); SPECIAL_CAR_SLOT = MAX_CAR_RESIDENT_MODELS-1 (5 PC, 4 PSX).
  So D2 keeps 5 resident models on PSX (4 normal + the special slot), 6 on PC. The Chicago lump had 9 models; the resident set is picked per region/mission.
- residentCarModels[i] = a level model index (0 = none; civ_ai.c 2232: 0 or >4 means not spooled). The spool/special model is checked in civ_ai.c 2168 (specModelValid, allowSpecSpooling) and replaced if the special model is not valid.
- Swaps are guarded by these checks (civ_ai.c 1792 finds a slot with the external model before loading another). Allocation details (buffers, sizes) not traced in this round.
- Forum (t=5469): fan request "show all types of vehicles at the same time in every region ... instead of the current limit of 5" (confirms the 5-model limit). A crash in mission 13 after a truck in mission 12 was blamed on region differences in the vehicle set.

## 2. Max cars at once
- D2: MAX_CARS = 20 (dr2limits.h), the car_data array (player included). So civ + cop + special cannot exceed 20 at once.
- D1: our RAM work: 22 AI road-traffic records (0x80098950, 0x50 each) plus the player car. The car array was checked only up to slot 11 (stride 0x18C), so the exact D1 max is not verified (the user's 20 is close to the D2 constant).

## 3. Regional specials (Chicago)
- gamesnd.c CarHasSiren(): SPECIAL_CAR_SLOT with resident model 8 (GameLevel 0), 9 (GameLevel 2), 10 (GameLevel 3) gets a siren (SFX bank, sound 12). main.c 496 sets residentCarModels[SPECIAL_CAR_SLOT] = 9 in one case. So the special vehicle per city is a model id in the special slot; spawn tables per region: not fully read this round (civ_ai region lists not extracted).
- Hitboxes: car_cosmetics colBox per model (cosmetic.c / dr2types.h CAR_COSMETICS: colBox, cPoints[12], cog).

## 4. Car sounds
- gamesnd.c: car sound banks loaded with LoadBankFromLump(SOUND_BANK_CARS, MapCarIndexToBank(i)) for each resident slot (i = 0..4 PSX); MapCarIndexToBank uses car_banks[4][9] (4 cities x 9 values) (gamesnd.c 284-292). Engine: 3 channels per car (i*3: rev/engine loop with pitch cp->hd.revs/4 + revsvol/64 + 1500, i*3+1: idle with pitch 4096, i*3+2: siren). Horn: lcp->horn.on switches the siren channel (SetChannelPosition3 with pitch 4096); cop/special cars use SFX 12.
- Civ voices: residentCarModels[index]==0 -> SOUND_BANK_VOICES (gamesnd.c 194).
- D1 sound per car: not compared in this round (D1 uses its own SND bank: unverified).

## 5. Wheels
- cars.c 691-734: wheelSize = car_cosmetics[model].wheelSize; sizeScale = wheelSize*14142/10000 (sqrt 2 scale); wheel vertices VertPtr[20..23] set to +-wheelSize; wheel positions from car_cosmetics wheelDisp[4] (SVECTOR).
- D1: fixed wheel size/positions in the exe per slot (our notes: wheel placement is exe-side). So D2 wheel data per car must be carried per slot, as in the cosmetic table.
