# Case lane · P9 round 5 (the orchestrator's second review of afc1a5f) · report, 12 November 2026

Gated head **`382688b`** on `lane/case-p9`, rebased on main `8be1b77`; `b27f78e` re-anchors two plants (the plant file alone). Gates (`gates/382688b.notes.md`): `make -k ci` **exit 0** (cp-policy-check 0 violation(s) on all five fixtures; harness-a11y in slot 14, 34 passed); `make test` **12465 passed**, 2 failed (the server's GPU, OpenSearch's memory case: both known), 2 xfailed strict (the restores' rows awaiting `P9_rows.diff`); `make live-collect` **exit 0**. With the three diffs applied: 0 violation(s) on all five, 724 passed none held, the diff's plants 5 of 5 (`p9_cp_policy_merged.r3.txt`); P9's plants **104 of 104** red (`p9_reds.r5.log`).

| Review item | State | Proof |
| --- | --- | --- |
| 1 MUST: step 2's wait held by kept backup Job pods | **Fixed** (`!job-name`); the runbook's restore **walked as written** on osprey-p9 under lease b after backups had run (13 Job pods kept): back as the set, nothing left, CronJobs resumed; the old wait shown red | `p9_kind_runbook_walk.r5.json`, `p9_runbook_wait_red.r5.txt` |
| 2 parts mixed part-way | **Said** in Am 7 point 8 and per refusal in *If it fails*; the same set again is the way out | RUNBOOK |
| 3 RDS re-pointed after step 2 | **Done** | RUNBOOK |
| 4 interrupted swap | **Done**: the recovery pod's command, decided by `<database>.restoring`; the `create_database_if_absent` warning | RUNBOOK |
| 5 room for a second copy | **Done**: the checks before step 1 | RUNBOOK |
| 6 restore-graph's words | **Fixed**: "put back" only when it was, "not touched" only before the move, no live database said, the old copy's removal checked | `test_restore_graph.py` (failed put-in, put-back, old copy left) |
| 7 the check's two branches | **Reached**: a stray short page file, a zip holding no file; plants red | `test_restore_graph.py` |
| 8 plants and merged record at the final head; ROUND4's tick | **Done** | above |
| Notes | Jobs read for writers; another set's stale restored copy dropped and said; the set-aside refusal names the fresh copy; the drop-the-old refusal in *If it fails*; P9_render.diff's exception narrowed to ClickHouse's pod; no build words; PyYAML said | `test_backups_render.py`, `test_platform_backup.py` |

**For the orchestrator, in order:** `P9_render.diff`, `P9_rows.diff`, `P9_decommission.diff`; `P9_carries.diff` (yours: the Keeper path's DROP on the live-checks row, the check's time on a real graph). **Questions for the owner:** rulings A and 9 (Am 7 points 4 and 10). **Running:** osprey-p9, up for review (round 5's code), down on the orchestrator's word or by the server's timer, Friday 13 November 11:25 UK. No lease held.
