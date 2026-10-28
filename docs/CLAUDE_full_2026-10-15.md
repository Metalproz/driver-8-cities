# D:\recomps — Driver 1 recomp + Driver 2 city ports (personal, local only)

Quiver library; the project lives in `Apps/Driver-DriverRecompiled/` ("the app").
Goal: one Driver 1 copy with all 8 cities. Milestone 1 = Driver 2's Chicago in LA's slot.

## Read first (in this order, nothing else up front)
1. `app/driver_personal/ROADMAP.md` — status, open issues C1–C15, backlog, open questions.
2. `app/driver_personal/chicago/NOTES.md` — technical record: workflow commands, formats,
   engine addresses, patches, resolved bugs with causes, ruled-out list. **Check the ruled-out
   list before proposing an experiment.**
3. `app/driver_personal/README.md` only when installing/re-applying after an update.
Memory notes in `~/.claude/projects/d--recomps/memory/` hold the user's decisions.

## Hard rules
- Never kill `Driver_Recompiled.exe` by image name (the user may be playing). Kill test
  instances by PID only. A guard hook blocks `taskkill /IM` etc.
- `build-release` is frozen: never write into it unless the user declares a release.
- `build-dev` is the user's dev client: rebuild or copy into it only when no exe from
  `build-dev` is running; never put CHI_START test packages or test state into it.
- Tests run on copies under `app/devtest/` (`dt.py`, `lab.py`) with their own memcards and
  ports (4380+/4390+/4400+). Never touch the user's saves (`app/saves`, build-dev memcards).
- Inputs in `chicago/work/d1_*.lev`, `d2_CHICAGO.*` come from the user's discs: never delete.
- Decisions already made (see memory + NOTES header) are not re-litigated; ask before changing.

## Token discipline (the main work chat hit 73 MB of tool output; don't repeat that)
- Heavy commands (converter, package build, exports, soaks, probes) go through
  `python app/driver_personal/chicago/devtools/run.py -- <cmd>`: full log on disk, capped output.
- Never `cat`/`Read` dumps, `.json` freeze dumps, `.lev`, OBJ or logs directly. Write a short
  Python script that prints a compact summary; read at most one contact sheet image per step.
- Investigations with several game runs or large outputs: delegate to the `chi-investigator`
  subagent (its context is discarded, only the report returns). Offline format/LEV analysis:
  `lev-analyst` subagent.
- One chat = one issue or one feature. Finish with `/chi-wrapup` (NOTES, ROADMAP, spots).
- Skills: `/chi-status`, `/chi-build`, `/chi-spot NAME`, `/chi-levcheck`, `/chi-wrapup`.

## Tools (all local; details in NOTES.md "Workflow")
| tool | use |
|---|---|
| `chicago/convert.py`, `build_package.py`, `exe_patches.py` | converter → package → exe patches |
| `chicago/devtools/dt.py` | snaps / live / spots / soak / addspot / dis on devtest copies |
| `chicago/devtools/lab.py` | continuous 6-slot lab: job queue, converter variants, regression captures |
| `chicago/devtools/run.py` | quiet runner (log to file, capped output) |
| `chicago/devtools/levcheck.py` | independent parse + OBJ/texture export of a LEV via DriverLevelTool, with stats |
| `D:/recomps/refs/OpenDriver2Tools-bin/*` | DriverLevelTool (D1/D2 LEV viewer, OBJ/TGA/overmap export, D1 road overlay), DriverImageTool (D1 PSX sky, D2 sky/frontend), DriverSoundTool (D2 MUSIC.BIN → XM, BLK → WAV) |
| `D:/recomps/refs/OpenDriver2Tools/` | source: `DriverLevelTool/driver_routines/regions_d1.cpp`, `d2_types.h` = second source of truth for D1 lumps (ROADS 16 B, JUNCTIONS 44 B, ROADBOUNDS 20 B, road map cell packing) |
| `D:/recomps/refs/REDRIVER2/src_rebuild/Game/C/` | Driver 2 decompiled: `dr2roads.c`, `cell.c`, `spool.c`, `draw.c`, `civ_ai.c`, `cop_ai.c`, `overmap.c` |
| `app/psxrecomp/tools/gpu_frame_*.py` + `docs/GPU_FRAME_TOOLS.md` | which guest function drew which primitive (per-function layers, frame diff) |
| `D:/recomps/tools/ghq.py xrefs ADDR` / `decomp ADDR` | **static code map** (Ghidra 12.1.4 + PSX loader, read-only, ~5 s): who reads/writes an address, decompiled function. Use BEFORE runtime traces (README in D:/recomps/tools) |
| `app/driver_personal/driver_dbg.py`, `psxrecomp/TCP_COMMANDS.md` | debug server client / command list |

