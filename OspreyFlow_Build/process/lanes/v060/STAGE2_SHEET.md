# v0.6.0 stage 2 · the run sheet: search measured again at client size (M1, M3–M6, M9, M10)

Written by rules-b, 15 November 2026, at the orchestrator's request (moved from rules). It reruns step 4's measures
(ADR-149 Amendment 2; `process/lanes/platform/v052-measure/RESULTS.md`, the 14 November figures) on main once the
v0.6.0 list is merged. Every command below was run short on stack d before it was written down
(`v060/stage2/REHEARSAL.md`): the rehearsal proves the commands run, and **its figures are not measurements.**

## Before
- **When:** after Build closes and the v0.6.0 list is merged. The official run is one QUEUE turn of about 25 min,
  plus about 20 min if diagnosis is needed. The orchestrator adds the line; take the turn only when it is first and
  `pgrep -x make` is empty.
- **Rule 14:** one lane holds stack d for the whole run. A figure taken without the lease, or under someone else's,
  is not a measurement.
- **What d holds:** B's client-size load, 570,565 nodes, with M6's earlier draws. The containers are stopped, not
  removed, so `up` restores the load as it was.
- **M6 adds to it:** each official M6 draws 55 nodes (50 after 5 warm-ups) into the intel case's analyst layer.
  The rehearsal drew 8.
- **The code measured is the run copy:** your worktree's head, rebased on the merged main. Note its commit before
  you start; the run copy's own commit is a snapshot of it.

## The commands
Run each from the worktree root, one at a time, never two together; never call `remote` while a run of yours is
alive. `<lane>` is the lane holding the lease. Each step writes `~/osprey-load/stage2/<step>/` on d's host and
refuses to write over an existing folder. If the step was run before, move the old folder aside first.

| # | Command | Takes | Passes when |
| --- | --- | --- | --- |
| 0 | `OspreyFlow_Build/scripts/stack_lease.sh acquire <lane> "v0.6.0 stage 2" d`, then `… up <lane>` | 1 min | the lease is on d and its six containers are up |
| 1 | `OspreyFlow_Build/scripts/stack_lease.sh remote <lane> -- bash OspreyFlow_Build/process/lanes/v060/stage2/run.sh inputs` | 10 s | the three hashes are step 4's: `queries.jsonl` f564f75f…, `leaks.jsonl` ae02aa9c…, `never_join.jsonl` 48af1d50…, with 500 lines each in the M10 files |
| 2 | `… run.sh budgets` | 4 min | **M1** p95 ≤ 300 ms and none over 2 s; **M3** p95 ≤ 1 s; **M4** p95 ≤ 1.5 s; **M5** p95 ≤ 1 s; **M6** p95 ≤ 5 s. Between the budget and the failure figure (M3 2 s, M4 3 s, M5 2 s, M6 30 s), a measure is *over budget*, not failed; past the failure figure, the pytest case fails |
| 3 | `… run.sh m9` | 2 min | M9 met: every answer arrives in under 5 s with OpenSearch stopped, and the bar says so. Afterwards `osprey-test-d-opensearch` is up again (the step prints its status) |
| 4 | `… run.sh leaks` | 4 min | M10 met: 500 of 500 controls reached, 0 failures, 0 indeterminate, the words check measured |
| 5 | `… run.sh never-join` | 3 min | M10 met: at least 450 of 500 controls reached (the 90% floor, the orchestrator's ruling), 0 failures. **It met the floor exactly on 14 November (450).** One more unreached control makes it *unmeasured*, not failed: the pytest case fails on "unmeasured", and the record says so. Never trim the file to pass. The rehearsal's first 20 cases reached 17 (below) |
| 6 | `… run.sh control` | 1 min | `positive control: the words check fired on 5 of 5` |
| 7 | `… run.sh table` | 10 s | the table prints every measure; M2, M7, M8 and M11 say "not measured here" |
| 8 | `OspreyFlow_Build/scripts/stack_lease.sh down <lane>`, then `… release <lane>`; delete your QUEUE line | 1 min | `status` shows d free |

**Only if a figure is over budget or failed:** `… run.sh profile` before step 8 (read-only, about 20 min: the
pre-Amendment-21 variants each read the whole store, 5 to 20 s a time).
`profile_page.py` shows where a search page's time goes. `profile_m9.py` times M9's graph fallback as built (`shipping`) beside the
query before Amendment 21 and its variants. It ran only after rules-b's fix, 4b98887; on main before that it
raised `TypeError`. **Only if `scripts/client_size_leaks.py` has changed since 14 November:** `… run.sh regen` (3 min)
before step 4. It writes `stage2/m10-regen/`. Read its counts (`leaks_words.measured` must be true), then replace
`~/osprey-load/m10/*.jsonl` by hand, keeping the old files beside them. Steps 4 and 5 then measure the new hashes,
which go into the record.

## Where the record goes
`process/lanes/v060/stage2/RESULTS.md` holds the table from step 7, with each step's run id (`remote`'s
`logged at …/runs/<id>/log`), the lease and its time, the branch head measured, and the comparison with the
14 November figures (RESULTS.md's "The shipping code's figures"). Keep the raw logs beside it as
`stage2/<step>.txt`. The results folders stay on d's host under `~/osprey-load/stage2/`.

## What changed since step 4, and why the runners still fit
- **The search path itself is unchanged.** Between step 4's tree (main 10ff9e2) and main 33a7c9f, no server-side
  search file changed: not `services/search_index`, not `services/api/search.py`, not `schemas/search.py`, and not
  app.py's search, suggest or board routes.
- **#3, #4 and #5 changed search in the Glass.** #5's `add-by-ids` is a new route. It refactors `seed`'s reading
  (`WorkingSetService._seed_ids`), which no runner calls.
- **The runners' routes are the same:** `suggest`, `search`, `boards`, `boards/{id}/items` and
  `GET /v1/investigations/{id}`.
- **The runners' own tests pass offline on main:** `test_step4_stack.py`, `test_measure_search.py`,
  `test_client_size_leaks.py`, `test_step4_dry_run.py` and `test_search_nodes_from_candidates.py`, 109 passed. The
  live gate and the docker-CLI M9 case skip, as they should.
- **One runner was broken, and is fixed:** `profile_m9.py` still built the fallback's query as it was before
  ADR-124 Amendment 21 and raised `TypeError` on main. It is fixed at 4b98887, with `tests/test_profile_m9.py` red
  first (`stage2/profile_m9-red-first.txt`). The measures themselves were not affected.
