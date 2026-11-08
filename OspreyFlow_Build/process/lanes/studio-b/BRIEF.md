# Studio-b lane · brief L1.6 · phase 9: connectors, and the screening-list connector

Written by the orchestrator, 8 November 2026, for the **studio-b lane's first session** (ADR-142 Amendment 4).
Studio (the parent) is building L1.4, the staging drawers, beside you, then L1.5. Read ADR-140 Amendments 9,
11 and 12 and `process/lanes/studio/REPORT.md` (L1.3) first. Opus, medium. Size L; then L1.8 (S), briefed later.

**The lane, the stacks, the merge rule.** A sister lane (ADR-142 Amendment 4) on account `sol`: your files are
the map's row for this lane in `process/BUILD_PLAN_PARALLEL_LANES.md`, carved from your parent's, and anything
else is a request to the orchestrator. Your parent works beside you in its own worktree: never touch its
files, and if a step needs one, ask the orchestrator first. A test stack by `stack_lease.sh acquire studio-b
"<purpose>" && …` only (three stacks now, a, b and c). Prompt L's rules: never stop on a question (log it under
"Decisions taken"; only loosening access, real data or contradicting an accepted ADR stops a piece); schemas
changes ride with the step; before ready-to-merge, your own lane-reviewer, then make -k ci and make test at a
commit rebased onto main, saved under `process/lanes/studio-b/gates/`.

**Binds.** `process/CLAUDE.md` rules 1–15 (3, 8, 9, 12, 13 and 15 above all); ADR-140 and Amendments 9
(screening lists as reference lists), 11 and 12 (a dataset's own reference list from its version file;
L1.4's import module is a stand-in until this step); `spec/09_INGEST_STUDIO.md`; the redesign plan's phase 9.

**Build** (the plan's row L1.6):
1. **Phase 9's connectors** beyond CSV, as the redesign's plan lists them.
2. **The screening-list connector in Sources:** mapping templates (OFAC SDN, OFSI, UN, EU, OpenSanctions where
   licensed, and blank), each with a **synthetic** golden file (rule 9: no real list anywhere, in the
   repository or CI); deployment-wide import and per-dataset subscription (by list id, never by name: L1.3's
   rule 3 finding); a schedule and *Refresh now*.
3. **Import replaces L1.4's stand-in** for a dataset's own reference list rows, writing the version file
   Amendment 12 names; coordinate the seam with studio through the orchestrator.

**Tests first, each red by a plant at the real call site:** each template maps its golden file; a rule offers
only subscribed lists (with rules' queue); a list another dataset owns is never offered; import is
idempotent per version; keyboard cases (rule 13) with registry ids as a diff; axe in dark, light and GOV.UK.

**Exit.** Phase 9's exit; make ci and make test green offline; live cases under a named lease and stack; a
friction fragment. Report in Prompt L's format, then stop.
