# Admin lane · brief T1 part 4 · parallel live runs, built on a branch

Written by the orchestrator, 10 November 2026 evening, for the admin session, **from main**. The mark commit stays for
tomorrow morning, as planned. Size M.

**The lane, the stacks, the merge rule.** Test stacks on the server only, Docker never started on this Mac. **Tonight the demo track (rules L2.11, studio L1.7, docs D2b) has first call on both local heavy slots and the stacks**: work offline first, and ask the orchestrator for a slot or stack, expecting to wait. `make test` through `stack_lease.sh offline <lane>`; a live check through `stack_lease.sh live <lane> -- --continue-on-collection-errors`. Never stop on a question: the strict option for access, logged. Take the `make -k ci` slot at every gate; lint from the branch's own diff. Your own lane-reviewer, then the gates. Report **by message**.

**Build:** part 4 of T1's brief, on its own branch, **touching no shared test file tonight**: pytest-xdist
(licence-checked) across 4–8 workers against one stack, each worker isolated (its own ArcadeDB database names, Postgres
schema or database, Valkey prefix or DB, ClickHouse database, object-store prefix), through the fixtures in one
conftest place. Tests first: two workers writing the same names never see each other's rows; a planted cross-worker
leak is caught; **rule 3's access-control live tests pass unchanged under it** (one live run on a stack when the
demo track has freed them). Then measure the graph_port suite serial and parallel on one commit. Part 5 (the slow
waits: the PID storyline, Gremlin chunking, the keep-alive) only if part 4 is done.

**Exit.** Isolation proven red first; the same suite's wall time serial and parallel; a friction row.

**Added at the owner's word (10 November evening): `make test` in parallel.** Once part 4's isolation is proven, apply
the same workers to `make test` itself (offline, on the server's 16 cores): `-n auto` (or a measured N) with
`--dist loadgroup`, the files that cannot share a process kept to one worker, and the order-dependence it exposes fixed
or named. Prove it: the same commit's `make test` serial and parallel give the same pass and fail set, and the wall
time before and after. Its Makefile half as a diff for the orchestrator.

**Decided by the orchestrator, 10 November evening (T1 part 4):** (a) the test stacks' Postgres `max_connections`
raised to 400 through `scripts/stack_lease.sh`'s `up` (ratified for that one setting; test stacks only, never
`osprey-small` or the product's settings), with a test, red first; ClickHouse left unredirected (its live tests name
their own databases), recorded in the friction row.

