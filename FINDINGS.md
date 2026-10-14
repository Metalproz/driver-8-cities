# Findings: fun facts and curiosities (Driver 1 / Driver 2)

Interesting things found while working on the project that have no or very little information online.
Not roadmap work: noted here to trace back later. Each entry: what it is, how we know (evidence), where the files are.
(User, 2026-10-13: "for future findings like this ... we should just note it somewhere".)

## F1. FLAT.LEV: an unused flat test ground on the Driver 1 disc (2026-10-13)

**What it is.** Driver 1 (PS1, NTSC-U SLUS-00842) ships 8 level files in `DRIVER/LEVELS`. They are MIAMI, FRISCO, IVIEW, LA, FLAT,
NEWYORK, TRAIN and CREDITS. FLAT is the only one the game never loads. It is level-table entry 4 (`0x80086EC0`, per-level name
"Flat" at `0x80086EE0`), and nothing in the retail game sets CITY to 4.

**What's in it** (offline export with DriverLevelTool, rendered top-down + 3D: `findings/flat_layout.png`):
- tiny: 159 objects, ~7,800 vertices, ~6,400 faces (Chicago converted: ~848,000 faces);
- completely flat: height range ≈ 0;
- one closed square road loop, plus about a dozen scattered pieces (flat tiles, small boxy building/car-park fragments);
- road data: 68 roads, 180 junctions; 54 texture pages; no mission start position.
Looks like a developer test ground for driving on flat ground: a closed loop to lap plus a few test objects.

**What it lacks** (why it can't load as a map):
- no car set: no LOADTIME lumps 25 (car palettes), 22 ×4, 28 (car models);
- none of the engine models every playable level has: SKY01-04, CLEANWHEEL/FASTWHEEL/DAMWHEEL, HUBCAP1, ped heads;
- its model-names lump does not parse as names.

**How we know it's never used:**
- EXP traced every menu route's mission number, CITY and the LEV file read: Take a Ride 0x78/7A/7C/7D, Interview 0xAE, Car park training 0xAD, Desert training 0xAA, Cheats > Credits 0x7F. None reads FLAT.LEV.
- Forcing it via LA's Take a Ride script (CITY opcode → 4) crashes at level start. With IVIEW's car set added it hangs instead (Infrastructure bisect, 13.10.).
- Story-mission scripts beyond the 124-entry MISSION.BLK index were not all scanned, but nothing points to FLAT.

**Online:** no mention found. Checked: almarsguides GameShark lists v1.0/1.1, Unseen64 Driver beta page, Driver Madness LEV threads, web searches.

**Details:** chicago/research_day_music.md (FLAT sections), WORKLOG 13.10. 19:4x-20:3x. The user decided (13.10.) not to make it playable. It was removed from the map selector and the roadmap.

## Related small facts (same investigation)
- The credits city (CREDITS.LEV, which we call "Newtown") is reached in the retail game only via **Cheats > Credits** (mission 0x7F, CITY 7, start 19494,16219). Wikipedia names it **Newcastle** (Reflections' home town) and says it's reachable on PS1 with a cheat device.
- **Interview** (Undercover > New Game, 0xAE) and the **Car park training** (0xAD) use the same map file, IVIEW.LEV. The Desert training (0xAA) uses TRAIN.LEV.
- Take a Ride mission numbers 0x79 and 0x7B are unused. The Take a Ride scripts differ only in the CITY operand (word 5) and the start position/heading (words 12-15).
