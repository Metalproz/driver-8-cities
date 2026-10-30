# Open for you: decisions and checks

Everything that still needs your answer or your test. Strategy keeps this list current: new items are added
as they come up, and answered items move to "Answered" with the date. Ask "what's left?" any time.
Every section is ordered by impact: what changes the engine / the whole game most comes first.

## Decisions waiting for you

None right now.

## Checks waiting for you

### Not yet confirmed from earlier probes (optional, whenever you play)
- Sky: each Driver 2 city shows its own sky, day and night (C126); no noise at the start of loading (C127).
- Sounds: Driver 2 sirens; Havana chase music; Driver 2 engine sounds after moving the menu cursor over another city (C120/C121/C137).
- Pause-menu map in every Driver 2 city (C122); Mods > Quality of Life > "Rewind" and the "Full Pro experience" section (C130/C131).
- City menu page 2 pictures for Las Vegas and Rio.

### Questions about your last session
- 30.10. 16:33 and 16:40 (probe "d2 cities 6"): the game froze twice. What were you doing right before (city, menu, ride)? Infrastructure is analysing the dumps (C140).
1. 28.10. ~17:30-17:45 on the laptop (probe "q73 chicago night"): the game froze 3 times and crashed once (after Newtown, while driving a Driver 2 city, after picking LA day). What were you doing, and how did it look (frozen picture, black screen, sound loop)? Cause found + fixed (C135, two bugs: wrong level table for Newtown/Desert; special car overwriting memory after a city switch), now in probe "d2 cities 6". Anything else you noticed?

### Waiting for details from you
- Havana map fixes: you said you'd send details later (27.10.).

## Answered (latest first)
- 30.10. probe "d2 cities 7": all listed checks good (Newtown no police / no falling, no black void, horns per car,
  tyres on the road, bus lights) -> approved, shipped to your dev client (C140-C145). Later the same evening: Havana
  mini tyres too big again after driving, restart drops the car from the air, night lights not scaled to the car (C148).
- 30.10. probe "d2 cities 6" review: Newtown spawns police with missing models -> no police in Newtown (C141); black
  void in loading zones instead of D1's "last frame" (C142); horns per car model as in D2 (C143); wheel sizes of every
  D2 car as in D2, Havana mini + Vegas player car first (C144); Chicago bus lights misplaced (C145); Las Vegas night
  still unlike D2, other nights "really good" (C146). Q74: allowed; you added the permission rule (30.10.), C129 traffic work unblocked.
- 30.10. Q72 = B (Driver 2's traffic code in D2 cities, Las Vegas first; C129). Q71: free sound memory in D2 cities by
  dropping Driver 1 sounds that Driver 2 sounds replace (engines, horns), keep the rest, only load what is used; then
  D2 sirens (C137). Q69: keep the start cars for now; backlog: car select screen with every car, real names, only the
  chosen car's data loaded (ROADMAP M6). Q73 = A (Chicago lit night signs, now in "d2 cities 4"). Q70: no push, you
  upload by hand (no reminders). New: Havana mini car shadow / lights / hitbox (C138).
- 28.10. probe "d2 cities 2": laptop speed with Extra draw/Uncap is fine (C119 OK). Issues reported: all D2 maps
  use Havana's day sky (C126), sound at the start of loading (C127), Las Vegas night looks unlike D2 (C128),
  D2 traffic lanes/diagonals/curves (C129), rewind as its own Mods setting (C130), rename "Chicago" section to
  "Full Pro experience" + warning (C131). Git: yes, use it (local commits resumed 28.10.).
- 27.10. Q68 = B: Driver 2 cities stay virtual cities in LA's slot with their own menu rows.
