# Studio lane · brief L1.5 · phase 8: expert steps

Written by the orchestrator, 8 November 2026, after L1.4's merge (`16a709e`), for a **fresh studio session**
on the orchestrator's account. Read `process/lanes/studio/REPORT.md` (L1.4) and ADR-140 Amendments 11 and 12
first. Rebase onto `main`. Opus, medium. Size L. After it comes L1.7. Studio-b (the sister lane) is building
L1.6, connectors, beside you: its files are the plan's studio-b row; ask the orchestrator before touching any.

**The lane, the stacks, the merge rule.** Studio's ownership map minus studio-b's; a test stack by
`stack_lease.sh acquire studio "<purpose>" && …` only; Prompt L's rules: never stop on a question (log it under
"Decisions taken"; only loosening access, real data or contradicting an accepted ADR stops a piece); schemas
changes ride with the step; before ready-to-merge, your own lane-reviewer, then make -k ci and make test at a
commit rebased onto main, saved under `process/lanes/studio/gates/`, with a leased live run including
`test_route_rights.py`. Expert steps run code a person writes, so this step gets the orchestrator's
independent review too.

**First, carried from L1.4's independent review (rule 3):** Test of a pipeline with **no** staging steps still
counts over masked rows. Give it the same two guards the staged path has, red at the real call site.

**Binds.** `process/CLAUDE.md` rules 1–15 (3, 5, 6, 8, 12 and 15 above all); ADR-140 (expert mode may declare a
sandboxed SELECT; rule 8); ADR-006 (no merge in storage); `spec/09_INGEST_STUDIO.md`; the redesign plan's
phase 8 and its exit.

**Build** (the plan's row L1.5, the redesign's phase 8):
1. **The `write_sql_transforms` right.**
2. **SQL transform:** a single SELECT over upstream node names, run by the Vault's DuckDB over staged Parquet
   in a sandbox (read-only, no file or network functions, a time and a memory limit, the person's own
   principal); the deploy gate refusing anything else or a SELECT that drops the `_ref` columns; a mandatory
   plain-words summary; disclosure in every run report.
3. **Fuzzy match:** left and right, the Splink-backed comparisons already in the product, a threshold that is
   part of the version, output columns plus `match_score`; it writes a scored, inferred `SAME_AS`, never a
   merge (rules 5 and 6), below-threshold rows kept and counted.
4. **YAML editing in expert mode** with the same gates.

**Tests first, each red by a plant at the real call site:** the sandbox refuses `read_csv`, `http`, a second
statement, a dropped `_ref`, and a query over another case's or dataset's staged table (rule 3); a fuzzy step
at two thresholds yields two versions and different counts; ADR-006's conformance cases still green (no merge
in storage); a SAME_AS it writes stays inferred until a person confirms (rule 5); keyboard cases (rule 13) with
registry ids as a diff; axe in dark, light and GOV.UK.

**Exit.** Phase 8's exit: the full prototype pipeline runs and its run report discloses both expert steps;
make ci and make test green offline; live cases under a named lease and stack; a friction fragment. Report in
Prompt L's format, then stop.