## Chats and step gating (user's rule, 2026-10-11)
- **Planning chat = the root of strategy and workflow** (SendMessage address: `Strategy` if renamed, else `recomps-1c`, ref [85c39e] since 2026-10-15 (before: recomps-27 [fab41b]);
  chats can be renamed: if ListAgents shows no such name, look for ref [fab41b] or ask the user). It owns ROADMAP.md's strategy sections
  (Next steps, milestones, backlog, open questions) and hands out steps. It has a per-prompt
  checkup hook that reads WORKLOG.md, so it sees every log line without being messaged.
- Worker chat: takes exactly one roadmap step or issue (C-number), runs its build/test/evaluate
  loop autonomously via lab/subagents until done, reports, and **stops**. The step then waits
  for the user to test it in build-dev; the next step starts only when the user prompts for it.
- Engine chats: exe patches, runtime, converter structure — same gating.
- **Live test chat** ("Live test" / recomps-f7): plays and tests together with the user in build-dev
  (triage of user snapshots, reproducing, verifying fixes, small dev tools). It hands findings to the
  worker chat that owns the issue (via WORKLOG + SendMessage) and does not take on big fix steps itself.

- **Team (user, 2026-10-12):**
  - **Strategy** (planning chat): discusses the work with the user, assigns issues, keeps ROADMAP/WORKLOG. Nothing
    starts without the user's go given there.
  - **Roadmap** (chat the user created 2026-10-12): the ONLY channel for anything that needs the user's input.
    Strategy sends approvals, decisions, verdict requests and open topics needing feedback there (numbered,
    short, with a recommendation); the Roadmap chat shows them to the user and relays the answers back to Strategy.
    Don't ask the user for decisions inside other chats.
  - **Infrastructure** (formerly "Water"): the only chat that changes code/data (converter, plugin, exe patches,
    runtime) and fixes issues, on assignment from Strategy; tests its own fixes; ships to build-dev on the user's go.
  - **Height**: closed (2026-10-12); its open items (C33 hook + ramp round 2 awaiting the user's test, C16/C17
    touch-ups, C20) belong to Infrastructure.
  - **Live test**: plays and tests with the user (snapshots, verdicts), no big fixes.
  - **QA-1, QA-2, QA-3** (Haiku; since 2026-10-12 17:00 background subagents of Strategy, restarted by it after a pause; handoffs in devtest/qa_handoff/): background QA testers like at a game studio. Each works on ONE issue at a time,
    assigned by Strategy, and tests freely on it (exception to the test budget) with **one own game instance**:
    test copy `devtest/qaN`, debug port (QA-1 4410, plus regionsweep.py's own `sweep` copy on 4430 while sweeping; QA-2 4420; QA-3 4440). They research and test, never
    change code, data, build-dev or shared files (only their own devtest/qaN, spots via `dt.py addspot`, their
    findings in WORKLOG). They report ONLY to Strategy: findings useful for a fix (reproduction, cause candidates,
    evidence), not progress. When done or stuck: report, then take the top free item of the **QA queue** in
    ROADMAP.md (mark it `[QA-n]`), so they work continuously (user, 2026-10-12: Strategy assigns QA work on its
    own; fixes and build-dev ships still need the user's go).

  - **EXP** (Haiku background subagent of Strategy, user 2026-10-12): experiments with potential solutions for open
    roadmap questions, aligned with the goal (authentic Driver 2 cities in Driver 1, engine unchanged unless
    unavoidable). Works only with Strategy. Experiments only in private copies: its own scratchpad copy of the
    converter, output `work/var_exp_*.lev`, test copy `devtest/exp`, port 4450. Never changes shared files, the plugin,
    exe patches or build-dev; results go via Strategy to Infrastructure.
    **When idle: bug hunt** (user 2026-10-12): Strategy gives EXP an open-ended task to explore Chicago gameplay for
    bugs/issues (findings with spot, repro, severity → Strategy). Strategy's own experiment needs take priority and
    pause the bug hunt until done.
  - **Polish** (Opus background subagent of Strategy, user 2026-10-13): owns the lower-priority issues and changes that
    need no engine work (C32, C31, C2/C7, C10, C12, C11, C1, C21, C23, C13/C24, C30, west map edge). Converter changes only
    behind CHI_POLISH_* switches (default off), own variant levels `work/var_polish_*.lev`, test copy `devtest/polish`,
    port 4470; never exe patches/plugin/runtime/build-dev. Asks Strategy for idle Haiku testers; Strategy has
    Infrastructure adopt verified switches as defaults. No new subagents while existing ones are idle (user rule).
  - **FAN** (Haiku background subagent of Strategy, user 2026-10-13): plays constantly like a Driver 1/Driver 2 fan and reports
    VERY OBVIOUS visual glitches/gameplay annoyances that are NOT in the PS1 originals (integrity of both games; authentic D1/D2
    behaviour is not a bug). Any test build except build-dev/the frozen release; own copy `devtest/fan`, port 4480; never changes
    code/data/shared files. Works in rounds, reports only to Strategy; Strategy weighs findings into the roadmap without
    disrupting its plan; big changes still go to the user via Roadmap. **Repeats escalate** (user 2026-10-13): FAN keeps a
    ledger (devtest/fan/findings.json, times seen per issue); an issue reported again rises in severity, and Strategy raises its priority.
  - **Design** (since 2026-10-15 a Sonnet 5.5 background SUBAGENT of Strategy; the earlier Fable 5.1 Design chat is retired, user rule): the ARTISTIC side only: design choices and creation,
    mostly sprites and graphics (skies, car looks/textures, menu preview sprites, minimap look, texture quality/fidelity to D2).
    All design requests and changes go to Design (user rule). Bugs and mistakes go to other chats/agents (Infrastructure, Polish,
    QA/FAN). Strategy gives Design tasks and suggestions; Design follows them. Own devtest copy and port (4490).
  - **Debug ports (fixed):** build-dev 4370 (user), spotplay 4377, lab slots 4400+, QA-1 4410, QA-2 4420, region sweep 4430,
    QA-3 4440, EXP 4450 + 4460, **Infrastructure 4461–4469**, Polish 4470, FAN 4480, Design 4490. Before launching, check the port is free (and that the listener's
    PID is your own game).

- **Testing rules (user, 2026-10-11, apply after the 18:4x combined ship):**
  - **No background stress tests:** the lab (`lab.py run`), soak series and idle rotations stay OFF until the
    user explicitly asks for them again. Exception: QA-1/2/3 test freely on their one assigned issue (1 instance each).
  - **Launch test copies only via `dt.launch`** (2026-10-14, C47): it starts them at BELOW_NORMAL priority so they never
    compete with the user's game (headless copies run uncapped); no direct Popen of Driver_Recompiled.exe in tester scripts.
  - **One test run per issue** (main gameplay only: driving, collision, falling through, drowning/restart,
    freezes) at the spot the change touches. OK → move on; failed → fix, then one run again. No hour-long tests.
  - **The user tests and judges:** after that one sanity run, hand the change to the user quickly, e.g. a spot
    launcher probe (`Driver (spot).bat` / `spotplay.py SPOT --lev LEVEL`), so they can try more probes and give
    their opinion. Prefer several small probes for the user over long automated verification.

- **Playable copy for the laptop (user, 2026-10-12):** after every build-dev update (on the user's go), the
  copy is updated (the Windows task "Driver playable publish" is DISABLED by the user since 2026-10-15; Strategy runs
  `publish_playable.py` by hand after a build-dev ship instead). Old behaviour: `publish_playable.py --if-changed`
  every 10 min (only when build-dev or spots.json changed and is stable for 2 min; logs a WORKLOG line). It mirrors build-dev (dev mode, logs,
  snapshots, overlay) to `<OneDrive Desktop>/Driver Chicago (playable)` with "Play Driver.bat" and "Play at spot.bat";
  OneDrive syncs it to the user's laptop. Snapshots/logs from there come back in its `dev/` folder (the planning
  chat's checkup shows them). Never write saves there; the copy must not be running while publishing.
- **Probes (user, 2026-10-12):** `app/driver_personal/probes.json` lists the CURRENT probes (name → test level,
  optional `build` = exe folder, default build-dev). Strategy keeps it up to date and runs
  `python app/driver_personal/probes.py sync`: every probe becomes a self-contained copy in
  `<OneDrive Desktop>/Driver Probe Tests/NAME` (its own exe, frozen at sync time, so test builds reach the laptop too;
  own saves; shared disc in `_disc`; "Play probe.bat" / "Play probe at spot.bat"); outdated probe folders are removed.
  Probes never go into build-dev or the "Driver Chicago (playable)" copy (that one is the dev client only).
  Snapshots from a probe land in its own `dev/dumps` (the planning chat's checkup shows them).
- **Lean disk (user, 2026-10-12):** delete what's no longer needed (finished probe folders, superseded `work/var_*.lev`,
  idle devtest copies, lab results, old outputs) so the disk and OneDrive stay lean. Each chat cleans up its own
  outputs when a step is done. Never delete inputs (`d1_*`, `d2_*`), the shipped level + its backup, running copies,
  or the user's snapshots/saves without asking.

- **Fun-fact findings (user, 2026-10-13):** curiosities about D1/D2 with little or no information online (unused levels,
  hidden content, leftovers) are noted in `app/driver_personal/FINDINGS.md` (evidence + files, images in `findings/`), not as
  roadmap work unless they matter for core gameplay. Any chat or subagent may add an entry.

- **PS1 hardware goal (user, 2026-10-13, Milestone 8):** the game must eventually run on a real PlayStation. New engine features
  should have a PS1-native path (guest MIPS code/data within PS1 RAM/VRAM/CD limits); note host-only dependencies in NOTES.

### Reporting protocol (every chat except the planning chat)
1. **Log** in `app/driver_personal/WORKLOG.md`: append one line per meaningful event (no
   per-experiment noise): `YYYY-MM-DD HH:MM | <chat name> | <C#/step> | what happened | key files`.
   Log: step/issue started, a cause found, a fix landed, a default changed (converter output,
   exe patch, runtime), build-dev updated, a regression found, step done/blocked.
   Details stay in NOTES.md (technical) and the issue's C-row (status).
2. **Message the planning chat** (SendMessage, ≤ 8 lines, first line says what it is) only for
   major events:
   - step/issue done → "awaiting user test";
   - blocked, or a decision that belongs to the user;
   - build-dev updated (what the user should test);
   - a new engine patch or runtime change, or changed shared defaults in convert.py/exe_patches.py;
   - a regression, or a new issue not yet in ROADMAP.md;
   - you want a change to the plan (Next steps/backlog): propose it, don't edit those sections.
   Not for progress updates: those go to WORKLOG.md only.
3. **ROADMAP.md**: workers may update their own C-row status, add new issues as C-rows, and add
   done-log entries; strategy sections are edited by the planning chat only.
4. **Shared files**: before changing defaults in convert.py / exe_patches.py, rebuilding
   `work/chicago_d1.lev` or installing into build-dev, check WORKLOG.md for another chat working on
   the same files and coordinate with it directly (SendMessage), using experiment switches meanwhile.
