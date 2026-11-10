# Case lane · brief L3.H2 · drawn watches on every load, and the ceiling on promotions

Written by the orchestrator, 10 November 2026 evening, for the case session, **from main**. Size S. Client track
and carries; no demo-track files.

**The lane, the stacks, the merge rule.** Test stacks on the server only, Docker never started on this Mac. **Tonight the demo track (rules L2.11, studio L1.7, docs D2b) has first call on both local heavy slots and the stacks**: work offline first, and ask the orchestrator for a slot or stack, expecting to wait. `make test` through `stack_lease.sh offline <lane>`; a live check through `stack_lease.sh live <lane> -- --continue-on-collection-errors`. Never stop on a question: the strict option for access, logged. Take the `make -k ci` slot at every gate; lint from the branch's own diff. Your own lane-reviewer, then the gates. Report **by message**.

**Build** (CARRIES' case rows):
1. **Releasing held rows runs the drawn watches**, as every load does (spec 01), red first.
2. **ADR-148 decision 10 on the write side:** a promotion or a drawn merge writing data marked above
   `deployment.highest_marking` is refused before anything is written, in words naming the limit (`promotions.py`,
   `drawn_merge.py`). The read-side fallbacks that read an unmarked dataset at the scheme's highest stay (strict).
3. **test_home_cases:** a non-member holding remove_case gets 404; the administrator's path; and the read-set's async
   level check uses `app.holds_a_level_in` rather than a copy.

**Exit.** Each red first; a friction row.
