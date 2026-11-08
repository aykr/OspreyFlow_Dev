# Case-b lane · brief L3.5 and L3.7 · analyst-defined link types, and the grading scheme

Written by the orchestrator, 8 November 2026, for the **case-b lane's first session** (ADR-142 Amendment 4).
Case (the parent) is building L3.3, drawing boards, beside you. Read ADR-143 decisions 9 and 11 and
`process/lanes/case/REPORT.md` (L3.2b) first. Opus, medium. L3.5 is M, L3.7 is S; then L3.8 (S), briefed later.

**The lane, the stacks, the merge rule.** A sister lane (ADR-142 Amendment 4) on account `sol`: your files are
the map's row for this lane in `process/BUILD_PLAN_PARALLEL_LANES.md`, carved from your parent's, and anything
else is a request to the orchestrator. Your parent works beside you in its own worktree: never touch its
files, and if a step needs one, ask the orchestrator first. A test stack by `stack_lease.sh acquire case-b
"<purpose>" && …` only (three stacks now, a, b and c). Prompt L's rules: never stop on a question (log it under
"Decisions taken"; only loosening access, real data or contradicting an accepted ADR stops a piece); schemas
changes ride with the step; before ready-to-merge, your own lane-reviewer, then make -k ci and make test at a
commit rebased onto main, saved under `process/lanes/case-b/gates/`.

**Binds.** `process/CLAUDE.md` rules 1–15 (3, 4, 6, 12, 13 and 15 above all); ADR-143 decisions 9 and 11;
ADR-090 Amendment 4 (proposed types decided on the Studio's Model tab); `spec/01` and `spec/03`'s link-type
passages.

**Build** (the plan's rows L3.5 and L3.7, in order, one ready-to-merge for both):
1. **L3.5, analyst-defined link types** (decision 9) and the Model tab's proposals block: an analyst proposes a
   type in a case; its links cannot be promoted until it is accepted; accepted, they can.
2. **L3.7, the grading scheme setting and its change command** (decision 11): the dry run writes nothing, and
   grades keep their original.

**Tests first, each red by a plant at the real call site:** a proposed type's links refused promotion, then
allowed once accepted; a proposed type visible only where its case is (rule 3); the grading command's dry run
writes nothing (red with a write planted) and existing grades keep their original; keyboard cases (rule 13)
with registry ids as a diff; axe in dark, light and GOV.UK.

**Exit.** Both rows' exits; make ci and make test green offline; live cases under a named lease and stack; a
friction fragment. Report in Prompt L's format, then stop.
