# studio lane · report · L1.2a Part A, redone ("Only the rows' events"), 7 November 2026
1. **The withdrawal takes only the dropped rows' own events and never touches the graph: met.** `6c1b09a`, `78e7ddc`. Each kept key now records its row's `event_ids` (the schema change is on main). The run asks only for this pipeline's own dropped keys; both other-case reads and `only_this_pipeline` are gone, and metering counts no withdrawal. Proved by `test_snapshot_withdrawal.py` (14) and `test_row_key_withdrawal_ledger.py`.
2. **Events set aside by id: met.** `bc1a6cf` adds `withdraw_events_by_id` (conformance case first) and removes `withdraw_events`, which nothing on any lane calls. DuckDB passes 124 of 124. On ClickHouse, with CI's image, all 6 withdrawal cases pass.
3. **The live proof: met.** `bef0496`, `5ac854e`. `test_snapshot_withdrawal_tells_nothing_live.py` uses two principals of two cases, through `run_recipe_as` and `run_published_recipe`, on real ArcadeDB, DuckDB and the ledger. It covers the row's return and the other case's timeline.
   - It is red four ways: link withdrawal restored, each of the two ledger reads, and events taken by link. Each is in `L1.2a_RED_RECORD.md`.
   - Green: 33 of 33 across the three live files and two unit files.
4. **Spec: met.** `2b27e3e`, `51819ea`. Amendment 15 is rewritten, title included (the reservation row takes it at merge), and spec 09 and spec 01 are corrected, with how earlier records revert and the known limits.
5. **The orchestrator's call, done** (`8a42214`, red twice). A run whose withdrawn rows come back says in words that it cannot be reverted. A row dropped again after coming back is left in place in words; before the fix it was a unique violation after the commit.
6. **The Studio's words** (`9b67faf`): "Withdraw their events; their nodes and links stay until their load is reverted". `sources.test.tsx` passes 9 of 9. Axe on the studio harness passes 72 checks (dark, light, GOV.UK).
7. **Self-review (lane-reviewer).**
   - Fixed: drop, back, drop; the old wording; the spec over-claiming; ClickHouse never run; the other case unread; a case blind to graph changes; reds missing for the ledger cases; stale words.
   - Kept, as limits in Amendment 15: the GIN indexes asserted; the untested retry; the live test's patched executor (the rule gate is not driven).
8. **Wide `tests/ingest` run** (18:25–18:45Z): 1,056 passed, 14 failed, 4 errors, none from this part. Of the failures: 8 are Postgres "too many clients" and 3 need `osprey.yaml`. The other 3 fail on main too: the PID r1 and r14 stays, and the KYC provenance case. `test_pin_calls_refresh_live.py` passes in 93.6 s.
9. **Lease:** studio, "L1.2a redo: withdrawal unit + live tests, red plants". Taken 18:01:42Z, released 18:50:16Z, stack stopped. Case ran inside it at about 18:09–18:10Z, so every live figure cited is from the re-runs after 18:21Z. A throwaway ClickHouse on 18123 was removed.
10. **Commits:** `bc1a6cf 6c1b09a bef0496 2b27e3e 4304f33 8a42214 78e7ddc 9b67faf 51819ea 5ac854e`, then this report with the friction row.
11. **Left:** L1.2c, revert counting a returning row's merge as its own, pending the owner. Part A2, the cross-case link merge, proved on main after this merges. Part B.
12. **Requests to the orchestrator:**
    - Apply `L1.2a_ci_makefile.diff`, unchanged.
    - ClickHouse's `test_frequency_counts_the_most_events_in_any_span_of_the_days_asked` fails in `event_frequency`, which this part does not touch.
    - Shared stale words: `packages/schemas/sources.py:30-31`, and `ingest.py:951-957` with the always-0 `links_kept_an_occurrence`.
    - A migration should drop the unused GIN indexes on the `node_ids` and `edge_ids` of `loaded_row_keys` and `withdrawn_row_keys`.
13. **Questions:** none. **Running:** nothing; the lease is free.
