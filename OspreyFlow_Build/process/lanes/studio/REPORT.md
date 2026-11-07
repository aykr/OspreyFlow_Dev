# studio lane · report · L1.2a Part A2 (the cross-case link merge), 7 November 2026
1. **Verdict: not real on main, proved.** Part A's live proof drove the raw ArcadeDB adapter, which stamps nothing. The Conduit's own paths stamp a Studio load with its case's dataset and confine the loader, through the scheduler's `check_case` and through *Run now*'s `get_principal` (both `scope_to_case`). Cases on two datasets never merge.
2. **Proofs, on real ArcadeDB and the real case and dataset stores:** `test_studio_load_stamps_its_case_dataset_live.py` (scheduler, 2) and `test_studio_run_now_stamps_its_case_dataset_live.py` (Run now through httpx `ASGITransport`, 1). Red with the raw adapter (U), and with `scope_to_case` out of `check_case` (V, red at the merge itself) and out of `get_principal` (T).
3. **Shared dataset: by design.** ADR-102 Amendment 3, ADR-099 decision 2 and ADR-143's "joins the source dataset", quoted in the test and in Amendment 15. Two cases read one link alike; a third dataset's case reads none.
4. **Part A's live proof moved** onto the stamping path with confined principals, the other case on the loader's dataset. Plants a–f and H were re-run red on it. W, X, Y and Z are red at `second_run`, `third_run`, `third_said` and `coming_back`, which were never shown red before.
5. **Carried items:**
   - ClickHouse's withdraw and restore are bounded: each `NOT IN` limited to its chunk, the restore paged. Each chunk's ids are bound once with `WITH`, since twice overran the URL under the lease. A recorded-statement test is red on main's shape.
   - `withdrawn_row_keys_among` is chunked.
   - The fake-against-ledger test compares `withdrawn_before` and `withdrawn_row_keys_among`.
6. **Spec:** Amendment 15's point 7 and its cross-case limit, and spec 09's limits, now say "not real on main, by these tests"; spec 09 now has three limits.
7. **Lease:** studio, "Part A2 live: stamping proofs (scheduler, Run now), plants U V T W X Y Z, ClickHouse conformance", 22:41:06Z–22:50:21Z. Nothing else was on the ports; the stack is stopped. The touched set passed 110 of 110. Conformance on both adapters with the bound test passed 250 of 251; the frequency case fails on main too.
8. **Commits:** `0df7d59 1ffac7b 0cf6076 67cf8cf d13867e`, then the spec, record, friction row and this report.
9. **Requests:** ClickHouse's `event_frequency` RANGE frame (on main); stale words at `packages/schemas/sources.py:30-31`. **Questions:** none. **Running:** nothing; the lease is free. **Next:** Part B, after the merge.
