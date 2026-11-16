# v0.6.0 stage 4 · the package test on candidate `ea5fc61` · the record

Run by platform-b on 16 November 2026, 10:09–11:08Z, on R1's kind cluster on the test server (stack b's lease, taken
by the owner), from a copy of `ea5fc61` (CI run 43842428591 green) whose `OspreyFlow_Core` was the candidate's exactly
and whose `OspreyFlow_Build` carried the run's tooling fixes (`lane/platform-b-v060-chart-before-listing`, to merge
after the release). Per `PACKAGE_TEST_SHEET.md`. Every record is on the server in
`~/osprey-runs/platform-b.c6/stage4-ea5fc61/` (40 files) and R1's `records/`.

**Before it (stage 3 on ea5fc61):** VERSION v0.6.0; `changelog_check --tag v0.6.0`; the four guides v0.6.0 with their
PDFs in step; citation and publication checks clean; the warm release dry run from a hash-checked archive, rc 0
(09:58:53–09:59:59Z, seven images built with the day's stamp and clean in trivy, the lock refusing only our five, the
chart packaged); `make chart-check cp-policy-check` against the run copy, 393 passed (with
`test_cp_egress_order.py`'s seed test).

## The rows

| # | Result | What it showed |
| --- | --- | --- |
| 0, 0m | PASS (155 s) | the 32 GiB node; `registry: osprey-r1-registry started (empty)`; the stand-ins; the sampler every 15 s |
| 1 | PASS (349 s) | the cold INSTALL, every block; the search rebuild Job Completed; the Glass answers |
| 2 | PASS | R1's 37 checks, first time |
| 3 | PASS | the dashboards check, 41 checks and 2 RECORD lines: a builder's own Superset session reads the whole mart (ADR-148 Amendment 21, stated); the other-unit case mirrored, R1 mapping units from groups. OspreyReader live: the reader `['OspreyReader']`, refused saving (403), reading no figure (403) |
| 4, 4b, 4c | PASS | spec 08 on poc: 14 passed, 15 skipped (dispositioned); its seed-free halves 3 passed; both plants red, as built green |
| 5 | PASS | a set; a change after it made, found, and gone after the restore; the rebuild (225/225) and the drift check (none) run once |
| 6 | PASS | INSTALL step 9's POC seed run as written: `seed: done, hmp, fixture-corp, scenarios`, then the index rebuilt (1517/1517); a picture written through the analyst's door and read back; the manifest verify 51 of 51 (the tile cache said: no tier-3/4 provider on this install) |
| 7 | PASS | the soak and the sampler's report (below) |
| 8 | PASS | DECOMMISSION with no choice refused at step 7 in the product's words ("there is no default"); with keep from block 9 (step 7; the sheet's `--from 7` predates blocks 7 and 8), every block, the backups bucket kept and named |
| 9 | PASS | `remake` kept the registry and 11 images (`registry: osprey-r1-registry kept, reused`); the warm INSTALL 247 s (cold 349 s); R1's 37 checks |
| 9b | FINDING (product), fixed for the next candidate | Amendment 18's refusal works live: a token minted as the Glass gets it, at v1.0, is refused on `/v1/me` in the amendment's words. **INSTALL step 6's block reads one api pod** (`kubectl logs deploy/api`), so it missed the Conduit's one-time `token version:` line held by the other pod and said all was well (case's ruling: fixed in v0.6.0, platform's `lane/platform-v060-step6-all-pods`). An app-only v1.0 token gets the plain refusal: v0.6.1's question. The sheet's `py check` mints its people's tokens itself, so it cannot show this row; the Glass path is the test |
| 10 | PASS, one recorded rerun | a set, then DECOMMISSION with destroy: the backups bucket's policy, its 124 objects, the bucket; the key's deletion scheduled for 2026-12-16; "backups: destroyed"; "0 thing(s) left behind". The first attempt collided by name with the sheet's own backup in the same minute (`row10-rerun-reason.txt`) |
| 11 | PASS | `down`: no cluster, no `osprey-r1-*` container, no `localhost:5001` image, no sampler |

## Memory (row 7; the sampler's report from the soak's mark)

156 samples, 0 gaps; the node's working set peaked at **12.92 GiB** of 32. Each container's peak and steady state
(MiB): ArcadeDB 5744 / 1497 (the peak during step 9's seed), OpenSearch 1151 / 1146, ClickHouse 659 / 586, NER 641 /
631, LiteLLM 496 / 491, Superset 410 / 391, the Conduit 334 / 295, PostgreSQL 333 / 295, the worker 218 / 217, Laurium
197 / 188, the report sync 136 / 78. No OOMKill; one restart each of the Conduit and the worker, step 9's scaling to
none and back. Nothing here changes a size (the owner's ruling: item 23 is out of v0.6.0).

## The search index's lag (row 4; ADR-150 Amendment 3)

A record just loaded or a grid just drawn was found 0.1 to 2.2 s later; a read after a redraw settled at 5.6 s.

## Reruns, each for a recorded reason outside the product

Row 10's first attempt (above). No other.
