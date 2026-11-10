# Case lane · brief L3.6 · drawn watches in the one queue, and *Open the board*

Written by the orchestrator, 10 November 2026, for the case session, **from main at 97e6689** (L3.9 merged). Size S.
ADR-143 Amendment 2 decision 8 replaced L3.6's separate alert kind: what is left is the `drawn_watch` kind's cases in
the one queue and *Open the board*. **It builds on rules' L2.10** (the one queue, team routing), which is re-gating
now: read lane/rules for the queue's shape, write tests first, and rebase onto main as soon as the orchestrator says
L2.10 has merged; touch no rules file before then.

**The lane, the stacks, the merge rule.** As L3.9's: stacks on the server only (b to g), Docker never started by a
lane; ask for a stack and before `make -k ci` or Playwright here; `make test` through `stack_lease.sh offline case`;
one server run at a time. Never stop on a question: the strict option for access, logged under "Decisions taken".
Your own lane-reviewer, then the gates at a commit rebased onto main. Report **by message**.

**Build:**
1. A drawn watch's match raises one alert per match per case in the one queue (`drawn_watch` kind), routed as the
   queue routes, and **withheld from a reader who may not see the watched item** (rule 3: no count, no bucket, no
   existence), red first at the adapter.
2. *Open the board* from the alert, by keyboard (rule 13), axe in three themes.
3. CARRIES' case rows that fit: board_store's item columns and row helper exported for the grading change (in place of
   case-b's copy); link types a drawing cannot satisfy (ROLE_IN's role) not offered, or the property asked for.
   Name any you leave.

**Exit.** One alert per match per case, withheld from a reader who may not see the item; *Open the board* by
keyboard; a friction row.
