# rules lane · report · L2.8d, a corrected node an alert names, and L2.8c's carries (8 November 2026)

1. **Rulings (orchestrator and owner, recorded):**
   - Q1 a: each caller records the corrected node, with no port change.
   - Q2: the L2.8c review's items 11 and 13 are built here.
   - Q3: ADR-109 Amendment 12 reserved and written.
   - Q4 a: the start-up DDL runs under a lock.
   - The reviewer's item 4 was settled on (b), the safe default. **An owner question is open:** may a correction that lowers a marking admit lower readers to an alert with no node? If (a), it is one line in `raiser_read_admits`.
2. **The referent rename: met.** For every caller (confirm and retract routes, the close, `supersede.py` sync and job, the enrich stage), an alert naming the corrected node stays listed for its reader. It is refused to the OFFICIAL reader of the SECRET revision and to another case. Test: `test_repoint_journal_callers_live.py`'s `..._naming_..._stays_listed`. Each is red with that caller's record removed or the settle's rename removed. The refusals are red with the revision at OFFICIAL, or with the case scope made true. A route confirming an alert's own node is covered too (reviewer item 1).
3. **Lowered markings: met.**
   - An alert with no node is not given to a reader below its raiser's read, for both a node and a link. Each is red with (a).
   - A re-mark never lowers a node; red with the node's own marking dropped.
   - A raised referent re-marks the alert's node; red with referents left out.
4. **Carries: met.**
   - (a) Two conformance cases: the other type elsewhere (red with id-only marking) and both types at the node (red with the label dropped).
   - (b) An Alert node carries only `ALERTED_ON` links; red with a planted `MENTIONED_IN`. The ontology doesn't guarantee it; the writer does.
   - (c) `remove_and_publish` is one helper; history serves no copy.
   - (d) The shared stand-in is used.
   - (e) Alert and hotlist stores share a DDL lock; red: `UniqueViolationError`. Ceilings are in point 4.
   - (f) A record opens at its first pair; red with it opened eagerly.
   - (g) Item 11: the stand-in's refusal is tested. Item 13: app.py registers through `register_all`, red with `alerts=` removed.
5. **Lane-reviewer: run, and fixed.** It returned five must-fix items (Alert node via a route, the incident conformance case, the hotlist DDL, lowered markings, gate evidence) and eleven minor ones. All are fixed except two minor ones left, below. Red records are in `l2.8d/`.
6. **Gate commit 6afb5b2, tree fbac952d8cf2a2989551d0f376758bdaee9676f8, on main 222b667** (`gates/6afb5b2.*`).
   - **make -k ci:** exit 0.
   - **make test:** Python 8,277 passed, 4 failed; JS 2,653/2,654. Every failure is this machine's, as at L2.8c, and is explained in the file.
   - **Live (rules lease, stack a):** 595/611 at a1bfc9e. The 16 failures:
     - 14 were packs: L2.8c's own regression on main, fixed at ba6f903, then 40/40.
     - KYC fails on main.
     - The rule list fails on O-hyg's leftover rules.
7. **Contention (rule 14):** platform reached stack a's Postgres unleased at 15:54–16:00Z. No `litellm*` database remains. Every run up to 16:01Z was re-taken.
8. **Left, minor:** the AST registration test misses a register-by-keyword. The journals' open-at-first-pair helpers are duplicated, and so are the live file's `_still_named`/`_still_listed`.
9. **Commits:** 1aa4dad, 9559d84, 49164b6, d13ed81, a1bfc9e, ba6f903, 6afb5b2, then this records commit.
10. **Ratify (outside rules' map):** app.py (routes, `register_all`), supersede.py, pipeline_run.py (studio), worker_main.py, working_set_revert.py, the graph-port suite, spec 01, the test fakes, test_packs.py.
11. **Requests:**
    - Mark ADR-109 Amendment 12 `written` in the reservations.
    - Put the open owner question on the owner's list.
12. **Still running:** nothing. Stack a is down and the lease released.
