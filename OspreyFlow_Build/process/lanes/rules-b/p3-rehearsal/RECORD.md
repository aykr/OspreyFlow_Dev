# rules-b P3 · the rebuild sheet's step 4 rehearsed (15 November 2026)

The orchestrator's F1: rehearse `process/lanes/demo/REBUILD_2026-11-18.md`'s "Before 07:00" step 4, the bare
`docker run … map_admin build great-britain --stage tiles` from the Conduit's image, beside a running stack.
**The bare run ran and passed.** Docs' override approach (lane/docs-v060-sheet-fix 03c18b2) was not needed and was
not rehearsed (the orchestrator: only if the bare run failed).

## What ran
- **Where:** on ospreyflow-test, under the QUEUE (rules-b first, `pgrep -x make` empty), beside stack b, which
  rules-b leased at 13:52:17Z and released after the run. Nothing of osprey-small was named or touched.
- **The code:** branch head 282aee2 (rebased on main 1d17dfe). The run copy's commit b5db38f has the same
  `map_admin.py` and `Dockerfile` blobs as 282aee2 (e2db793…, 5c4a835…).
- **The image:** `ospreyflow-basemap:p3` (never Wednesday's `:v0.6.0`), sha256:29f83d44…, 1.95 GB, built in 92 s.
  The script removed it.
- **The command:** the sheet's own, with three differences:
  - the tag;
  - the container named `rulesb-p3-basemap-tiles` and labelled for the reaper;
  - `--unit unit-1 --by cli:rules-b` standing in for the placeholders.
- **Logs:** `rehearse.sh` wrote `rehearse.txt` (raw, with only a GitHub release URL's signed query masked).

## Figures
| | |
| --- | --- |
| Time | 13:52:40Z to 14:35:53Z, exit 0. Step 4: 2,192 s (36.5 min): download about 12 min, planetiler 7 min 37 s (cpu 1 h 16 min), settlements about 16 min |
| Last line | `Built great-britain.pmtiles and saved its settlements; run --stage places to load them.` (56,486 settlements) |
| Memory | cgroup `memory.peak` 4,099 MB, the 4 GiB cap; `memory.swap.peak` 2,990 MB; `docker stats` sampled peak 3,964 MB. `memory.peak` counts page cache, and the stage writes 3.7 GB. It finished regardless |
| Latency beside it (ms) | ArcadeDB p50/p95/max: baseline 6.0 / 6.6 / 6.9 (n 59), during 5.6 / 8.3 / 41.7 (n 437). Postgres: 10.9 / 12.5 / 12.9, then 11.3 / 14.1 / 23.2 |
| Disk | about 5 GB: `extracts/` 2.1 GB, `great-britain.pmtiles` 1.5 GB, `sources/` 1.4 GB. 423 GB free before, 415 GB after |

## The correction (`sheet-step4.patch`, for the orchestrator; the sheet is not rules-b's)
- **The command is final as written.** No `--cpus`: p95 latency rose by under 2 ms.
- **v0.6.0 must contain 51f2581.** Without it, the bare run fails at once, looking for `/app/osprey.yaml` and
  Postgres.
- **`<tiles>/built` must be writable by uid 10001.** Run `chown -R 10001:10001 <tiles>/built` first.
- **`--unit` is required but not checked here.** The places stage checks it, in the window.
- **Check before step 4 whether the demo's map already serves `osm-local-great-britain`.** If it does, the stage
  overwrites the file that provider serves, because planetiler runs with `--force`. The sheet's "the running demo's
  map is unchanged" holds only if it does not (the review's item 11).
- **`--memory 6g` on the sheet** (the orchestrator, 15 November): at the measured 4g the stage reached the cap and
  swapped 3 GB. The demo server has 53 GiB free, and a higher cap only loosens the measured run. The figures above stay
  those of the 4g run.

## The lane review and what it changed
A lane-reviewer read the branch before the run and found 12 items.
- **Fixed before the run:**
  - 7883a82 (the review's 2, 5, 6 and 7): `_main` tests that `--stage places` and a whole build still check the unit,
    and the bare tiles stage end to end and its refusal. One `basemap()` read. `--unit`'s help says the tiles stage
    checks none.
  - 45fb26a: four plants, 4 of 4 red, control green (`review-plants.txt`).
  - 282aee2 (the review's 1, 3, 9 and 10): the script's trap cleanup, the reaper label, its own container name,
    a 5-minute baseline with the warm-up sample dropped, the cgroup peak, the probe's database dropped, and the
    commit, image and disk recorded.
- **Left, recorded:**
  - 4, the gates: queued by the orchestrator.
  - 8, ownership: `map_admin.py` is Platform's. The change follows from rules-b's #10 and F1, and the friction row
    records it.
  - 11: the sheet's caveat above.

## Decisions taken (Prompt L)
- **The rehearsal's container was named apart from the sheet's.** A leftover could then never block Wednesday's run
  by its name. The cleanup removes it on every exit path anyway.
- **`--memory 4g` proposed at first, as the measured form; the orchestrator overruled it to 6g** (above).
- **The places stage was not rehearsed.** It loads into a unit and registers a provider, so it belongs in the
  window. Its behaviour is the merged #10's, measured in `v060-basemap/RECORD.md`.
