# Admin lane · brief L2.6 · the Audit section, and Operations' ageing

Written by the orchestrator, 8 November 2026, after L2.5's merge (`3656678`), for a **fresh admin session**
on the orchestrator's account. Read `process/lanes/admin/REPORT.md` (L2.5) first. Rebase onto `main`. Sonnet
or Opus at medium, as the plan says for L2.6–L2.7. Size M. After it comes L2.7, then L2.5b once case's
ownership route (L3.8) is on main.

**The lane, the stacks, the merge rule.** Admin's ownership map; a test stack by `stack_lease.sh acquire
admin "<purpose>" && …` only; Prompt L's rules: never stop on a question (log it under "Decisions taken";
only loosening access, real data or contradicting an accepted ADR stops a piece); schemas changes ride with
the step; before ready-to-merge, your own lane-reviewer, then make -k ci and make test at a commit rebased
onto main, saved under `process/lanes/admin/gates/`. The Audit section touches access (who reads which
audit, by unit), so it gets the orchestrator's independent review too.

**Binds.** `process/CLAUDE.md` rules 1–15 (3, 4, 7, 12, 13 and 15 above all); ADR-145 decision 9, O2 and O3,
Amendment 4 decision 11 (R7); ADR-112 (`read_audit`, `read_rule_audit`); ADR-146 Amendment 2 (rules' L2.9:
the rule audit leaves Rules and Monitoring for the Administrator and returns here).

**Build** (the plan's row L2.6):
1. **Admin › Audit (O2):** every audit the deployment keeps, read by unit as the plan's exit says (a reader
   of one unit sees that unit's entries alone); the rule audit for the Administrator (rules' L2.9 handed it
   here); filters by who, what and when; the words an entry holds withheld exactly as their own reads
   withhold them (rule 3: an entry naming what the reader may not see shows its existence only as the
   existing audits already decide).
2. **Operations' ageing (O3):** what ages and when, inside *Admin › Running › Operations*.
3. ***Promotions overdue*** (R7) to the dataset's Authors holding `review_promotions`, fired once at N days.
   Promotions themselves are case's L3.4: build the ageing rule and the alert against the promotion record's
   shape as L3.4's brief will define it, behind one named seam, and say what is left for L3.4; if nothing
   can be built usefully before L3.4, log it under "Decisions taken" and leave it.

**Tests first, each red by a plant at the real call site:** the audit access test by unit (red with the
unit filter removed); an entry's withheld words stay withheld; the overdue alert fires once at N days (if
built); keyboard cases (rule 13) with registry ids as a diff; axe in dark, light and GOV.UK.

**Exit.** The row's exit (or its promotions part named as left); make ci and make test green offline; a
friction fragment. Report in Prompt L's format, then stop.
