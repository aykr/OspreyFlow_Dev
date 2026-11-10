# Admin lane · brief T1 · faster live test runs on the server

Written by the orchestrator, 10 November 2026, at the owner's word ("yes go ahead with all the steps"), for the admin
session, **from main**. A tooling step: no product code changes. Five parts, in order; each merges on its own, so
the lanes gain from the first as soon as it lands. Opus, medium.

**Why.** Studio's L1.7 live set (route rights, the whole of `tests/ingest` and `tests/conformance/graph_port`, ~20
named files) ran 2½ hours on stack f; rules' L2.10 delta about 1½. Measured at 10:24 UTC: the server's load 5.5 of 16
cores, each stack's ArcadeDB at 8–12% CPU. The runs are serial and wait on round trips and deliberate sleeps, not on
the machine.

**The lane, the stacks, the merge rule.** As before: stacks on the server only (b to g), Docker never started on this
Mac; ask the orchestrator for a stack and before `make -k ci` or Playwright here; one server run at a time. Never stop
on a question: build the recommended option and log it. Your own lane-reviewer, then the gates. Report **by
message**. `stack_lease.sh` and `lane_stacks.tsv` are the orchestrator's: ratified for this step. `pytest.ini`,
`conftest.py` files and test fixtures: ratified where a part needs them. The Makefile and `ci.yml` are the owner's:
changes as diffs, applied at merge. Rule 15 throughout: every new selector, flag or isolation is shown red first, at
its real call site.

**Build:**
1. **Measure.** Every `remote` and `offline` run's pytest gets `--durations=30` (and vitest its slowest list) so each
   log names its slowest tests; a live run's log records its wall time. Then one measured run of a large live set (the
   one studio ran: its command is in `~/osprey-runs/studio.meta/runs/last/cmd.sh` on the server) on a free stack, and a
   short written table: the 30 slowest tests, the share of time in sleeps/polling, and the share that needs no store.
2. **Live runs carry only what needs a store.** A marker (or the existing `_live`/`_store` naming, whichever is the
   rule already) that separates tests needing a real store from those that do not; a live run selects only the first,
   since `make test` already runs the rest. A test that needs a store and is not marked fails loudly (red first: an
   unmarked store test planted in the real shape).
3. **Select live tests by what changed.** A map from source paths to the live test files they reach (the graph adapter
   and port → `conformance/graph_port`; the scheduler → its tests; the Studio's run path → its ledgers; every change →
   `test_route_rights.py`), a `stack_lease.sh live <lane>` (or a script) that runs the selection for the lane's diff
   against main, and the full set kept as a nightly run on main. A path no rule covers selects the full set, never
   nothing (red first: a change under an unmapped path).
4. **Parallel live runs.** pytest-xdist (licence-checked) across 4–8 workers against one stack, each worker isolated:
   its own ArcadeDB database names, Postgres schema or database, Valkey key prefix or DB index, ClickHouse database,
   object-store prefix. Tests first: two workers writing the same names never see each other's rows; **rule 3's
   access-control live tests pass unchanged under it**, and a planted cross-worker leak is caught. Its own review
   before it is turned on for the lanes.
5. **The slow few.** From part 1's table: deliberate sleeps and polling loops in the slowest tests shortened (a fake
   clock for the scheduler, polling on an event rather than a timer), each change keeping what the test proves (show
   the test still goes red on its original fault).

**Exit.** A typical lane's live check measured before and after (wall time, same commit); the selection never runs
nothing; parallel runs keep every access-control result; a friction row per part.
