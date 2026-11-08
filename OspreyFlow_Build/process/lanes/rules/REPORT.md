# rules lane · report · L2.8c, the other supersedes through the repoint journal (8 November 2026; after review rounds 1 and 2)

1. **Settlements (the orchestrator's, 8 November, on the owner's review list):** Q1 a (the graph names each clone `superseded_by`, reported to `on_link_cloned` before the commit); Q2 a (the purge published to connected canvases); Q3 a (D8 measured under the lease); the referent-node gap is its own step, L2.8d, before L2.9. ADR-109 Amendment 11 written under its reserved heading.
2. **D8–D10: met.** D8, `get_authorized` by id under the rules lease on stack b: 1.85 / 6.27 / 82.46 ms median with 0 / 1 / 10 pending records (Amendment 11 point 7, `l2.8c/d8-timing.txt`). D9 and D10 in `test_repoint_journal_callers_live.py`: the rename and repoint never deadlock; the busy pool refuses in words, and a read stops at the first refusal; record locks in their own key space (each red: deadlock, the bound, skipped, four waits).
3. **Every caller through the journal: met.** An alert citing the link each caller replaces stays listed for its reader and refused to the OFFICIAL reader of the SECRET clone and to another case. The callers: the confirm and retract routes, the close's confirm, `supersede.py` sync and job, the enrich stage, `NOT_SAME_AS`. Each is red with its journal entry removed, the clone written at OFFICIAL, or the case scope made true.
4. **The graph: met.** Conformance cases: the clone named before the commit; a rolled-back correction leaves no mark; a self-loop is cloned once, new node to new node (round 2's must-fix; red with the old order).
5. **Records outlive no writer, and no writer outlives its record: met.** A writer held open past the stale limit keeps its record (red: dropped). A cancelled outside-commit writer closes its record and stops its keep-alive (red: kept beating). A re-mark counts a cited link's ends (red: the node stayed OFFICIAL).
6. **Bindings at their call sites: met.** `recipe_run` → runner, runner → stage, the stamping graph → adapter, the worker's `register_all`. `alerts` is now a required keyword on both jobs (`test_pipeline_enrich_journal.py`, `test_worker_registration.py`, each red at its site).
7. **Purge published: met.** The purge is published, and each socket projects it for its reader (red: nothing sent / no record). The re-marking script publishes too. A settle holding no working set still waits for a socket's resync (Amendment 11 point 8).
8. **Step 3, the fakes' tolerance: met** (red with it put back).
9. **Gate commit e9c8fd3, tree 0a8da0dc, rebased on main 2b984f2** (admin's L2.4 part 2 merged; `gates/e9c8fd3.*`). **Leased run** on stack a, 15:16–15:22Z: 97/97, covering this lane's live file and the graph-port suite's supersede, restore, withdraw, revert, link-state and footprint cases. **make -k ci:** exit 0, every gate green. **make test:** Python 8,220 passed, 4 failed, 2 errors; JS 2,653/2,654. None of the failures are this branch's: the local osprey.yaml; the closed Valkey port; `graphify-out` at the root; the phone fixture's object store, closed offline; the proxy image build, refused by Docker Hub's 429; and a MatrixView budget under load, which passes alone. The earlier run at 47435fa, before the rebase, is kept: its leased run was 150/151, the one failure the KYC test that fails on main.
10. **Graph-port withdraw cases:** with main's `_restore_link_state`, the withdraw and link-state cases pass under the marking (`round1/withdraw-cases-with-marking.txt`; the leased run above).
11. **Carried to L2.8d, a line each:**
    - (a) A conformance case for "another type holding the id is never marked" (Amendment 11 point 1).
    - (b) A test that an Alert node carries only `ALERTED_ON` links, which no rule cites (point 3's exemption).
    - (c) `purge_copies` vs `WorkingSetReverter.remove`'s history scrub: one helper, and whether history serves old copies.
    - (d) `test_written_back_reads_in_full_stages.py`'s own `_Store.repointing` to the shared stand-in.
    - (e) Each worker replica now runs the alert store's DDL and opens its pools: Postgres's concurrent-DDL and connection ceilings.
    - (f) An enrich stage opens a record even when it writes no point.
    - (g) The review's 11 and 13 as ruled.
12. **Commits:**
    - b9f960f-era work rebased onto 83b3d17. Round 0: step 3; D9 and D10; the graph marking; the callers and publish; the amendment.
    - 3b3066f round 1, then rebased.
    - 18d4e9d round 2 (47435fa before the rebase onto 2b984f2).
    - e9c8fd3 the first gate records; this commit holds the second.
13. **Ratify (outside rules' map):**
    - Graph: `ports/graph.py`; the ArcadeDB adapter (marking and self-loop); graph-port suite cases.
    - Case's: `dataset_scope.py`; `working_set/service.py` (`publisher`, 7 lines after `__init__`).
    - Studio's: `pipeline_run.py`, `recipe_run.py`.
    - Others: `extract/writer.py`; `app.py` (two routes, two registrations); `supersede.py`; `worker_main.py`; `resolve/same_as_writer.py`, `trigger.py`; `link_changes.py`, `entity_pictures.py`; `scripts/remark_alert_nodes.py`.
    - Spec and tests: `spec/01_DOMAIN_MODEL.md`; the listed test fakes and `repoint_journal_fakes.py`.
14. **Requests:** none open. Main took the stack-b pin, `test_port_guard` and `_restore_link_state` (83b3d17).
15. **Still running:** nothing. Stack b down, lease released.
