# rules lane · report · L2.8d, a corrected node an alert names, and L2.8c's carries (8 November 2026; after two review rounds)

1. **Rulings:**
   - Q1 a: each caller records the corrected node, with no port change.
   - Q2: the L2.8c review's items 11 and 13 are built here.
   - Q3: Amendment 12.
   - Q4 a: the start-up DDL runs under a lock.
   - **The owner's ruling (a):** a lowering correction admits the lower reader to an alert with no node. It is applied through the one floor function, `alerts.raiser_floor`.
   - Decisions taken: none beyond these.
2. **The referent rename: met.** For every caller (confirm and retract routes, the close, `supersede.py` sync and job, the enrich stage), an alert naming the corrected node stays listed for its reader. It is refused to the OFFICIAL reader of the SECRET revision and to another case. Test: `test_repoint_journal_callers_live.py`'s `..._naming_..._stays_listed`. Each is red with that caller's record removed or the rename removed; the refusals are red with the revision at OFFICIAL, or with the case scope made true. A route confirming an alert's own node is covered (red: referents alone).
3. **Lowered markings, per the owner's ruling: met.**
   - A lowered node and a lowered link each admit the OFFICIAL reader to an alert with no node (raised through the rule gate's own row). Each is red with (b).
   - The queue, the audit and a pack item agree (red with (b)).
   - A node-bearing alert is never lowered (red with the node's marking dropped).
4. **Carries: met.**
   - (a) Two conformance cases.
   - (b) The `ALERTED_ON` guard.
   - (c) `remove_and_publish`; history serves no copy.
   - (d) The shared stand-in.
   - (e) DDL lock, one table per transaction, with no deadlock against a live read. Red cases: `UniqueViolation`; `DeadlockDetected`.
   - (f) A record opens at its first pair.
   - (g) Items 11 and 13.
5. **Review round 1 (my lane-reviewer):** 5 must-fix, 11 minor, all fixed but 2 minor.
6. **Review round 2 (independent):**
   - Items 1–3 fell away under ruling (a), replaced by the agreement test.
   - Item 4: the lock order.
   - Item 5: rebased, with the packs fix kept to its lines.
   - Item 6: the worker binds `judgement_store`, which is now required.
   - Item 9: the shared `RaiserReads` fake.
   - Item 10: every red re-taken at the rebased branch, and the stray lines removed.
   - Item 8 falls away under (a); an unjudgeable marking refuses one alert.
7. **Gate commit eae33d9, tree f12f9e2a2ce4128196de144f876c1a67eae1846b, on main 6336bed** (`gates/eae33d9.*`).
   - **make -k ci:** exit 0.
   - **make test:** Python 8,447 passed, 4 failed, 2 errors; JS 2,660/2,661. All are this machine's or Docker Hub's, and each is explained in the file.
   - **Live (rules lease, stack b, at 42ab45d, no code difference):** 626/628. The KYC case fails on main; the rule list fails on O-hyg's leftover rules.
8. **Found and fixed:** L2.8c's packs regression (14 live cases red on main) lands here.
9. **Contention (rule 14):** platform was on stack a unleased, 15:54–16:00Z; every run in that window was re-taken.
10. **Left, minor:** the AST registration test misses a register-by-keyword. Helpers are duplicated in the journals and the live file.
11. **Commits:** main..eae33d9 (11), then this records commit.
12. **Ratify (outside rules' map):** app.py, supersede.py, pipeline_run.py (studio), worker_main.py, working_set_revert.py, packs.py, the graph-port suite, spec 01, test fakes, test_packs.py.
13. **Requests:** mark Amendment 12 `written`.
14. **Still running:** nothing. Stack b is down and the lease released.
