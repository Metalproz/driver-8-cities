Driver 1 songs, rendered from DRIVER/SOUND/MUSIC.BIN (8 songs), 60 s each, 16-bit stereo 44.1 kHz.
Files: song0_NY.wav, song1_Interview.wav, song2_Newtown.wav, song3_Miami.wav, song4_Miami_night.wav,
song5_SF_Desert.wav, song6_SF_night.wav, song7_LA.wav. xmrender.py = the renderer (XMPlay superpacked XM +
PS1 ADPCM bank, DriverSoundTool conventions; a minimal player: notes, volume, pan, speed/tempo, common effects,
no envelopes). Caveat: this is our own minimal renderer, not a reference player: timbre and timing may differ
from the game. song4 (Miami night) hit a desynchronised pattern and was cut at that pattern (rest silent).
Song index = (mission + 3) & 7 (mission loader 0x800687B8). Use by mission/city (verified mapping):
  song 0: NY (0x7D).           song 1: Interview (0xAE)
  song 2: Newtown / CREDITS cheat (0x7F)              song 3: Miami (0x78)
  song 4: Miami night (0x79)                          song 5: SF (0x7A) and Desert (0xAA)
  song 6: SF night (0x7B)                             song 7: LA (0x7C); Car park (0xAD) plays song 0
"The Briefcase" and "Chase Mission" are not named in the exe. Chase clips were not identified: the table at
0x8008AA04 (xm_coptrackpos) did not show clear per-song positions, so no *_chase.wav was made.
Listen by ear to find the Briefcase (a mission track, not a city track).
Samples: rendered from the VAG bank in MUSIC.BIN (ADPCM decoded), instrument i -> bank sample i.
