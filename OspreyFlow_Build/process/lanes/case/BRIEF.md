# Case lane · brief L3.H1 · a hygiene step: one read-set rule, a home case kept, the run report's count

Written by the orchestrator, 10 November 2026, for the case session, **from main at a96036a** (L3.6 merged). Size S.
Each part merges on its own if it is ready before the others.

**The lane, the stacks, the merge rule.** As before: stacks on the server only, Docker never started on this Mac;
ask for a stack and before `make -k ci` or Playwright here; `make test` through `stack_lease.sh offline case`; a live
check through `stack_lease.sh live case` (merged today: the selection by change). Never stop on a question: the
strict option for access, logged. Your own lane-reviewer, then the gates. Report **by message**.

**Build** (CARRIES' case rows):
1. **One read-set rule.** A pure function in `services/api/dataset_scope.py` (ratified for this step) that both
   `scope_to_case` and `drawn_watches.case_read_set` call, so the borrowed-layer rule cannot drift between them.
   Red first: a plant at the shared function, caught through both callers' existing tests.
2. **A home case cannot be removed** (ADR-145 Am 4 decision 2; docs' D2a row): no route refuses it today. Refuse
   it in words, naming nothing of the case beyond what the reader already sees, red first.
3. **The run report states its drawn-watch count** (L3.6's carry): how many drawn-watch alerts a load raised, in
   words, counted only as the run's own principal may see.

**Exit.** The three, each red first; a friction row.
