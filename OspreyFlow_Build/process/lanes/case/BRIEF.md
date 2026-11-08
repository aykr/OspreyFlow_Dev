# Case lane · brief L3.2 · case views replace branches, and no branches anywhere

Written by the orchestrator, 8 November 2026, for a **fresh case session** on account `sol` (ADR-142
Amendment 3). The previous session's last step, L3.1b, is merged (`d198174`); read its report
(`process/lanes/case/REPORT_L3.1b.md`) for what it left. Rebase onto `main` first. Opus, medium. Size L.
The riskiest lane: every piece starts with its access and existence-leak tests, and the `lane-reviewer`
reads the step before you report ready to merge.

**Binds.** `process/CLAUDE.md` rules 1–15 (3, 4, 6, 12 and 15 above all); ADR-144 and its Amendment 1;
ADR-143 decision 1 and Amendment 2 (the analyst layer); ADR-099 Amendments 13–15; `spec/01`, `spec/02`,
`spec/03` and `spec/04` wherever they name a branch.

**Build** (the plan's row L3.2):
1. **Case views** (ADR-144), and `scripts.migrate_branches_to_views`, dry run first (the dry run writes
   nothing).
2. **No branches anywhere** (ADR-144 Amendment 1): gone from every route, screen, keyboard spec and spec;
   `tools/no_branches_check.py` wired into `make ci` (as a diff for the orchestrator: the Makefile and
   `ci.yml` are the owner's), shown red first with a planted branch word.
3. **A branch's unnamed writes** (proposals, extractions, `ALERTED_ON`) touching an original-layer node
   never reach the original case through the source (from L3.1's final review; test first).
4. **What a branch held:** branch-only items to the original case's layer, and anything in a legacy
   branch's or alert-jump case's own layer (cases made before L3.1) moved into the original case's
   layer, tagged `from_branch`.

5. **Carried from GitHub's CI on `e89d44a`** (recorded, not fixed, at the owner's word): axe's
   `target-size` (WCAG 2.2 AA) fails on `case-screen-options-harness.html` variant c, dark and light, on
   the ghost button *Add many from a list*. Fix it, with the harness's axe case red first.

**Ask the owner first** (through the orchestrator, as multiple choice, recommendation first) only if the
migration meets a case it cannot place: report it, never guess (as L3.1's migration did).

**Tests first, named, each red by a plant of the real call site's shape:** ADR-144's and Amendment 1's
tests; the migration's dry run writes nothing and the real run leaves every seeded case with its views
and no branch; an unnamed branch write never reaches the original case (red with the layer check
removed); the selection bar's view actions by keyboard (rule 13), with their registry ids sent to the
orchestrator as a diff.

**Exit.** The row's exit; every screen in the dark, light and GOV.UK themes with axe; the live cases
under a named lease and stack (`stack_lease.sh acquire case "<purpose>"` gives a or b; pin the ports it
prints); a friction fragment. Report in Prompt L's format, then stop.
