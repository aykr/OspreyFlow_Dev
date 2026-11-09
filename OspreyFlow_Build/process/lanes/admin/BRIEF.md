# Admin lane · brief L2.7 · *Needs you*, Home's *What you can do*, and Admin's tips

Written by the orchestrator, 9 November 2026, after L2.6's merge (`0194eec`), for the **admin session already
open** on the default account (`ayan`), or a fresh one. Read `process/lanes/admin/REPORT.md` (L2.6, especially
items 4 and 8, "Left for L2.7") and ADR-145 Amendment 4 decisions 11 and 12, as ruled by the owner on 9
November (option (c): a refusal or tip names the **roles** that hold a right, never people). Rebase onto
`main`. Opus, medium. Size M. After it comes L2.5b, once case-b's ownership route (L3.8) is on main.

**The lane, the stacks, the merge rule.** Admin's ownership map. The test stacks are on the owner's server
only (b to g); stack a and Docker are off on this Mac: never start Docker. Ask the orchestrator for a stack,
then use main's `OspreyFlow_Build/scripts/stack_lease.sh` (acquire, up, `remote admin -- …` from your
worktree's `OspreyFlow_Build`, down, release); `remote-log admin` reattaches a dropped run. Prompt L's rules:
never stop on a question (log it under "Decisions taken"), except that **loosening access stops the piece**:
L2.6's decision (j) was such a case and had to be withdrawn. Schemas ride with the step. Before
ready-to-merge: your own lane-reviewer, then `make -k ci` and `make test` offline at a commit rebased onto
main, saved under `gates/`, with a leased live run including `test_route_rights.py`. **Re-gate after any code
change**: L2.6's gates predated its last round. Report to the orchestrator **by message**, not only in your
window. This step shows people things on Home and in *Needs you*, so it gets the orchestrator's independent
review.

**Binds.** `process/CLAUDE.md` rules 1–15 (3, 4, 7, 12, 13 and 15 above all); ADR-145 Amendment 4 decisions
11 and 12; ADR-090 Amendment 4; ADR-143 Amendment 6 (the grading scheme); ADR-145 Amendment 6 (as merged).

**Build, in this order** (the plan's row L2.7):
1. **The data engineer's *Needs you*** (A2): *promotions overdue* through `PromotionAgeingStore.alerts_for`,
   passing `_promotion_recipients` as `still` (L2.6's seam), so an alert is shown only to a person who is
   still a recipient at read time; and the Model tab's proposal count, reminder and *Needs you* entry for
   analyst-defined link types (CARRIES, from case-b's L3.5). Nothing listed or counted that the reader can't
   see: a proposal above the reader's clearance shows only that one exists, as ADR-143 Amendment 4 (b) says.
2. **Remove Admin's *Proposed types* section**: proposals are decided on the Studio's Model tab (ADR-090
   Amendment 4; CARRIES, from case-b's L3.5).
3. ***Admin › Connections*** gains the SQL and API connection settings' fields (CARRIES, from studio-b's
   L1.6), within what ADR-140 Amendments 13 and 15 allow an administrator to see (secrets write-only).
4. **Admin's read-only display of the grading scheme** over `GET /v1/grading-scheme` (CARRIES, from case-b's
   L3.7).
5. **Once rules-b's L2.12 is on main** (it brings `help/roles.ts` and `admin-tips.patch`): Admin's tips for
   Roles' tables and team editor, People, Datasets and levels, and every disabled Admin action saying why and
   which roles can, through studio-b's `whyNotByRole` (CARRIES, narrowed by rules-b). Then Home's *What you can
   do, and what you answer for*, from the same source as the tips. If L2.12 hasn't landed when 1–4 are done,
   say so and wait; don't copy its files.

**Tests first, each red by a plant at the real call site:** *Needs you* shows an overdue promotion only to a
current recipient, red with `still` bypassed; the Model tab's count excludes proposals the reader can't read,
red with the filter removed; no tip or refusal names a person or a role id (a test over every Admin string,
like L1.8's `ui_words_check`); the Connections fields never return a secret; keyboard cases for every new
action (rule 13), registry ids as a diff; axe in dark, light and GOV.UK.

**Exit.** The row's exit ("the section lists nothing the reader can't see"); keyboard and tooltip cases; make
ci and make test green offline; live cases under a named lease and stack; a friction fragment. Report in
Prompt L's format, then stop.
