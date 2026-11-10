# Rules-b lane · brief T3 · dialogs' colour contrast actually gated

Written by the orchestrator, 10 November 2026 evening, for the rules-b session, **from main**. Size S. Tooling:
`a11y/every-harness.spec.ts` ratified for this step.

**The lane, the stacks, the merge rule.** Test stacks on the server only, Docker never started on this Mac. **Tonight the demo track (rules L2.11, studio L1.7, docs D2b) has first call on both local heavy slots and the stacks**: work offline first, and ask the orchestrator for a slot or stack, expecting to wait. `make test` through `stack_lease.sh offline <lane>`; a live check through `stack_lease.sh live <lane> -- --continue-on-collection-errors`. Never stop on a question: the strict option for access, logged. Take the `make -k ci` slot at every gate; lint from the branch's own diff. Your own lane-reviewer, then the gates. Report **by message**.

**Build** (CARRIES' orchestrator row from your L2.11a and platform-b's P6): axe reports colour contrast inside a fixed,
transformed overlay, and 1:1 (invisible) text anywhere, as *incomplete*, not failed, so every-harness passes them.
Make every-harness fail on axe's incomplete `color-contrast` (or measure the tokens' pairs directly where axe
cannot), red first with the two plants you and platform-b found (text equal to its background in a dialog; 1:1 text in
a panel). Then run it across every harness and **list** what it newly finds; fix none of them tonight unless trivial
token use, and carry the rest by owner.

**Exit.** The gate red on both plants, green on main's tree or with each finding listed; a friction row.
