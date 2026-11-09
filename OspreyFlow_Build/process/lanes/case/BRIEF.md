# Case lane · brief L3.4 · promotion, and a removed case's layer merged or deleted

Written by the orchestrator, 9 November 2026, after L3.3's merge (`ab3d638`), for a **fresh case session** on
the orchestrator's account. Read `process/lanes/case/REPORT.md` (L3.3), ADR-143 decisions 8 and 10 and
Amendments 2–4 first. Rebase onto `main`. Opus, medium. Size L. The riskiest lane: access and existence-leak
tests first, and the orchestrator's independent review before merge. After it comes L3.9 (merging a drawn
dataset). Case-b (the sister lane) builds L3.7 and L3.8 beside you.

**The lane, the stacks, the merge rule.** Case's map minus case-b's; a test stack by `stack_lease.sh acquire
case "<purpose>" && …` only; Prompt L's rules (never stop on a question; schemas ride with the step; every live
test removes what it writes; your own lane-reviewer, then make -k ci and make test at a commit rebased onto
main, saved under gates/, with a leased live run including `test_route_rights.py` and every live file the
change reaches). The Studio's *Analyst promotions* list lives in `ingest/runs/`, studio's: by agreement, through
the orchestrator, and studio is building L1.5 now.

**Binds.** `process/CLAUDE.md` rules 1–15 (3, 4, 5, 6, 12 and 15 above all); ADR-143 decisions 1, 8 and 10 and
Amendments 2–4; ADR-145 Amendment 4 decisions 8 and 11 (the promotion policy admin built in L2.4 part 2: Author
promotes, or a second person reviews, the approvers being the dataset's Authors holding `review_promotions`);
ADR-140 (one load).

**Build** (the plan's row L3.4):
1. **Promotion:** the sheet; one load; the dataset's policy and highest marking enforced; review by the policy's
   approvers; *promotions overdue* (admin's L2.6 built the ageing against a seam: wire it).
2. **The Studio's *Analyst promotions* list** in `ingest/runs/`, by agreement.
3. **A removed case's layer merged** by the dataset's Authors as a promotion, with the read grant for that merge
   only, and its delete (Amendment 2 decision 1). A composite case's layer is never merged, only deleted (the
   orchestrator's settlement, admin's Q5); the owner may later choose a member merge.
4. **Carried:** the withdrawal rule settled for this step (spec 03; `MORNING.md` item 60): `board_items.
   promoted_at` set at promotion; an unseen promoted link stays and the withdrawer is told nothing. From
   `CARRIES.md`: mount rules-b's alert badge overlay and the boards' Alerts panel if rules-b's L2.12 has landed.

**Ask the owner first (through the orchestrator; it stops only that piece): open question 2, online revert of
a promotion.** Build the rest.

**Tests first, each red by a plant at the real call site:** ADR-143's promotion and policy tests; a promotion
above the dataset's highest marking refused; the read grant for a layer merge ends with that merge; no
promoted item is readable before review where the policy asks for one; decision 1's tests; keyboard cases
(rule 13), registry ids as a diff; axe in dark, light and GOV.UK.

**Exit.** The row's exit; make ci and make test green offline; live cases under a named lease and stack; a
friction fragment. Report in Prompt L's format, then stop.
