# Case lane · P9 round 4 (the orchestrator's review of 7916044) · report, 12 November 2026

Gated head **`afc1a5f`** on `lane/case-p9`, rebased on main `816ccf7` (L1.9 part 2 in). Gates (`gates/afc1a5f.notes.md`): `make -k ci` **exit 0** (cp-policy-check 0 violation(s) on all five fixtures; harness-a11y in slot 14, 34 passed); `make test` **12459 passed**, 1 failed (the server's GPU, known), 2 xfailed strict (the restores' rows awaiting `P9_rows.diff`); `make live-collect` **exit 0**. With the three diffs applied: 0 violation(s) on all five, 717 passed none held, plants **96 of 96** red, the diff's **5 of 5** (`gates/p9_cp_policy_merged.r2.txt`).

| Review item | State | Proof |
| --- | --- | --- |
| 1 MUST: ArcadeDB never removed before its restore is proven | **Fixed**: restored into `<db>.restoring`, held to the set's zip and opened (ArcadeDB opens damage with only a warning, measured), swapped by rename; any failure leaves the live one; ClickHouse's failed second RENAME puts the live one back | `test_restore_graph.py` (ArcadeDB's own image); runbook's *Where the data is* |
| 2 ClickHouse's user to backup and restore-analytics alone | **Fixed** | `test_each_container_holds_the_secret_keys_its_command_calls_for_and_no_more` |
| 3 a killed run's zip | **Fixed**, red first | `test_a_zip_a_killed_run_left_…` |
| 4 kind, beside a live database (lease b) | **PASS**: back as the set, nothing left; truncated zip and ClickHouse's refused reads each leave the live data, refused for their own reason. It found a real bug: ClickHouse's Keeper path reused on the same set's second restore (Code 253), fixed red first | `gates/p9_kind_live_restore.r4.json` |
| 5 writers from the render; CronJobs suspended | **Fixed** (transitive over the rows; the report sync and the Glass caught) | `test_a_new_workload_that_writes_is_a_writer_without_naming_it` |
| 6 one set's name | **Fixed** | `test_a_restore_names_one_set_or_is_refused` |
| 7 two plants red for another reason | **Fixed**; also three plants that named unselectable cases, four re-anchored | `gates/p9_cp_policy_merged.r2.txt` |
| 8 stand-in's InvalidPart/Order, EntityTooSmall; RBAC 403; versioning | **Done** (Am 7 point 11; CARRIES row) | `test_s3_standin.py`, `test_the_api_refusing_…` |
| 9 RDS to the set's finish | **Done**: `finished` in each manifest, `sets` prints it; Am 7 point 10; runbook's first step; CARRIES | `test_a_set_records_when_it_finished_…` |
| 10 and notes | **Done**: Am 5 hunk dropped; runbook for the operator; UTC; database names from the render; malformed manifest; claims' swap keeps both; diffs re-cut with index lines | `P9_ROUND4.md` |

**For the orchestrator to apply, in order:** `P9_render.diff`, `P9_rows.diff`, `P9_decommission.diff`; and `P9_carries.diff` (yours). **Questions for the owner:** rulings A and 9 (listed in Am 7 points 4 and 10). **Running:** the osprey-p9 kind cluster, up for review (round 4's render), down on the orchestrator's word or at the latest by the server's timer, Friday 13 November 11:25 UK. No lease held.
