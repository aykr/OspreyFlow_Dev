# Studio lane · brief L1.3 · phase 7a: the staging catalogue's engine

Written by the orchestrator, 8 November 2026, for a **fresh studio session** on account `sol` (ADR-142
Amendment 3). The previous session's last step, L1.2b, is merged (`1fb38ba`): Phase 6's exit is met.
Read its report (`process/lanes/studio/REPORT.md`), including what it recorded but did not resolve (a new
pipeline pins no pack, where the seeded draft pins niem 3, because it has no domain-model step). Rebase
onto `main` first. Opus, medium. Size L.

**Binds.** `process/CLAUDE.md` rules 1–15 (1, 3, 8, 9, 12 and 15 above all); ADR-140 and its Amendments
7–10 (Amendment 9 decision 3: screening lists as reference lists); ADR-141; `spec/09_INGEST_STUDIO.md`;
`spec/ingest_studio_redesign/` and `BUILD_PLAN_INGEST_STUDIO.md`'s phase 7.

**Build** (the plan's row L1.3): the staging catalogue's engine: Knowledge Adapters, golden files,
staged Parquet and `source_refs`; it carries reference lists of kind `screening` (ADR-140 Amendment 9
decision 3). The engine only: no screen in this step (L1.4 builds the drawers).

**Tests first, each shown red:** golden files per step; provenance survives a Join (red with
`source_refs` dropped at the join); a screening list round-trips through the catalogue; a guided-mode
transform stays a Knowledge Adapter with its golden file (rule 8), never an expression.

**Exit.** Phase 7a's exit as the redesign's plan states it, and the row's; fixtures synthetic and
in-repo (rule 9); any live case under a named lease and stack (`stack_lease.sh acquire studio
"<purpose>"`, a or b; pin the ports it prints); a friction fragment. Report in Prompt L's format, then
stop.
