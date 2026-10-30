# Open for you: decisions and checks

Everything that still needs your answer or your test. Strategy keeps this list current: new items are added
as they come up, and answered items move to "Answered" with the date. Ask "what's left?" any time.
Every section is ordered by impact: what changes the engine / the whole game most comes first.

## Decisions waiting for you

None right now.

## Checks waiting for you

### Probe "d2 cities 7" (since 30.10. evening; replaces "d2 cities 6")
1. Newtown: no police in traffic, nothing floating, no falling through (also after backing out of another city's Day/Night screen) (C140/C141).
2. Unloaded areas: no black void, no colour noise; the last picture stays like in Driver 1 (C142).
3. Horns: each Driver 2 car model honks with its own Driver 2 horn; police honk too (C143).
4. Tyres touch the road on every Driver 2 car (Havana mini, Las Vegas start car, buses, fire truck); no bouncing at spawn (C144).
5. Chicago bus (and other big vehicles) lights sit on the body at night (C145).
6. Everything from d2 cities 6 still fine: freezes, sky, sounds/sirens, pause map, night looks (Chicago/Havana/Rio approved), Mods "Rewind", shadow of your car.
Known, coming next (C147): Las Vegas night player car too dark, neon colour cycling, Vegas night traffic mix.

### Questions about your last session
- 30.10. 16:33 and 16:40 (probe "d2 cities 6"): the game froze twice. What were you doing right before (city, menu, ride)? Infrastructure is analysing the dumps (C140).
1. 28.10. ~17:30-17:45 on the laptop (probe "q73 chicago night"): the game froze 3 times and crashed once (after Newtown, while driving a Driver 2 city, after picking LA day). What were you doing, and how did it look (frozen picture, black screen, sound loop)? Cause found + fixed (C135, two bugs: wrong level table for Newtown/Desert; special car overwriting memory after a city switch), now in probe "d2 cities 6". Anything else you noticed?

### Waiting for details from you
- Havana map fixes: you said you'd send details later (27.10.).

## Answered (latest first)
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
