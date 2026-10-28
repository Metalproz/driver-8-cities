# C88 / C89 design: paged Cheats menu with 4 new cheats, cheats in Survival (Polish, 24.10., analysis only)

Owner of the implementation: Infrastructure (after C40). Static facts from the D1 v1.1 exe (ghq.py) and the FRONTEND
overlay (FRONTEND.BIN, disc LBA 88, loaded at 0x801C0000, disassembled offline); GameShark lists (almarsguides.com,
Driver v1.1 misc codes) used only as pointers and they agree with the code. Classic Driver 1 must be unchanged while every
new cheat is off: every patch below is gated by its own cheat word (0 = original instruction path).

## 1. How Driver 1's cheats work today

- **Unlock table** 0x8008671C: 8 entries x 0x38 B, each a button sequence ending in -1; an unlocked cheat has its first
  word set to -2 (GameShark "View Credits Cheat Enabled" 8008671C FFFE / FFFF etc.). 0x800967D8 = number of rows (8).
- **Menu (FRONTEND):**
  - draw 0x801C753C: rows from y 0x96 every 0x24 for every unlocked entry. Names come from the pointer table at
    0x801CEA40 (8 pointers: CREDITS, INVINCIBILITY, IMMUNITY, REAR WHEEL, MINIS, STILTS, NULL, ANTIPODEAN). "On" / "Off"
    is read from row 1 0x8009681C, row 2 0x80096820, other rows 0x8009D8DC + 4 x row. "Sorry - No Cheats Activated"
    0x801C07A4 is shown when none is unlocked.
  - input 0x801C7330..0x801C74D4: cross on the cursor row (0x801CEE48) jumps through table 0x801C0728:
    - row 0: credits (starts the credits level)
    - row 1: xor 0x8009681C (Invincibility)
    - row 2: xor 0x80096820 (Immunity)
    - row 3: xor 0x8009D8DC (Rear wheel)
    - row 4: xor 0x8009D8E0 (Minis)
    - row 5: xor 0x8009D8E4 (Stilts)
    - row 6: NULL, does nothing
    - row 7: xor 0x8009D8EC (Antipodean)
- **Hidden words the menu never sets:**
  - 0x8009D8E8 = **low gravity**. StepOneCar 0x8001D7C4 reads it: gravity -0xAAA (1/4) instead of -0x2AAA. This is
    GameShark "Low Gravity Mode Enabled" 8009D8E8 0001.
  - 0x8009D8F0 = backwards mode.
- **Resets:**
  - 0x80024820..0x8002484C, when a game starts, by game type 0x800967F4:
    - type 0x13 zeroes 0x8009681C and 0x80096820
    - type 0x15 zeroes 0x80096820
  - 0x80024D10..0x80024D40 (demo / attract start) zeroes all menu cheats.
  - Replays restore cheats from the replay header (0x80024868..: 0x80097640 bits 30 / 31, 0x80097644 bits 0-3).
- **Paging to reuse:** the selector's two-page Take a Ride menu (driver_chicago.c 948-1215:
  - MenuRow tables in mod memory (MENU_ADDR)
  - the FRONTEND struct list moved there by build_package.menu_patches
  - a vblank handler that rewrites the lists per page and turns the page on cross over an R_PAGE row)
  The Cheats screen is a separate hard-coded draw / input pair, so it needs the same trick on its own tables (section 2).

## 2. Menu pages (plugin + small FRONTEND patch; PS1 path = the same patch with the tables in the overlay's free tail)

- **FRONTEND patch:** make both the draw loop and the input jump read **two per-row tables in mod memory**:
  - name pointer (replaces 0x801CEA40)
  - state-word address (replaces the fixed 0x8009681C / 0x80096820 / 0x8009D8DC + 4k reads and the 8-case jump)
  - Page 1 keeps today's 8 rows exactly, including the unlock check against 0x8008671C.
- **Plugin (vblank, like chicago_slot_vblank):**
  - On the Cheats screen it adds a last row "More cheats >" (page 1) / "< Driver 1 cheats" (page 2).
  - It turns the page on cross and rewrites the two tables.
  - Page 2 rows: INFINITE MASS, NIGHTMARE, LOW GRAVITY, SUPER SPEED, all always unlocked (no button code).
  - Page 3+ follows the same pattern for later cheats.
- **New state words:** four words in the plugin-word block next to THRS / SPTW / SPLB (proposal: 0x800933C4..0x800933D0,
  Infrastructure assigns). LOW GRAVITY reuses 0x8009D8E8 (see 3c).
- **Replays and modes:** add the four bits to the replay header (free bits of 0x80097644, bits 4-7), or replays of a
  cheat run desync. Add the words to the demo reset at 0x80024D10.

## 3. The four cheats

