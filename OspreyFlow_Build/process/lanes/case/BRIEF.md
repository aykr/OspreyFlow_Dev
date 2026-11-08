# Case lane · brief L3.2b · no branches in the Glass, and the check in make ci

Written by the orchestrator, 8 November 2026, after L3.2's merge (`c3fc52f`), for a **fresh case session**
on account `sol`. Read `process/lanes/case/HANDOFF.md` and `REPORT.md` first: they are what this step starts
from and what it must not redo. Rebase onto `main`. Opus, medium. Size M. **First exit: L3.2b merges before
the run's single push**, because until then main's Glass calls the branch routes L3.2 removed.

**The lane, the stacks, the merge rule.** Case's ownership map; a test stack by `stack_lease.sh acquire case
"<purpose>" && …`, pinning the ports it prints; questions, requests and ready-to-merge to the orchestrator
by message (Prompt L); before ready-to-merge, your own lane-reviewer, then make -k ci and make test at a
commit rebased onto main, saved under `process/lanes/case/gates/`, with the commit and its tree.

**Binds.** `process/CLAUDE.md` rules 1–15 (3, 4, 11, 12, 13 and 15 above all); ADR-144 and Amendment 1;
ADR-143 decision 1 and Amendment 2; the owner's Q2 and Q4 and the orchestrator's Q1 and Q3 (REPORT.md).

**Build** (HANDOFF.md's list):
1. **The Glass without branches:** the Cases list with views; *Save as a view* on the selection bar and in
   the over-cap dialog (`save_as_view`); the *Views in this case* panel (share, delete); *Ask the model
   about these* saving a private view and asking with `view_id` (`ask_in_a_view`); the GOV.UK list and
   form; `canvas/branchNodes.ts` and `workingset/branchByFilter.ts` gone.
2. **A view opens collapsed at its own threshold** (`test_a_view_opens_collapsed_at_its_threshold`, spec 03
   §3.1b).
3. **G:** "branch" out of `spec/00`–`09`, with B14 in spec 08 (no origin link, as Q1 ruled).
4. **H:** axe's `target-size` on `case-screen-options-harness.html` variant c (the CI carry).
5. **`tools/no_branches_check.py` in make ci:** drop the tree test's xfail; send the Makefile and `ci.yml`
   wiring as a diff for the orchestrator.
6. **ADR-144 Amendment 2** (reserved for you): the refusal renamed `original_layer_read_only`, B14 withdrawn,
   and who applies a view's window and threshold.

**Tests first, each red by a plant at the real call site:** `keyboard/views.spec.ts` for every view action
(rule 13), registry ids as a diff; axe in dark, light and GOV.UK; a private view's panel shows nothing to
another member; the over-cap dialog's *Save as a view* by keyboard; the gate red with one branch word
planted in the Glass.

**Exit.** No branch word anywhere the gate scans; make ci (with the gate) and make test green offline; the
live view routes under a named lease and stack; a friction fragment. Report in Prompt L's format, then stop.
