# Open for you: decisions and checks

Everything that still needs your answer or your test. Strategy keeps this list current: new items are added
as they come up, and answered items move to "Answered" with the date. Ask "what's left?" any time.
Every section is ordered by impact: what changes the engine / the whole game most comes first.

## Decisions waiting for you

| # | Since | Impact | Question | Recommendation |
|---|---|---|---|---|
| Q74 | 30.10. | **Engine, all 4 D2 cities:** blocks the Driver 2 traffic work (C129) | You said "allow it" (30.10.), but Claude Code's safety check refuses to let Claude change its own permission settings, so you have to add the rule once yourself: type `/permissions` in this chat -> Allow -> add `Bash(D:/recomps/tools/gcc-mipsel-none-elf-12.3.0/bin/*)`. | Add that one rule. |

## Checks waiting for you

### Probe "d2 cities 6" (since 30.10.; replaces "d2 cities 3/4/5" and "q73 chicago night")
1. No more freezes: Newtown / Desert / Interview rides (also after LA Day/Night -> back), and switching Driver 2 cities (e.g. Las Vegas -> Rio, Chicago -> Havana) then driving (C135).
2. Sounds in Driver 2 cities: traffic honks with Driver 2 horns, police use Driver 2's siren; back in Miami/LA the Driver 1 sounds return (C137). Loading a Driver 2 map after another map: no noise at the start (C127).
3. Sky: each Driver 2 city shows its own sky, day and night (also after playing another city first) (C126).
4. Las Vegas + Rio day/night: driving, ramps, own music + chase music, Driver 2 car sounds; Rio sea drowns you; Vegas no odd colours with different cars.
5. Havana chase music; Havana/Chicago Driver 2 engine sounds (also after moving the menu cursor over another city) (C120/C121).
6. Pause-menu map in every Driver 2 city (centred, d-pad scrolls, other buttons close); LA/Miami unchanged (C122).
7. Night look as in Driver 2: Chicago signs lit (Q73 A), buildings lit flat, darker cars, no colour noise in map holes; Las Vegas casino neon/signs lit, lamp glow, pole traffic lights glow; Havana lamp heads lit; Rio; roads dark (C128/C132-C134).
8. Mods > Quality of Life > "Rewind" switches rewind on/off on its own; "Full Pro experience" section with the warning (C130/C131).
9. City menu page 2: Las Vegas and Rio pictures.
10. Your car's shadow fits the car in every Driver 2 city (Havana mini most visible); light glows in Driver 2 sizes (C138).

### Questions about your last session
- 30.10. 16:33 and 16:40 (probe "d2 cities 6"): the game froze twice. What were you doing right before (city, menu, ride)? Infrastructure is analysing the dumps (C140).
1. 28.10. ~17:30-17:45 on the laptop (probe "q73 chicago night"): the game froze 3 times and crashed once (after Newtown, while driving a Driver 2 city, after picking LA day). What were you doing, and how did it look (frozen picture, black screen, sound loop)? Cause found + fixed (C135, two bugs: wrong level table for Newtown/Desert; special car overwriting memory after a city switch), now in probe "d2 cities 6". Anything else you noticed?

### Waiting for details from you
- Havana map fixes: you said you'd send details later (27.10.).

## Answered (latest first)
- 30.10. probe "d2 cities 6" review: Newtown spawns police with missing models -> no police in Newtown (C141); black
  void in loading zones instead of D1's "last frame" (C142); horns per car model as in D2 (C143); wheel sizes of every
  D2 car as in D2, Havana mini + Vegas player car first (C144); Chicago bus lights misplaced (C145); Las Vegas night
  still unlike D2, other nights "really good" (C146). Q74: allowed (rule still has to be added by you, see above).
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
