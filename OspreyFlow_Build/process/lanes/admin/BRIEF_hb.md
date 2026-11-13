# Admin lane · brief hb · the heartbeat's stage view for every lane, and the default view reorganised (M)

Written by the orchestrator, 13 November 2026, at the owner's word: "build this view into the heartbeat for all the
lanes and refresh the current organisation of heartbeats". "This view" is the stage table the orchestrator gave the
owner for R1: each stage of a lane's current step, numbered, with ✅ done, ⏳ now, — not yet, and a one-line status.
Branch `lane/admin-hb` from main. **Offline only** (R1 holds the server). Opus, medium.

## Files

`OspreyFlow_Build/scripts/lanes_heartbeat.sh` and `OspreyFlow_Build/tests/test_lanes_heartbeat.py` (and, if a
lane's own instructions need it, the launcher's prompt text in `OspreyFlow_Build/scripts/lanes_launch.sh` as one added line; nothing
else of the launcher).

## 1 · A lane says its stages: a new verb

`lanes_heartbeat.sh stages <lane> "<step>" "<n>|<state>|<name>[|<note>]" ...`

- Writes `$DIR/<lane>.stages` whole (atomically, as `beat` writes its file): the step, the time, one line per stage.
- `<state>` is `done`, `now`, `todo` or `blocked`; anything else is refused in words, as `beat` refuses a bad state.
- A second call replaces the list (a lane re-states its stages when they change; there is no partial update).
- `lanes_heartbeat.sh stages <lane> --clear` removes it (a step finished).
- A lane's stages are shown only while its beat names the same step (or its current step in progress.tsv), so a
  stale list from a finished step never shows.

## 2 · The default view, reorganised (one screen first, detail after)

In this order:

1. The header line and OVERALL (as now).
2. **NEEDS YOU**, at the top, from the same reading `show` already makes (owner-named waits, blocks, usage
   limits), or "Nothing needs you." Today it is only in `show`/`summary`.
3. **PATH TO <release>** (finish.tsv, as built on 13 Nov), unchanged.
4. **LANES NOW**: one block per lane that is not paused or idle: `LANE · step · state · last heard Nm ago`, then its
   stages as a numbered list, each `✅`/`⏳`/`—`/`⛔` + name + note, and the count "stage 3 of 10". A lane with no
   stages shows its beat's note in one line. Paused and idle lanes are one line at the end: "Idle: …; paused: …".
5. **VIEW 1 · FOUNDATION FEATURES** and **VIEW 2 · DEPLOYMENT** collapsed to one line per group (`Ingest Studio:
   11 of 11 done`), the group's open steps listed only when it has any. `--full` (new on the default view) keeps
   today's full blocks.
6. **RELEASE**: last, published, next, and the merge count since the cut on one line ("98 merges since 4b8de6c");
   the full merge list only under `--full`.
7. HOUSEKEEPING and the LANES table as now.

Target: the default view at or under ~60 lines on today's data (it is 133); record before and after.

## Tests (rules 12, 13, 15; red first, each recorded)

- `stages` writes, replaces, clears; a bad state is refused and nothing written; the file is written whole.
- LANES NOW shows a lane's stages with the right marks and "stage n of m"; a stale stages file (another step) is not
  shown; a paused or idle lane is in the one-line tail, not a block.
- NEEDS YOU in the default view: an owner-named wait appears there; a wait on the orchestrator does not.
- The collapsed views: a group with every step done is one line; a group with an open step lists it; `--full`
  restores today's blocks (today's order test still passes under `--full`).
- RELEASE's one-line merge count; the list only under `--full`.
- The existing 39 tests stay green (adapt only those that test the old default layout, and say which).
- Each new behaviour shown red with the code planted out, in the shape the real call produces.

## Then

Ready-to-merge to the orchestrator with the default view's before/after line counts and a sample of the new view
(from the test fixture, never real secrets). The orchestrator then tells every lane to send its stages.

**Never.** No server, no lease, no push. Nothing outside the files above.
