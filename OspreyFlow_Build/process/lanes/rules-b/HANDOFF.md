# rules-b: handoff, 15 November 2026 (paused for the move to sol, on the orchestrator's word)

Read this first. It is the only memory carried over from the Mac session.

## State at the pause

- **Branch:** `lane/rules-b-p3-rehearsal`, from main 3d961cc. Its head is 44a649a; quote the head from
  `git rev-parse` before using it. The tree is clean.
- **Lease:** none held. No stack is up for rules-b, and no run of rules-b's is alive on ospreyflow-test.
- **QUEUE:** rules-b's line (P3) is second in `/root/osprey-runs/QUEUE`, behind admin's #18 gate. If admin's gate
  finishes first, the sol session takes the P3 turn (the orchestrator's word).
- **Merged and closed:** v0.6.0 #10, the basemap, at b81fe0b. Its recipe diff is applied to `demo/HANDOFF.md`.
  Before that: am20, route-collapse, and the admin-forms research.

## The open item: P3, the rehearsal of the rebuild sheet's step 4

The sheet is `process/lanes/demo/REBUILD_2026-11-18.md`, section "Before 07:00", steps 1–4 and prerequisite P3. The
ruling is the orchestrator's (F1).

**Found and fixed already (143032e).** The sheet's bare `docker run … map_admin build great-britain --stage tiles`
would have stopped before downloading anything:

- `map_admin._main` opened the maps settings and audit first, which needs `/app/osprey.yaml` and Postgres;
- the build then checked the unit, also in Postgres;
- the image holds no `osprey.yaml`, and a bare container reaches no database.

Now `--stage tiles` runs before the settings are opened (`_tiles_here`). The builder is checked from the tiles
folder alone (`builder_state`), and the places stage still checks the unit. Two tests ran red first
(`p3-rehearsal/red-first.txt`). The plants are 12 of 12 red with the control green (`p3-rehearsal/plants.txt`), and
152 tests pass across the map suites.

**What is left:**

1. **Take the turn.** Read the QUEUE and check `pgrep -x make`. Go only when rules-b is first and make is idle. Then
   run `stack_lease.sh acquire rules-b "<purpose>"` and `stack_lease.sh up rules-b`, on any of b–g.
2. **Run** `stack_lease.sh remote rules-b -- bash ../OspreyFlow_Build/process/lanes/rules-b/p3-rehearsal/rehearse.sh`
   from OspreyFlow_Build, as a background run (never `&`). Expect about 50 min. The script:
   - builds the image from the run copy's OspreyFlow_Core, tagged **`ospreyflow-basemap:p3`**. That is the
     orchestrator's word: never Wednesday's `ospreyflow-basemap:v0.6.0`. The script refuses to run if the tag
     already exists.
   - places planetiler v0.10.2's jar in a scratch tiles folder and checks it against sha256
     `f310bd0413e2e4512b27f4046d418664e8e1d3bf31603c2a70e23de06c167e4d`. `built/` is chowned to 10001.
   - starts `probe.py`, which times one ArcadeDB SQL call and one Postgres `SELECT 1` on the leased stack every
     10 s: 60 s of baseline, then throughout the run.
   - runs the sheet's step 4 as written, with `--memory 4g`, the tiles folder read-only and `built/` writable, as
     the image's uid 10001. The unit is `unit-1` and `--by cli:rules-b`.
   - prints the exit, wall time, the container's peak memory, the last line (expected: `Built great-britain.pmtiles
     and saved its settlements; run --stage places to load them.`), p50, p95 and max latency for baseline against
     the run, and what was written.
   - removes the image and the scratch folder at the end.
3. **Afterwards.** Bring the stack down, release it, and delete rules-b's QUEUE line. Save the log, secrets masked,
   as `p3-rehearsal/rehearse.txt`.
4. **The sheet's correction**, as a diff to the orchestrator; `demo/REBUILD_2026-11-18.md` is not rules-b's file.
   The command is corrected to what ran. Add `--cpus N` only if the run's p95 latency rose well above the baseline,
   and say which. Note the following:
   - (A) needs the merged fix, so v0.6.0 must contain 143032e;
   - the real run uses `ospreyflow-basemap:v0.6.0`, built from v0.6.0, while the rehearsal used `:p3`, built from
     this branch;
   - the time and peak memory measured;
   - that `<tiles>/built` must be writable by uid 10001.
5. **Write `p3-rehearsal/RECORD.md`** with the image, the time, the memory, the last line, latency with and without
   the run, and the correction. Then send the orchestrator **ready-to-merge for this branch** (143032e and the
   sheet's correction), with the head from `git rev-parse`.

## Figures already measured (#10, stack b, 15 Nov; `v060-basemap/RECORD.md`)

- **Download:** 11 min.
- **planetiler** at `-Xmx2g`: 7 min 18 s, container peak 3.0 GB, all 16 cores.
- **Reading the settlements:** 14 min. They are 56,486 of 1,059,567 named points.
- **The places stage's writing:** about 23 min.
- **Disk:** pmtiles 1.5 GB, planetiler's sources 1.4 GB, extract 2.1 GB.

## Standing rules carried (the memory index has more)

- osprey-small, the owner's demo, is never touched.
- Never `make dev-up`, and never start Docker on the Mac.
- Never open a desktop app.
- Never push or merge, and add no Co-Authored-By lines.
- Never stage `OspreyFlow_Core/osprey.yaml` or `OspreyFlow_Core/data/`.
- Offline pytest runs on ports 59991–59994 with `OSPREY_LANE` unset and a fresh `PYTHONPYCACHEPREFIX`.
- Server runs go through `stack_lease.sh remote` or `offline`, one at a time, as background runs.
- Beat the heartbeat every 30 min while working, and record stages with `lanes_heartbeat.sh stages`.