### 3a INFINITE MASS (player only)
- **Code:** car-car response in GlobalTimeStep (0x8001C9C4..0x8001CF0C). One impulse (sp+0x50/54/58) is applied to both
  cars plus a yaw kick (x 0x37, C82's SPTW for model 5):
  - a2 at 0x8001CA50 gates car s7 (0x8001CA58..0x8001CCB8)
  - t2 gates car s3 (block after 0x8001CCB8)
  - Mission rules already clear one side (0x8001CA00..0x8001CA4C: mission cars >= 0x17 in mission types 3 / 6), so
    "one car not moved" is a path the game already has.
  - The car id byte is +0 (player = 0). Damage: DamageCar3D 0x8003FC98 is called for both cars at 0x8001C7FC / 0x8001C824.
- **Patch (exe, PS1-native):** a jal to a small cave at 0x8001CA4C/50 that runs when INFM != 0:
  - clears a2 if the s7 car's id is 0, and t2 if the s3 car's id is 0
  - doubles the impulse for the other car (an infinite mass partner gets the full relative velocity, not half)
  - optionally skips the player's DamageCar3D call (the cheat says "never affected")
  - With INFM 0 the cave returns at once.
- **Risks:**
  - cops / AI that ram the player now bounce hard (intended)
  - the player can push cars through scenery
  - Survival / chases become easier

### 3b NIGHTMARE (every car can chase the player)
- **Code:**
  - AI records: 0x80098950 + 0x50 x n, 22 records.
    - +0x01 state; 4 = pursuit, which FUN_800635C0 resets to 2 = civilian
    - +0x05 cop flag
    - +0x10 model, +0x11 palette
  - Spawn FUN_800154A8: a car becomes a cop when 0x80096FF4 == 1 (FUN_80063B74), then gets model 1 / 2 (unmarked
    0x80096774).
  - Cop director FUN_80064A64:
    - cops on 0x800976F8
    - cap 0x80097760 (< 5)
    - Survival limit 0x80097764 (GameShark "No Cops In Survival" 80097764 FFFF)
- **Patch:** when NGHT != 0:
  - (exe, PS1) in FUN_800154A8 after the record setup: set the pursuit state / cop flag for every spawned car but KEEP its
    civilian model and palette
  - raise the cop cap so the director does not recycle them
  - keep 0x800976F8 on
  - Host-only alternative for a first test: a plugin vblank that turns state 2 into 4 for every active record.
- **To verify in game first (one run):** whether the pursuit AI needs a cop-only resource (siren / cop model / felony
  target 0x80096FC0) for non-cop models. Unmarked cops already chase in civilian models, so likely not.
- **Risks:**
  - CPU: 20 pursuers
  - roadblocks / spawning logic
  - D2 cities: the same code; the C59 "cop model only on cops" rule stays, because only the AI state changes

### 3c LOW GRAVITY (half gravity, all cars, every map)
- **Code:** StepOneCar 0x8001D7C4: `lw v0, 0x8009D8E8; bnez -> -0xAAA (0x8001D7D4); else -0x2AAA (0x8001D7D8)`.
- **Patch (exe, 1 word, PS1):** 0x8001D7D4 `2402F556` (addiu v0, zero, -0xAAA) -> `2402EAAB` (-0x1555 = half). The menu
  row sets 0x8009D8E8.
  - Side effect: the hidden 1/4 gravity GameShark code then gives 1/2 as well (nobody uses it).
  - Keeping D1's 1/4 needs a second value word instead.
- **Risks:**
  - long jumps over map edges / into D2 skyline areas never reachable before (water ring, empty regions)
  - landing on roofs
  - the C17 / C34 bridge-launch family gets worse

### 3d SUPER SPEED (player: acceleration and top speed x2)
- **Code:**
  - pad handler FUN_8001FF24 sets thrust 7200 / about -7000 at car + 0xF0 for the player
  - exe C35T (handler's last block, 0x800204CC area) already multiplies `thrust * THRS (0x800933B8) >> 12`
  - Drag in the wheel forces is linear (`- vel * 12`, as in Driver 2's wheelforces.c), so top speed scales with thrust.
- **Patch (exe, PS1):** in the C35T block, when SPD2 != 0, shift the product left by 1 (thrust x 2). Doubling THRS from the
  plugin also works on host, but the exe gate is PS1-clean and keeps Miami's 19/16 rule bit-exact when off.
  - Reverse / brake thrust stay unchanged.
  - If the measured top speed stays < 2x (a wheel-speed clamp like Driver 2's 3300 in the friction code), also raise that
    clamp under the same gate.
- **Risks:**
  - tunnelling through thin walls at 2x speed (scenery test per frame)
  - area streaming can't keep up (Chicago C45 stalls, C81-type collision hang) -> test Chicago's longest straights
  - camera lag

## 4. C89: cheats in Survival

- **Code:** 0x80024820..0x8002484C, game type 0x13 (strong evidence it is Survival):
  - 0x80024924 sets cop mode 0x80096870 = 2 for 0x13
  - the hi-score table counts it in seconds
  - the same block zeroes Invincibility + Immunity
  - type 0x15 (a second driving game, to confirm) zeroes Immunity
- **Patch (exe, 2-3 words, PS1):** gated by a word ALLC (plugin: on in the personal build, 0 = Driver 1 rule):
  - skip the stores at 0x80024838 / 0x8002483C (type 0x13)
  - skip 0x80024848 (type 0x15)
  - The other cheats are not reset there at all.
  - The new cheats read only their own words, so they already work in Survival once their patches exist.
- **Check (one run):** start Survival with Invincibility on: before, the word reads 0 in game; after, 1.

## 5. Order / effort (Infrastructure)

1. Menu pages and the four words: FRONTEND table patch + plugin page handler, reusing the selector code. About 1 day.
2. Low gravity: 1 word.
3. C89: 2-3 words.
4. Super speed: C35T gate.
5. Infinite mass: cave, about 10 words.
6. Nightmare: spawn gate + cap. Verify the pursuit AI on civilian models first.

One runner test per cheat (Miami + Chicago + one extra), all cheats off = Driver 1 unchanged (bus_head_on / camera /
interview tests still pass).
