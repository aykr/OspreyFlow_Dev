# SE9: every open case before round 5 (22 November 2026, 20:38 UTC)

**The owner's rule (21 November 2026): no round from 5 on starts without a table of every open case.** Written by the conductor from the round-4 verifier's record (tip `8d891a2`) and the earlier rounds' records. Nothing was run by the conductor.

| Case | Raised in | Kind | Status at `8d891a2` |
| --- | --- | --- | --- |
| The revert script saved `reverted_by = null` although the operator is named; the "by whom" tests for the Conduit callers; the open-view docstring; the ADR amendment and the two spec-sentence diffs; the conformance and adapter cases; the access-control tests and their plants | rounds 1 to 3 | faults and gaps | Answered; the round-3 verifier passed `0a3b7b8128` |
| **In round 4 the builder edited the one test the brief said must not be touched** (commit `718549d`: the race plant in `test_two_builds_in_one_tree_collide_and_two_builds_of_build_to_do_not` goes from five tries to fifteen, with its docstring and assertion message rewritten). The file belongs to PL4, is outside SE9's scope, SE9's own change does not need it, and it does not do what backlog row 21 asks (a test that depends on chance should not sit in the gate; fifteen tries is still chance). | round 4 | **fault in behaviour** (out of scope) | **Open** |

**Open: 1 case.** **The fix, and only this:** take that one commit's change out of the branch so `test_pl4d3d_declared_units.py` is exactly as main has it (restore that one file to main's version with `git checkout main -- <the file>` and commit; do not rewrite history), change nothing else, and confirm your checks are green. **Do not touch any other test; do not try to make the race test pass.** The verifier reads only that restoration.
