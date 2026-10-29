# Open for you: decisions and checks

Everything that still needs your answer or your test. Strategy keeps this list current: new items are added
as they come up, and answered items move to "Answered" with the date. Ask "what's left?" any time.

## Decisions waiting for you

| # | Since | Question | Recommendation |
|---|---|---|---|
| Q69 | 28.10. | Chicago and Havana start you in Driver 2's **secret car** (model 12). Driver 2 itself starts you in its normal car (model 1), as Las Vegas and Rio now do. Switch Chicago + Havana to the normal car? | **A:** switch to D2's normal car (as in Driver 2). B: keep the secret car. |
| Q70 | 28.10. | Git: the project history is now committed locally again (driver_personal). A GitHub remote "driver-8-cities" (public) exists from 14.10. Should commits also be pushed there? | Keep it **local only** for now (safe backup on this PC); decide on pushing later. |
| Q71 | 28.10. | Police sirens: Driver 2's sirens (6-15 KB each) don't fit in the free sound memory (1.3 KB Chicago, 5.9 KB Havana). Keep Driver 1's sirens, or make room (e.g. drop or shorten other sounds)? | Keep D1 sirens until sound memory is reworked. |
| Q72 | 28.10. | **D2 traffic lanes (C129):** Driver 1's traffic can only drive along the grid; Driver 2's diagonal lanes and curves are lost (Las Vegas: 74 diagonal roads, 157 curves). Exact copy = run Driver 2's own traffic-driving code for the D2 cities (about 45-60 KB memory per D2 city, PS1-compatible). The alternative (convert into Driver 1's grid) can only make staircase approximations. | **B:** run Driver 2's traffic code in D2 cities (only exact option); Las Vegas first. Needs installing a free PS1 compiler (GCC for MIPS, as used by PS1 homebrew) on this PC. A: grid approximation. |
| Q73 | 28.10. | **Chicago at night:** our conversion dims 55 Chicago textures at night that Driver 2 draws fully lit (e.g. the Chicago Theatre sign, the Biograph front). Las Vegas, Havana and Rio now use Driver 2's lit night textures. Chicago's current night look was approved by you earlier. Switch Chicago to Driver 2's lit signs too? | **A:** yes, as in Driver 2. B: keep the current Chicago night. **Compare:** probe "q73 chicago night" (lit) vs "d2 cities 4" (current), Chicago at night. |

## Checks waiting for you

### Probe "d2 cities 4" (since 30.10.; replaces "d2 cities 3")
- No more freezes: Newtown / Desert / Interview rides (also after LA Day/Night -> back), and switching Driver 2 cities (e.g. Las Vegas -> Rio, Chicago -> Havana) then driving (C135).
- Night look as in Driver 2: buildings lit flat, darker cars, Las Vegas lamp glow, no colour noise in map holes (C132/C134).
- Sky: each Driver 2 city shows its own sky, day and night (also after playing another city first).
- Loading a Driver 2 map after another map: no noise at the start of loading.
- Night look in Las Vegas (casino neon/signs lit, pole traffic lights glow), Havana (lamp heads lit), Rio; roads dark.
- Mods > Quality of Life > "Rewind" switches rewind on/off on its own; "Full Pro experience" section with the warning.
- Las Vegas + Rio day/night: driving, ramps, own music + chase music, Driver 2 car sounds; Rio sea drowns you; Vegas no odd colours with different cars.
- Havana chase music; Havana/Chicago Driver 2 engine sounds (also after moving the menu cursor over another city).
- Pause-menu map in every Driver 2 city (centred, d-pad scrolls, other buttons close); LA/Miami unchanged.
- City menu page 2: Las Vegas and Rio pictures.

### Questions about your last session
- 28.10. ~17:30-17:45 on the laptop (probe "q73 chicago night"): the game froze 3 times and crashed once (after Newtown, while driving a Driver 2 city, after picking LA day). What were you doing, and how did it look (frozen picture, black screen, sound loop)? Cause found + fixed (C135, two bugs: wrong level table for Newtown/Desert; special car overwriting memory after a city switch), now in probe "d2 cities 4". Anything else you noticed?
- How did Chicago at night look in both probes (Q73)?

### Waiting for details from you
- Havana map fixes: you said you'd send details later (27.10.).

## Answered (latest first)
- 28.10. probe "d2 cities 2": laptop speed with Extra draw/Uncap is fine (C119 OK). Issues reported: all D2 maps
  use Havana's day sky (C126), sound at the start of loading (C127), Las Vegas night looks unlike D2 (C128),
  D2 traffic lanes/diagonals/curves (C129), rewind as its own Mods setting (C130), rename "Chicago" section to
  "Full Pro experience" + warning (C131). Git: yes, use it (local commits resumed 28.10.).
- 27.10. Q68 = B: Driver 2 cities stay virtual cities in LA's slot with their own menu rows.
