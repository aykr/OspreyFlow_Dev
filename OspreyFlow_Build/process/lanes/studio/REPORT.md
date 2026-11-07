# studio lane · report · L1.2a Part A (main's red tests, and Amendment 15), 7 November 2026
1. **Revert tests: met** (`4d35c07`, `b56b24e`). ADR-110 Amendment 6 point 3 says the adapter is right. The fakes now require `withdrawn_by_load = null` and store it. Red with the clear removed from the adapter.
2. **`test_unfiltered_node_lookup_confined`: met, because the read is gone.** My first fix allowlisted the read; the review showed its ground false, so I dropped that commit. Under the owner's "Never withdraw nodes" (ADR-110 Amendment 15, `8a0fca5`):
   - a full snapshot withdraws a dropped row's links and events, never a node (`cb84f7f`);
   - a kept link is counted only from its own pipeline's rows in the case (`elements_kept_by_other_rows(..., only_this_pipeline=True)`, in the real store, `LedgerSink`, the Protocols and the fake);
   - metering counts no withdrawal.
   `test_snapshot_withdrawal.py` is red with node withdrawal restored and with the count taken from every row; `test_metering.py` is red with withdrawals counted. A merge counts as the create it stands for (`cc8967b`, red with merges uncounted), so Amendment 15 point 5 says so and the disclosure is dropped.
3. **The real-path test: met, live, under the lease** (`e690ade`). `test_snapshot_withdrawal_tells_nothing_live.py` drives `run_recipe_as` over the real `RecipeRunStore`. With and without another case's row and hidden link on the dropped row's node, it finds the whole `ScheduleRunView`, the whole `report_view` and the case's live nodes identical (only ids, times and `wall_ms` are left out). It is red three ways under the lease:
   - node withdrawal restored: the live nodes differ;
   - metering counting withdrawals: the run view differs;
   - the kept-link count taken from every row: the report view differs.
   `test_source_refresh_snapshot_live.py`, updated to Amendment 15, passes (2 of 2).
4. **Lease:** studio, "Part A live: two snapshot-withdrawal live files". Taken 12:47:45Z, released 12:49:13Z. The four throwaway containers were stopped when the lease came to me; I started them, ran the two files and stopped them.
5. **`test_load_checks.py`: met** (`464b5ad`). The two verify cases were red on main with `KeyError`. The whole file (9 tests, 4 Postgres-backed) passes 9 of 9 on the throwaway stack under lease studio, "Part A: test_load_checks.py, the whole file": taken 12:50:19Z, run 12:50:24Z to 12:50:27Z, stack stopped, released 12:50:30Z. This closes the omission. The earlier run of all 9 was unleased (breach 2).
6. **Two rule 14 breaches** (reported, in the friction row): that run, and an earlier `tests/ingest -k "not live"` run whose name filter missed files that reach the stack.
7. **Request:** apply `process/lanes/studio/L1.2a_ci_makefile.diff` (ci.yml and `OspreyFlow_Build/Makefile`). It supersedes L1.1's and wires L1.1's six live files plus the new one; with it, the test-file coverage check reads "737 test file(s), 0 allowlisted, no new drift".
8. **Commits after main `bc853bd`:** `4d35c07 464b5ad 5061df4 cb84f7f b56b24e 8a0fca5 cc8967b efb8bdd e690ade`, then this report. **Questions:** none. **Running:** nothing; the lease is released and the stack is down.
