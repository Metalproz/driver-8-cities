# Chicago day colour grade (Design, 2026-10-14)

Goal: Chicago by day a touch cooler/greyer, like Driver 2's overcast Chicago. Mockups: `out/grade_mockup.png`
(three b16b day shots: downtown, street, overpass; left = today, middle = grade A, right = grade B).

## What actually differs from Driver 2 (measured)
- The textures are Driver 2's own, so the buildings and roads are already the right colours. The difference is
  **Driver 1's distance haze**: everything far fades toward Miami's near-white fog (`0xefefef`), which Chicago day
  inherits through the plugin's "day words" (CITY 3 compares -> Miami's path). D2 has no white haze by day; its
  far buildings keep their tone and meet the grey-blue skyline band.
- Driver 2's day panorama (SKY0.RAW): sky top (156,180,214), above the skyline (207,221,234), horizon haze between
  the towers (145,149,152). Today's Chicago sky in game reads (238,242,247) near the top band and the far buildings
  wash out to ~(230,230,230): too bright and too neutral next to D2's values.
- Per-city colour words in Driver 1: function 0x800298BC sets two words by CITY: **0x80097138 (fog / fade colour,
  bytes r,g,b)** and **0x80097150 (second plane colour)**: Miami/default `ef ef ef` + `df c0 5f` (sand), SF `bc b4 b0`
  + `ba a6 6f`, NY `7e 77 74` + `78 63 29`, LA (the compare with 0x80097898) `48 45 45` + `43 32 00`, Train `89 73 65` +
  `69 3a 30`. 0x800270D4 copies both into the scratchpad colours 0x1F8001F4/F8 (poly colour words 0x28xxxxxx) each
  frame, scaled by the brightness byte 0x80097128 at night/rain. The exe has **no GTE far-colour writes** (no ctc2 to
  RFC/GFC/BFC): the depth fade is done in software, so the fade colour must come from these words or a table built
  from them at level init. Live pokes of both words after the level had loaded changed nothing in the chase-cam views
  (devtest/design, 20:4x), so the value is consumed at level init (or by the far ground planes only): set it **before
  level init**, where the plugin already writes the day words.

## Proposal (two candidates; A recommended)
| | fog word 0x80097138 (r,g,b) | what it does | mockup |
|---|---|---|---|
| today | (239,239,239) `0x00EFEFEF` | Miami's white haze | left column |
| **grade A** | (204,212,222) `0x00DED4CC` | far buildings fade into D2's haze colour above the skyline: cooler, calmer, still bright; matches the sky band so the dome and the city meet without a white seam | middle column |
| grade B | (184,194,206) `0x00CEC2B8` | heavier overcast; the far city sits in a grey-blue murk, closer to D2's night-less "cold" Chicago but darker than D2's day sky, risk of a dull picture | right column |
- Second word 0x80097150: keep Miami's sand (it is a ground/plane colour; the lake looks right today). If it turns
  out to be the horizon fill behind the dome, use (156,180,214) `0x00D6B49C` (D2 sky top).
- Global saturation: no texture retouch. The mockups add ~15 % desaturation on top of the fog shift to show the
  "overcast" target; if the implementer wants that in-engine, the only cheap lever is the ambient word (0x8003A6B4
  site, 0x282828 by night) which is not a saturation control: skip it. The fog colour alone gets 80 % of the look.
- Night: unchanged (b16b night uses LA's night words; the D2 night panorama already reads overcast).
- Rain variant (sky 15): use grade B's word, rain in D2 is the greyest Chicago.

## Switch for Polish / Infrastructure
`CHI_DAY_FOG=r,g,b` (default off = Miami's); the plugin writes 0x80097138 (and 0x80097150 if given as
`CHI_DAY_PLANE`) while Chicago day is chosen, before level init (same place as the day words / sky number), restoring
Miami's on leave. Verify with one shot at the downtown spawn: the far skyline band should no longer be whiter than
the sky panorama above it.

## Judging it (user)
Downtown spawn, look along the long avenue: today the far end is white; with A it is the same grey-blue as the sky
band. If it looks "foggy" rather than "overcast", back off toward (216,222,230).
