# studio lane · report · L1.2a Part A2 (the cross-case link merge), 7 November 2026, with its self-review
1. **Verdict: not real on main, proved.** Part A's live proof drove the raw ArcadeDB adapter, which stamps nothing. The Conduit stamps a Studio load with its case's dataset and confines the loader (`scope_to_case`), through *Run now*'s `get_principal` and through the scheduler, where each run is stamped by the `check_case` of its own `_owner`. Cases on two datasets never merge.
2. **Proofs, on real ArcadeDB and the real case and dataset stores:**
   - `test_studio_load_stamps_its_case_dataset_live.py`: the executor's closures; `ScheduleExecutor` with two pipelines due in one tick plus a run now; and a shared dataset.
   - `test_studio_run_now_stamps_its_case_dataset_live.py`: in process, through httpx `ASGITransport`.
   - Red with the raw adapter (U), with `scope_to_case` out of either entry point (V, T), with owners resolved before any runs (S1), with Run now stamping but not confining (S2), and with nobody confined (S3).
3. **Grounds:** cases on one dataset share a link by design (ADR-102 Amendment 3); cases on two datasets write two nodes (the owner's ruling, ADR-099 Amendment 16).
4. **Part A's live proof** runs confined on the stamping path, and every live world under a recipe id of its own. Plants a–f and H, and W, X, Y and Z (`second_run`, `third_run`, `third_said`, `coming_back`), are red in their natural shapes.
5. **Carried, done:**
   - ClickHouse's withdraw and restore send bounded statements: one `WITH`-bound list, `has(ids, …)` in each `NOT IN`, the restore paged.
   - A test refuses httpx's URL limit as the real client does. It is red on main, and red on my own twice-bound version (`6a05fa3`, before `2e28211`).
   - `withdrawn_row_keys_among` is chunked, and the fake-against-ledger test runs over two cases (red with the fake ignoring the case: F).
6. **Open, in Amendment 15 and spec 09:** a source refresh through `case_for_dataset` is not driven, since the fixture's pipeline names no dataset. The stamp is the case's first dataset until Part C (the orchestrator's call).
7. **Self-review:** the lane-reviewer found a shared recipe id across worlds, which had me bend plant Z to parity; two files missing from CI; untested assertions and orders; claims wider than the tests; and a lax bounds test. All are fixed, and the first A2 round is marked superseded.
8. **Lease:** studio, "Part A2 re-run: fresh-id plants a-f H W-Z, S1 S2 S3 F U V T, conformance, touched set", 23:38:24Z–23:42:53Z. `lsof`, `pgrep` and `docker ps` were clean before and after, and the stack is stopped. The twelve touched files (listed in the record) pass 158 of 158; both adapters' conformance passes 249 of 250, the frequency case failing on main too.
9. **Commits** (on `2b9d177`): `6a05fa3 ea75535 2e28211 7d500b7 9c9e6f1 8dd87f7 6d828f0 5d4becb 88ede9c af7c936 310e2d5 01b17c7 ddef319 eee37d6 2dd576a`, then this report.
10. **Requests:**
    - apply `L1.2a_A2_ci_makefile.diff`;
    - ClickHouse's `event_frequency` RANGE frame, on main;
    - the stale words at `packages/schemas/sources.py:30-31`;
    - record the ratification of the ClickHouse adapter and `recipe_runs.py` at merge.
11. **Questions:** none. **Running:** nothing; the lease is free. **Next:** L1.2c (ADR-110 Amendment 16), then Part B.
