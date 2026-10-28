# Classic maps: interview car pool, music tracks, selector rows (EXP, 2026-10-16, offline)
Inputs: D1 disc (games/Driver - You Are the Wheelman (USA) (v1.1).bin) via a scratchpad copy of the ISO reader; DRIVER/MISSIONS/MISSION.BLK (70736 B, LBA 63177); DRIVER/SOUND/MUSIC.BIN (886840 B); DRIVER/LEVELS/*.LEV (LBAs in the disc tree).

## 1. Selector rows (verified in earlier runs)
| selector row | route | mission no (0x80096808) | CITY | LEV | start x,y,z (D1) |
|---|---|---|---|---|---|
| Driver 1 cities: Miami | Take a Ride | 0x78 | 0 | MIAMI | 134000,164,420739 |
| Driver 1 cities: San Francisco | Take a Ride | 0x7A | 1 | FRISCO | -389478,159,179363 |
| Driver 1 cities: Los Angeles | Take a Ride | 0x7C | 3 | LA | 376863,164,-217530 |
| Driver 1 cities: New York | Take a Ride | 0x7D | 5 | NEWYORK | -136176,164,-358832 |
| Driver 1 cities: Newtown | Take a Ride | 0x7F (cheat CREDITS) | 7 | CREDITS | 19494,165,16219 |
| Driver 1 cities: Interview | Take a Ride | 0xAE | 2 | IVIEW | -10500,164,-22144 |
| Driver 1 cities: Training | submenu, not one route | - | - | - | - |
|   Training > Car park | Training | 0xAD | 2 | IVIEW | -10500,163,-22144 |
|   Training > Desert | Training | 0xAA | 6 | TRAIN | -6913,209,-103397 |
- So "Training" is a submenu (Car park = IVIEW, Desert = TRAIN). Renaming the row "Training" to "Desert" would drop the Car park route. Infrastructure should rename the Training submenu item "Desert" only if the Training row stays as the menu parent.
- Interview (0xAE) and Car park (0xAD) both load IVIEW.LEV (CITY 2), so they share the level and start; they differ in mission number only.

## 2. C64 interview car pool
- MISSION.BLK index: 124 entries (offsets 0x1F0 .. 0x11450 = file end), i.e. mission numbers 0x20..0x9B. The Interview/Car park/Desert numbers (0xAE, 0xAD, 0xAA) are outside this index (entry 0x8E = 142). So the interview's script is NOT in the MISSION.BLK entries read by the 0x20-based rule. Its car spawns are therefore not in those 124 entries.
- Candidates for where the interview car pool is set: (a) IVIEW.LEV itself (its lump 28 has car models: IVIEW's own car set, 4 special car texture pages, mocap lumps 22 x4, palettes 25; levfile showed these); (b) a second mission table read by the exe (not located); (c) exe-side mission scripts for the Undercover/Training routes (not located).
- Next: ghq.py xrefs on the mission loader (the code that reads MISSION.BLK entries) to find the index rule for numbers >= 0x9C; then decode the spawn opcodes (car model, position) of 0xAE.
- Selector entry needs: data = IVIEW.LEV + its car set (already in the LEV); exe = a mission number of 0xAE that the loader can read (index rule); spawns = unknown until (c) is located.

## 3. Music (D1 MUSIC.BIN)
- Structure (verified): int pairs {xm offset, bank offset} for 8 songs at ints 0..15 (xm/bank pairs: 68/24176, 99380/130988, 213728/243288, 329692/361184, 441236/469228, 549296/577288, 664044/697160, 768844/807652), end 886840 at int 16.
- Track names: "Briefcase", "Chase" and "Miami" are not in the original exe strings (only "Chase" at 0x80010D7C as a substring; "NEWYORK" is the LEV name table at 0x80010083 / 0x8001011B). So the names are not in the exe; the mapping must come from the mission scripts' music opcode or from the game's song-select code (0x8004D208 song init reads song*8 of MUSIC.BIN; NOTES).
- Open: song index for "The Briefcase", "Chase Mission", New York night, Miami night; the gp+0x217C and (mission+3)&7 rule were not checked (needs ghq decomp of the caller of 0x8004D208).

## 4. Update (EXP, 2026-10-16): loader rule, music rule, Interview entry, exported songs
- Mission loader (ghq decomp FUN_000686bc @0x800686bc): a segment table at 0x8008C1E8 of (key u16, value u16) pairs, ends 0x7FFF. It takes the first key >= mission number and reads MISSION.BLK index entry idx = mission - key + value (LoadfileSeg reads the 8-byte index pair). So the 0x20 rule was wrong: the Interview (0xAE) is entry 118 (key 0xAE, value 118), Car park (0xAD) entry 117, Desert (0xAA) entry 114, Miami (0x78) entry 88 (key 0x7F, value 95 -> 120-127+95).
- Song rule (same function): DAT_000977A0 = (mission + 3) & 7, passed to InitMusic (FUN_0004D208 caller FUN_00022818) unless city_index == 4 (Flat). Mapping: Miami 3, SF 5, LA 7, NY 0, Newtown 2, Interview 1, Car park 0, Desert 5, Miami night (0x79) 4, SF night (0x7B) 6.
- Mission interpreter (FUN_00068928 jump table 0x800110D8): 0x22 = city_index, 0x1F = night, 0x34 = DAT_000C7030 (value), 0x43 = DAT_000967BF (byte = the car pool / car set argument passed to FUN_0001AF2C in the mission setup), 0x13 = start-position pair (x,z), 0x3D = DAT_00096898 = 3 (the spawn/AI state), 0x27/0x28 flags, 0x40/0x54/0x59 more variables.
- Interview entry 118 text and values: start x,z = (-10500, -22144) via 0x31; timer 0x18 = 10000; text "Well done!" (0x6C6C6557..). It has NO 0x43 opcode, so DAT_000967BF is not set by the Interview script; Car park (117) and Desert (114) set 0x43 = 0.
- Car spawns: not decoded. The spawn call is FUN_0001AF2C(0x17, ..., DAT_000967BF, 4) in FUN_00022818; the model/position list is in its arguments and the Interview has no explicit car-set byte. Next: decompile FUN_0001AF2C.
- Songs exported: driver_personal/findings/d1_music/song0.xm .. song7.xm (raw Extended Module, patterns only; samples are the VAG bank after each XM in MUSIC.BIN) + README.txt with the mission map. "The Briefcase" / "Chase Mission": not named in the exe; identify by ear (chase = a mission with an XM position table, 0x8008AA04).

## 5. Interview cars and rendered songs (EXP, 2026-10-16)
- Spawn call (FUN_00022818, ghq decomp): `if (DAT_00096898 == 3 || DAT_00096898 == 8) FUN_0001AF2C(0x17, DAT_00097668+4, *(short*)(DAT_00097668+0x10), DAT_000967BF, 4)`. DAT_00096898 = 3 is set by mission opcode 0x3D; = 8 is set for missions 0xAA..0xB3 except 0xAE (then DAT_000967BF = 0 is forced).
- FUN_0001AF2C (ghq decomp): clears car slot 0x17 (player_car + 0x17*0x18C), sets its position from the mission position (DAT_00097668+4), heading from DAT_00097668+0x10, and writes the AI record byte +0x10 = model (param_4 = DAT_000967BF), +0x11 = param_5 (4), mode +0x01 = 7 (for slots != 0). So one mission car, slot 0x17, model = DAT_000967BF.
- Car park (0xAD) and Desert (0xAA): one mission car, model DAT_000967BF = 0 (opcode 0x43 operand 0 or the 8-rule reset), position from the script's 0x13/0x31 values, heading from the script. Model slot 0 is the D1 cop model in LA (lump 28); to confirm in game.
- Interview (0xAE, entry 118): no 0x3D opcode and the 8-rule excludes 0xAE, so DAT_00096898 stays and no mission car spawns. Its cars are the normal IVIEW traffic (IVIEW.LEV's car set) plus DAT_00096854 = 1 (set for CITY 2 in FUN_00022818). Random choice: only the traffic spawner (not decoded).
- Selector Interview entry: data = IVIEW.LEV (already has its car set); exe = nothing new: the original path with mission 0xAE and CITY 2 sets all of the above (the loader rule now reads entry 118). So the entry reproduces the pool when it runs mission 0xAE with CITY 2.
- Songs: rendered to driver_personal/findings/d1_music/song0_NY.wav .. song7_LA.wav (60 s each) with xmrender.py (superpacked XM + ADPCM bank, our minimal player; song4 cut at a desynchronised pattern). Chase clips not identified (table 0x8008AA04 not clear).

## 6. Interview check in the game (EXP, 2 runs, devtest/exp, port 4450)
- Run 1 (classic menu, build-test default package): Take a Ride list has 4 rows (Miami, SF, LA, NY); 5 downs wrapped to SF (mission 0x7A, CITY 1). Not the Interview; no cars in 20 s (0 AI cars at 5 samples). Shows the classic list has no Interview row.
- Run 2 (pages menu, Chicago-slot package var_roads_b13_day, slot state "la"): Take a Ride > page 1 > 5 downs > cross: mission word 0x7C (LA), CITY 2, DAT_00096898 0, car-set byte DAT_000967BF 2 (stale), DAT_00096854 0, night 0. No AI cars in 20 s (0 active in 5 samples).
- So the selector's Interview row loads CITY 2 with the LA mission number 0x7C, not 0xAE. The original first mission is 0xAE (Undercover > New Game, CITY 2 with DAT_00096854 = 1 set by the 0xAE setup). Differences found: mission word (0x7C vs 0xAE), DAT_00096854 (0 vs 1 in the original path; 0x7C is not in the 0xAA..0xB3 range), and no mission car (no 0x3D).
- Not measured: (b) the original Undercover first mission in the same build (run limit reached); earlier b15 runs of the same path showed mission 0xAE, CITY 2, DAT_00096854 1 (cars not counted then).
- Fix suggestion (Infrastructure): the Interview row must write the mission word 0xAE (the rule in FUN_000686BC reads entry 118) and set DAT_00096854 = 1 for CITY 2, as FUN_00022818 does for mission 0xAE. Also check that the Interview loads the traffic (AI spawns were 0 in both runs; check CHI_ROADS / road lumps on the Chicago-slot package, as with the mix4 probe).

## 7. C63: "The Briefcase" and the LA day recordings (EXP, 2026-10-16)
- Mission "THE BRIEFCASE" = MISSION.BLK entry 14 (text in the entry). Segment rule (table 0x8008C1E8): idx = mission - key + value; first key 0x2C value 43, so mission = idx + 1 = 15 (0x0F). Song = (15+3)&7 = 2 (the song-2 XM: 117 BPM).
- "Chase the boat." = entry 47 = mission 0x30 (48): song (48+3)&7 = 3 (Miami's song, XM 133 BPM).
- Audio (references decoded with soundfile/libsndfile MP3): "LA DAY MUSIC" = 299 s, onset tempo 117.5 BPM; "LA DAY CHASE" = 308 s.
  Renders (our minimal player): song2 117.5 BPM, song3 117.5 BPM (render), song0 112. The main reference best matches song2 in band-energy correlation (0.37 at 20 s, 0.22 at 45 s, others <= 0.19), but the margins are small.
  Chase reference: no match above 0.19 for songs 2 or 3 (best 0.10-0.12 at 150-200 s): NOT identified.
- Result: LA DAY MUSIC = song 2 (the Briefcase mission's song) is the best candidate by mission mapping and tempo; the chase recording's song and position are NOT identified (the coordinator's chase position table 0x8008AA04 is not decoded). The feature match is weak because our renderer's timbre differs from the original sample bank.
- Chase test (order position 11, 60 s renders, LA DAY CHASE recording, band correlation): song 2 from order 11 = 0.051 (worst of the set); the controls scored 0.058-0.151, best song 5 (0.151 at 199 s). NOT confirmed: the chase recording is not song 2 from order position 11 by this measure. The table 0x8008AA04 value 11 does not identify the chase track.
