# Case-b lane · brief L3.8 · the ownership route for Disable…

Written by the orchestrator, 9 November 2026, after L3.7's merge (`e935ded`), for a **fresh case-b session on
the default account** (`ayan`; the owner, 9 November: every lane moves to it at its next changeover). Read
`process/lanes/case-b/REPORT.md` (L3.7) and the ADRs on Admin's *Disable…* and person removal (ADR-145, and the
admin lane's L2.5 report, `process/lanes/admin/REPORT.md` history) first. Rebase onto `main`. Opus, medium.
Size S. Case (the parent) is on L3.4 beside you; L3.4's promotion store is not on main yet.

**The lane, the stacks, the merge rule.** Your files are the map's row for this lane in
`process/BUILD_PLAN_PARALLEL_LANES.md`; anything else is a request to the orchestrator, never your parent's files.
**Ask the orchestrator before taking a test stack**; then `stack_lease.sh acquire case-b "<purpose>" && …`,
at most two leased live runs on the machine at once. Prompt L's rules: never stop on a question; schemas ride
with the step; every live test removes what it writes; your own lane-reviewer, then make -k ci, make test and
test-js at a commit rebased onto main, saved under gates/, with a leased live run including `test_route_rights.py`.

**Binds.** `process/CLAUDE.md` rules 1–15 (3, 4, 7, 12 and 15 above all).

**Build** (the plan's row L3.8): the ownership route Admin's *Disable…* reads: for one person, what they own —
views, boards, promotions they proposed or must review, proposed link types, watches if the store is on main —
so an administrator can transfer each before disabling them.
- **Who may read it:** an administrator who may disable people (`manage_people`), and no one else.
- **What it gives:** counts and display names only; never an identity-provider id or a source-system identifier
  (rule 7); an item above the administrator's own clearance is counted in words ("2 you can't see") or left out,
  strictly so its existence can't be inferred beyond what Admin's People already shows.
- **Promotions:** read L3.4's store if it is on main when you build; otherwise leave a seam named in the report,
  and case wires it.
- **Tests first:** an access test (non-administrator refused; a hidden item never named), a row in
  `test_route_rights.py`, each red by a plant at the real call site (rule 15).

**Exit.** The row's exit (Lane 2's L2.5b consumes it); make ci, make test and test-js green offline; a friction
fragment. Report in Prompt L's format, then stop.
