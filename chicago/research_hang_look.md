# Hang "look" (probe build-test 18:06, levels var_look2_day/night), snapshot 20261016-184920-v56777-hang (EXP, offline)
State (ram.bin): CITY 3, mission 0x7C (LA mission, Chicago slot), night 0, player (101769, 315, 26574), region 0xA9, area_cur 0x10,
area_flag 0 (no area load), spool_left 0, spool indices 0, level_ready 1, frame_ctr 0x1D0D: the game is in a normal level state,
not a loading stall (no C33 guard, no C45 spool wait, no CD wait loop).
CPU (regs.json): i_stat 1 (vblank), i_mask 0xD, exception_entries 128298, exception_reentry_blocks 3499, cause 0x410 = ExcCode 4 (AdEL, address
error on load), EPC 0x8005F350, current_func 0x1FC0D8E0 (not a game function), last_store_pc 0xBFC116A8 (BIOS). A load fault re-entering
the exception handler = a BIOS exception loop.
Faulting code: FUN_0005F0EC (ghq): `lh idx = (sp+0x30)`; `lw p = *(0x9F000000 + 4*idx)` (model table in mod memory, 2048 entries); `lhu v, 2(p)`.
At EPC 0x8005F350 the pointer p is read from the table; a bad p (not a valid RAM address) faults.
mod.bin (the model table at 0x9F000000): 2048 entries = 508 offset-like (< 2 MB, e.g. entry 0 = 0x132104), 708 absolute (0x9F...), 832 zero.
The offset and absolute entries alternate in runs over indices 0..~200, so the table is not one pointer per index (2 words per model or mixed
use): not yet decoded. Entries 0..70 are offset-like, so an unrelocated pointer is a candidate for the bad load.
Candidates: (a) model table entries not relocated for the new model slots (today's shared patch list: 'model table 2048 entries at 0x9F000000,
88 patches'); (b) a model index from the cell/object list that is beyond the filled part of the table. Evidence: the faulting lookup is the
model-table read in FUN_0005F0EC; the exception loop follows the AdEL.
Moon stub 0x80011868 and chase table 0x8001188C: no code reads them (ghq xrefs: total 0), so they are not the trigger.
Class: not a known freeze class in NOTES (C33 area switch, C45 spool stalls, C38/C50 Play Again): no area load, no spool wait; new.
No reproduction run (no concrete trigger yet).

## Follow-up (EXP): trigger search (offline)
- Registers in regs.json look truncated (gp 0x0000F450, sp 0x000085C0, fp 0x000085D8): not usable as KSEG0 stack pointers, so lh(sp+0x30) (the failing model index: the local short local_30[4] of FUN_0005F0EC) could not be read. Needs a dump with 32-bit sp/gp.
- Objects within 1500 units of the dump position (D1 101769, 26574; var_look2_day.lev): 5 objects, models 768, 54, 149. Their model-table entries are non-zero offset-like values (768 -> 0x14EDB4, 54 -> 0x134ACC, 149 -> 0x137728). So no zero-entry model near the player: the zero-entry trigger is NOT supported by the nearby objects.
- Note: mod.bin (0x90000 bytes) is shorter than these offsets, so the offsets point past the dumped mod area (not checked further).
- Verdict: failing model index unknown; no concrete trigger; no reproduction run.

## Root cause (EXP, offline, 2026-10-16): stale out-parameter -> bad table read
- The true sp is 0x1F800330 (scratchpad; from the BIOS exception frame at kernel 0xE1F4: sp 31st word, EPC 0x8005F350, SR 0x40000404, gp 0x96770, player x 0x18D89 in the frame). lh(sp+0x30) = 0x3640 = the low half of 0x9F013640 (a model DATA pointer, not an index).
- FUN_0005F0EC (ghq): `FUN_000217C8(pos, slot, local_30)` fills local_30[0] = model index, but the return value is ignored. FUN_000217C8 writes only when FUN_00021690 != 0.
- FUN_00021690 returns 0 when the query cell (1500-unit grid, DAT_0009E714/18 = 960 x 1260 cells) is outside the grid (checked: the player is inside: cell 548,612).
- So the query point of some car/object slot is outside the grid (or in an unloaded road region); local_30[0] keeps the stale value 0x3640 = 13888 (>2048), the code reads 0x9F000000 + 4*13888 (outside the 2048 table), gets a garbage pointer and lhu 2(p) faults (AdEL), and the BIOS exception handler re-enters forever.
- Fix route (Infrastructure, guest code): check FUN_000217C8's return in FUN_0005F0EC (skip the slot when 0), and bound-check local_30[0] < 2048 with a non-zero table entry before the lhu. The index is also only 10 bits in FUN_000217C8 ((x>>16)&0x3FF), so models >= 1024 can never be selected there (check table size assumption).
