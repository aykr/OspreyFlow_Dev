# Case lane · brief L3.1 · phase 5 as amended: one dataset per case, composites, the analyst layer

Written by the orchestrator, 6 November 2026 (step 0). Opus, medium. Size L. The riskiest lane: every
piece starts with its access and existence-leak tests, and the `lane-reviewer` reads it before merge.

**Binds.** `process/CLAUDE.md` rules 1–15 (rule 14 as ADR-142 rewords it; rules 3, 4, 6, 12 and 15
above all); ADR-143 (decision 1, decision 3 and "What is not reopened"); ADR-140 Amendment 7 (phase 5
held and rebuilt here); ADR-099 and its Amendments 3, 4, 8, 11, 12 and 13; ADR-140 R8 and decision 1;
ADR-126 (derived figures); `spec/ingest_studio_redesign/` and `BUILD_PLAN_INGEST_STUDIO.md`'s phase 5
(target model per dataset, reference lists, ADR-126 derived, one dataset per case, composites);
`spec/01_DOMAIN_MODEL.md`, `spec/03_CONDUIT_MIDDLEWARE.md` and `spec/04_VAULT_BACKEND.md` where they
touch datasets and the access step.

**Build.** Phase 5's scope, plus ADR-143 decision 1: each case owns exactly one dataset of kind
`analyst_layer` (beside `composite`), created with the case, named for it, of the case's unit, never
offered in any dataset list or the Studio's switcher, never chosen, never shared. A request under a case
reads its source dataset (or a composite's members) **plus** its layer, through the one access step
(`AccessFilter.gremlin_has_step`, `Principal.datasets`). `scripts.migrate_cases_to_one_dataset`, dry run
first (the dry run writes nothing), also creates each case's empty layer. Rewrite your slice of
`spec/01`, `spec/03` and `spec/04` in the same commits (rule 11).

**Tests first, named, each shown red by a plant of the real call site's shape:**
- graph-port conformance: a link from a loaded node written into case A's layer leaves that node's
  degree, `expand`, path length and histogram bucket **unchanged under case B** reading the same
  dataset (red with A's layer id added to B's principal);
- access: an analyst-layer dataset never appears in any dataset list or switcher, for any role;
  a principal outside the case is refused exactly as for a missing case (ADR-099 decision 5);
- the read set: a case's principal holds its source (or composite members) and its layer, and nothing
  else (red with the layer missing, and with a second case's layer added);
- the migration: the dry run writes nothing; the real run leaves every seeded case reading one dataset
  plus its layer; a case it cannot place is reported, not guessed;
- phase 5's own exit tests.

**Ask the owner first (stop that piece, carry on with the rest):** ADR-143 open question 1 — where the
analyst writes that exist today go (ADR-098 hand-marking, `manual_link`'s `SAME_AS`, accepted question
proposals, accepted extractions). The ADR recommends: analyst-originated ones into the layer, model and
pipeline output into the dataset. As multiple choice, recommendation first.

**Files.** The Case lane's ownership map; `packages/schemas/**` changes go through the orchestrator as
a small shared commit merged first (tell it what you need); ADR or amendment numbers are reserved by the
orchestrator before you write them. The dev stack (ArcadeDB, Postgres) only under the lease.

**Exit.** Phase 5's exit; ADR-143's "unchanged under case B" conformance case green on a leased stack
(name the lease); every seeded case reads one dataset plus its layer; the touched spec sections
rewritten; a friction fragment.

**Report** (Prompt L's format, also in `process/lanes/case/REPORT.md`): each exit criterion with its
proving test and the lease it ran under; the commits; requests to the orchestrator; questions for the
owner; one hand check (full commands and where to click, default and GOV.UK themes); whether anything of
yours is still running.
