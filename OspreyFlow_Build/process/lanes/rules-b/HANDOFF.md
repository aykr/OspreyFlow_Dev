# rules-b handoff, 15 Nov 2026 (paused for the move to sol)

**Step:** P3, the rehearsal of `process/lanes/demo/REBUILD_2026-11-18.md`'s "Before 07:00" step 4 (the
orchestrator's F1). Branch `lane/rules-b-p3-rehearsal`, from main 3d961cc; quote its head from `git rev-parse`.
**Last commit:** this handoff, on 44a649a.
**Done.**
- The sheet's bare `docker run … --stage tiles` would have failed: `_main` opened `/app/osprey.yaml` and Postgres
  before any verb, and the image holds neither. Fixed at 143032e: `_tiles_here` and `builder_state` in
  `services/api/map_admin.py`. The tiles stage reads no settings or audit and checks no unit; the places stage still
  checks the unit.
- Red first: `p3-rehearsal/red-first.txt`. Plants 12 of 12 red, control green: `p3-rehearsal/plants.txt`. 152 tests
  pass across the map suites.
- The script `p3-rehearsal/rehearse.sh` and the latency probe `probe.py` are written. The image tag is
  `ospreyflow-basemap:p3`, never Wednesday's `:v0.6.0` (the orchestrator's word).
**Running:** nothing. No lease and no stack up. rules-b's QUEUE line is second, behind admin's #18 gate.
**Next.**
1. When rules-b is first in `/root/osprey-runs/QUEUE` and `pgrep -x make` is empty: `stack_lease.sh acquire`, then
   `up`.
2. `stack_lease.sh remote rules-b -- bash ../OspreyFlow_Build/process/lanes/rules-b/p3-rehearsal/rehearse.sh`, as a
   background run, from OspreyFlow_Build. About 50 min. It removes the image and the scratch folder itself.
3. Afterwards: bring the stack down, release it, and delete the QUEUE line. Save the log, masked, as
   `p3-rehearsal/rehearse.txt`.
4. Correct the sheet as a diff to the orchestrator; the file is not rules-b's. Give the command that ran; add `--cpus`
   only if p95 latency rose well above the baseline. Note that v0.6.0 needs 143032e and that `<tiles>/built` must be
   writable by uid 10001.
5. Write `p3-rehearsal/RECORD.md`: the time, peak memory, last line, latency and the correction. Then send
   ready-to-merge.
**Open questions:** none. **Do not redo:** #10, merged at b81fe0b, with its measurement in `v060-basemap/RECORD.md`; the bare-stage fix; the
plants.
