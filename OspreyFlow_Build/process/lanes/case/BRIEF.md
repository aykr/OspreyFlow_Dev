# Case lane · brief L3.3 · drawing boards

Written by the orchestrator, 8 November 2026, after L3.2b's merge (`3eca381`), for a **fresh case session**
on account `sol`. Read `process/lanes/case/REPORT.md` (L3.2b) and ADR-143 (decisions 4–8) with Amendments 2
and 3 first. Rebase onto `main`. Opus, medium. Size L. The riskiest lane: access and existence-leak tests
first, and the orchestrator's independent review before merge.

**The lane, the stacks, the merge rule.** Case's ownership map (with the new `boards/`); a test stack by
`stack_lease.sh acquire case "<purpose>" && …` only; Prompt L's rules: never stop on a question (log it under
"Decisions taken"; only loosening access, real data or contradicting an accepted ADR stops a piece); schemas
changes ride with the step; before ready-to-merge, your own lane-reviewer, then make -k ci and make test at a
commit rebased onto main, saved under `process/lanes/case/gates/`.

**Binds.** `process/CLAUDE.md` rules 1–15 (3, 4, 6, 9, 12, 13 and 15 above all); ADR-143 decisions 4–8 and
Amendments 2 and 3 (a fresh drawing's items live in its drawn dataset; who merges a drawn dataset); ADR-144
(views); ADR-146 (drawn items watched: the alert goes in the one queue, rules' L2.10, so build the watch and
leave its queue case to L3.6 with L2.10).

**Build** (the plan's row L3.3):
1. **Boards:** declare an item, link by handle, Alt-drag, right-click and keyboard; marking, grading and
   source on every drawn item; matching to existing entities (scored, never merged in storage: rule 6);
   pictures (ADR-105 Amendment 3).
2. **A board with no case makes a drawn dataset and its home case** (Amendment 2 decision 5).
3. **Drawing an item sets its watch** (decision 8), the watch only; its alert's queue case is L3.6's.
4. **The layer's marking ceiling:** no drawn item above the case's ceiling, refused in words.
5. **The restore test** the plan names.

**Tests first, each red by a plant at the real call site:** `keyboard/boards.spec.ts` for every board action
(rule 13), registry ids as a diff; ADR-143 Amendment 2's tests for decisions 3, 4, 5 and 8; a drawn item is
never readable outside its case (rule 3), red with the layer check removed; matching never merges (rule 6);
axe in dark, light and GOV.UK. **Open question 4** (moving versus linking) is a field analyst's check: build
the plan's recommended behaviour and log it for the owner.

**Exit.** The row's exit; make ci and make test green offline; the live cases under a named lease and stack;
a friction fragment. Report in Prompt L's format, then stop.
