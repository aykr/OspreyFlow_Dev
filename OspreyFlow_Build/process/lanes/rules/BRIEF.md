# Rules lane · brief L2.9 · four places: Rules and Monitoring, /alerts/<id>, the way back

Written by the orchestrator, 8 November 2026, after L2.8d's merge (`7dfb3a1`), for a **fresh rules session**
on account `sol`. Read `process/lanes/rules/REPORT.md` (L2.8d), ADR-145 Amendment 4 and ADR-146 first.
Rebase onto `main`. Opus, medium. Size L. After it come L2.10 (one queue, team routing; needs admin's L2.5),
L2.11 and L2.12. **L2.9 is one of the docs lane's gating steps**, with L2.10, L2.5, P1 and P3.

**The lane, the stacks, the merge rule.** Rules' ownership map (the shell, layout, Home, status bar, theme and
brand, the GOV.UK header, `alerts/**`, the Rules and Monitoring place and their Conduit modules); a test stack
by `stack_lease.sh acquire rules "<purpose>" && …` only; Prompt L's rules: never stop on a question (log it
under "Decisions taken"; only loosening access, real data or contradicting an accepted ADR stops a piece);
schemas changes ride with the step; before ready-to-merge, your own lane-reviewer, then make -k ci and make
test at a commit rebased onto main, saved under `process/lanes/rules/gates/`. This step touches access (a
place's routes refuse who may not enter it), so it gets the orchestrator's independent review too.

**Binds.** `process/CLAUDE.md` rules 1–15 (3, 4, 7, 12, 13 and 15 above all); ADR-145 decisions 1–3 and
Amendments 1 and 4 (four places; the switcher; each place follows the full checks its routes make); ADR-146
and Amendment 1 (the alerts journey; Rules and Monitoring as a place of its own); ADR-132 Amendments 5 and 6
(the GOV.UK header and its place switch); ADR-144 (views, for *Open the evidence*: case's L3.2 built the
view routes, and its L3.2b is building the Glass's views now, so use the views API and coordinate through
the orchestrator); `spec/02_GLASS_FRONTEND.md`'s shell sections.

**Build** (the plan's row L2.9):
1. **Rules and Monitoring as a fourth place:** in the switcher and in the GOV.UK header, offered only to the
   rights that open it (N6), its routes refusing anyone else; the place's own shell and tabs.
2. **Monitoring and its count leave the Glass** (reworking L2.2 and L2.3's rail and banner).
3. **The workspace router and `/alerts/<id>`:** an alert's own address, refused exactly as a missing alert
   to anyone who may not read it (rule 3; ADR-124's jump rule as amended); Home opens the alert.
4. ***Open the evidence*** as a private view of the alert's case with the way back (R5), replacing the alert
   jump's case-of-its-own (the orchestrator's interim Q1 from L3.2 ends here).

**Tests first, each red by a plant at the real call site:** ADR-145 Amendment 4's switcher test (each role
sees only its places, and each hidden place's routes refuse it); ADR-146's address, refusal and way-back
tests; `/alerts/<id>` for an unreadable alert answers exactly as for a missing one; keyboard cases in
`keyboard/shell.spec.ts` and the place's own spec (rule 13), registry ids as a diff; axe in dark, light and
GOV.UK.

**Exit.** The row's exit; make ci and make test green offline; live cases under a named lease and stack; a
friction fragment. Report in Prompt L's format, then stop.
