# Build plan: the Ingest Studio redesign

4 November 2026 · for the owner · companion to `INGEST_STUDIO_REDESIGN_BRIEF_v2.md`.

Ten phases. Each is sized to fit **one Claude Code session** (or less), leaves the product working and
demonstrable on the Prison Intelligence Dataset, and can be the last phase done for a while. The order is
chosen so that the cheapest, most visible wins come first and the data-model changes come once the
screens around them exist. Sizes: **S** = half a session, **M** = one session, **L** = one long session
that may need a second to finish; the "effort" column follows the owner's practice of Opus at medium for
judgement rounds and Sonnet for mechanical ones.

Every phase obeys `process/CLAUDE.md` (rules 1–15): conformance and access tests first, nothing truncated
silently, access control in the adapter, inferred until confirmed, no merge in storage, British English,
no `Co-Authored-By` lines, the owner pushes. Where a phase changes a rule, phase 0 has already recorded
the owner's ruling as an ADR, so the session implements a decision rather than arguing one.

| # | Phase | Size | Effort | Leaves the product… |
| --- | --- | --- | --- | --- |
| 0 | Record the rulings: ADRs, spec edits, no code | S | Opus · medium | unchanged in code; the spec now says what is being built |
| 1 | Prerequisite fix: idempotent run events (ADR-109 Amendment 1) | S | Sonnet | re-runs no longer double the timeline |
| 2 | Vocabulary and navigation: four tabs, readiness strip, dataset switcher, Runs tab assembled from existing screens | M | Sonnet | the Studio reads as Model / Sources / Pipelines / Runs; nothing under the surface changes |
| 3 | Sources as first-class: `SourceTable`, per-source governance, the register wizard, connections | L | Opus · medium | Connect gate gone from pipelines; sources registered once |
| 4 | Refresh policy on the source: triggers, incremental and full-snapshot modes, source-refresh runs | M | Opus · medium | new data arrives by policy; Runs shows it |
| 5 | Target model per dataset, reference lists, ADR-126 derived; one dataset per case and composites | L | Opus · medium | the Model tab is real; cases read one dataset |
| 6 | The canvas as editor: drawer, Preview per node, Test, Deploy; the Map editor's three panes; guided mode's numbered list | L | Opus · medium | the pipeline screen matches the prototype |
| 7 | Staging, closed catalogue: Lookup, Join (keyed), Filter, Derive, Union, Dedupe; staged Parquet; `source_refs` provenance | L | Opus · medium | multi-table pipelines without code |
| 8 | Expert steps: SQL transform (sandbox, gates, disclosure), fuzzy match (scored SAME_AS), the right, YAML editing | L | Opus · medium | the owner's R4/R5 delivered with their safeguards |
| 9 | Connectors: SQL database, API, JSON schema; Admin area connections | M | Sonnet | sources beyond CSV |
| 10 | Operations and external orchestration: Admin Operations view (roll-ups, scheduler health, storage, quotas, budget alerts); run API hardened; CLI; Airflow provider and DAG export; external-trigger provenance | L | Opus · medium | an admin sees what the deployment spends; Airflow can drive a pipeline without leaving OspreyFlow's guarantees |

A week with a tight token budget: do phase 0 and phase 1 (both small), then phase 2. That alone removes
most of the confusion the redesign was asked for. Phases 3–10 can each wait for a fresh budget.

---

## Phase 0 · Record the rulings (S)

**Goal.** The spec says what will be built before any code changes, so every later session implements
rather than debates (rule 11; "never edit an ADR, append or write a new one").

**Do.**
1. Read `OspreyFlow_Build/Claude outputs/ingest_studio_redesign/INGEST_STUDIO_REDESIGN_BRIEF_v2.md` and
   `BUILD_PLAN_INGEST_STUDIO.md` (this file). Open the prototype only if a screen is unclear.
2. Find the next free ADR number in `spec/06_DECISIONS.md`.
3. Write **two new ADRs**: "The Ingest Studio as a four-step studio", recording rulings R1–R9 verbatim from
   the brief's §0, with the brief as its design reference, and listing the amendments below as its steps; and
   "Operations and external orchestration", recording R10–R11 (brief §6.7 and §7.1), marked accepted (design)
   and built in phases 4 and 10.
4. Append **amendments** (never edits) to: ADR-006 (fuzzy-match step writes an inferred scored `SAME_AS`,
   threshold versioned, below-threshold rows kept); ADR-099 (one dataset per case; composite datasets;
   decision 6 reworded; Amendment 3's "first dataset of the case" replaced by "the dataset the Studio is
   open on"); ADR-108 (superseded in part: canvas is the editor, domain-model node removed, Verify/Publish
   replaced by Test/Preview/Deploy); ADR-110 (schedule and folder watch become the source's refresh
   policy); ADR-126 (packs derived from the dataset's target model).
5. Edit `spec/09_INGEST_STUDIO.md`: a new §0 pointing at the ADR and the brief; §9 rewritten as the brief
   §9 says. Edit `process/CLAUDE.md` rule 8 to read: "No expression or scripting language in the Ingest
   Studio's guided mode. Expert mode may declare a sandboxed SELECT (ADR-<n>); transforms in guided mode
   remain Knowledge Adapters with golden test files."
6. Add a row to the friction log in `process/07_BUILD_PLAN.md`; commit (owner pushes).

**Exit.** `git diff --stat` touches only `spec/06_DECISIONS.md`, `spec/09_INGEST_STUDIO.md`,
`process/CLAUDE.md`, `process/07_BUILD_PLAN.md`. No code. The session's report lists both ADR numbers.

---

## Phase 1 · Idempotent run events (S)

**Goal.** A re-run of the same file must not double the timeline (ADR-109 Amendment 1, "not fixed").
Phase 4 depends on it.

**Do.** Write the failing test first: load a fixture twice through the run path and assert the analytics
store holds each transaction's event once (`load_events`). Fix at the class: key events by the pipeline's
dedupe identity (not by load id alone), so a second write of the same row's event is a no-op. Confirm the
typology rules still read one transaction once. Spec: amend ADR-109 (append), update
`03_CONDUIT_MIDDLEWARE.md` §5.1's event write.

**Exit.** The new test green; `tests/ingest/` and `tests/scenarios/` green; the run report's counts
unchanged for a first run and zero events added for a second.

---

## Phase 2 · Vocabulary and navigation (M)

**Goal.** The Studio reads as four places with one method, with no change to recipes, routes or stores.

**Do.**
1. `apps/workspace/src/ingest/IngestStudio.tsx`: four tabs **1 Model · 2 Sources · 3 Pipelines · 4 Runs**
   and the readiness strip (model version, source count, pipelines with untested drafts, last run). Model
   and Sources may be thin for now: Model shows the dataset's packs (read from the case/ADR-126 setting)
   and a "coming in phase 5" note; Sources lists today's source files (the Files tab) with their marking.
2. The top of the Studio is a **dataset switcher**, not a case switcher: list the datasets of the
   principal's unit on which they hold a studio role; opening the Studio from a case preselects that
   case's dataset. Recipes are listed by dataset (ADR-099 Amendment 3 already scopes them so).
3. **Runs tab** assembled from existing parts: the recipe run ledger (`recipe_runs`), the schedule editor
   and folder watch from the Publish screen, held rows (today's Glass tab, reached here with the same
   rights), *Run now* (today's run route), *Revert this load* behind the `revert_loads` right (the
   `revert_load` function gets its first screen). The grid: one row per deployed pipeline, one cell per
   day, teal/amber/grey as the prototype.
4. **Renames**, labels only (routes and YAML keys unchanged): recipe → pipeline; Verify → Test; Publish →
   Deploy as vN (Deploy no longer runs or schedules; "Deploy and run now" as a second button); checks on
   load → load rules; flagged → needs attention; superseded → previous version.
5. The Admin area's "Schedules and runs" is renamed **Operations** and keeps everything it shows today (every
   schedule in the deployment, owner, outcome, paused reason); its metering and controls come in phases 4 and 10.
6. Keyboard: every new control reachable, with its case in `keyboard.spec.ts` or the Studio's equivalent
   (rule 13); axe scans green on the new screens (both themes, GOV.UK where applied).

**Exit.** The Prison Intelligence demo's chapter 4 (run the reports pipeline) and chapter 9 (run the two
live pipelines, release held rows) walk end to end from the new tabs. `PipelineStudio.test.tsx` and
`PublishScreen.test.tsx` updated, green. Spec: `09_INGEST_STUDIO.md` §1.0 rewritten for the four tabs.

---

## Phase 3 · Sources as first-class (L)

**Goal.** A source table is registered once, carrying its profile, marking, units, legal basis and
connection; pipelines reference it and inherit those.

**Do.**
1. Domain: `SourceTable` (dataset_id, connection_id, location, profile, handling, units, legal basis,
   created_by, versions) in `01_DOMAIN_MODEL.md`; Postgres table and routes under
   `/v1/datasets/{id}/sources` (list, get, register, re-profile, edit governance, audited); access test on
   every route (rule 4). `Connection` records (type, name, admin-owned) with Files as the only type for now.
2. The **register wizard**: Connection → (Connection details, when new) → Table/file → Profile (automatic,
   today's profiler) → Governance and refresh. Back on every step. The refresh step records the policy
   (phase 4 executes it).
3. The Sources tab: table, source page (profile, governance, lineage from the recipe registry, *Open in a
   pipeline*, *Re-profile*, *Edit governance*).
4. Pipelines: a Source node names a `SourceTable`; the Connect gate's fields are removed from the pipeline
   and read from the source. Migration: each existing recipe's first-source settings become a `SourceTable`
   (`scripts.migrate_sources`, dry-run first); the recipe keeps working unchanged.
5. The Map editor's left pane reads the source's profile (prepares phase 6).

**Exit.** Registering `cell_stays` from the ingest root and using it in a new pipeline, with no marking
asked inside the pipeline; every existing recipe still runs; `test_source_confinement.py` still green
(the ingest root rule is unchanged).

---

## Phase 4 · Refresh policy (M)

**Goal.** New data arrives by the source's policy; every pipeline using the source runs.

**Do.** Policy on `SourceTable` (trigger: manual / folder watch / schedule; mode: incremental with a
watermark column, or full snapshot with keep / supersede). Move ADR-110's folder watch and schedule to
be driven by the source: a source refresh enqueues a run of each pipeline that uses it (same `run_recipe_as`
path, trigger `source_refresh`, the policy's owner as the acting person, the same refusals). Incremental:
the watermark kept per source, read in the connector's query. Full snapshot with *supersede*: elements
whose only load was the previous snapshot are superseded (revertible), never deleted. Runs grid shows the
trigger. **Metering (R10, part 1):** every run records wall time, rows read and staged, bytes written to
Parquet and the object store, and graph writes, on `PipelineRunReport` and in the ledger; the run report and the
Admin Operations list show them. Tests: a second snapshot with one row gone supersedes exactly that row's elements; an incremental
poll loads only rows past the watermark; a re-read is idempotent (phase 1).

**Exit.** The demo's PIN-call file re-read creates nothing new and doubles no events; a two-snapshot
fixture behaves as specified.

---

## Phase 5 · Target model per dataset; one dataset per case; composites (L)

**Goal.** R3 and R8.

**Do.**
1. `TargetModel` (dataset_id, version, **state: draft | live | previous**, packs, extensions, list refs) and
   `ReferenceList` (dataset_id, key column, version, screening flag; absorbs `ListSchedule`) in
   `01_DOMAIN_MODEL.md`; routes under the dataset (open draft, save draft, discard draft, impact, make live,
   revert-as-new-draft); exactly one live and at most one draft per dataset, enforced in the store; the Model
   tab as the prototype plus the draft/live split and the impact view (brief §4, R12). Extensions are retired,
   never deleted; POLE core types cannot be removed or renamed. A Test run may name the draft model version. A
   deployed pipeline pins the live version it was deployed against; *Make live* flags pipelines that write a
   changed or retired type (reuse today's `pack_versions` flagging) and pauses their schedules with the reason.
   Tests: a second draft is refused in words; editing never changes what a running pipeline reads; make-live
   flags exactly the pipelines that write a changed type; revert produces N+2, never rewrites N.
2. The pipeline's domain-model node removed; a v1 recipe reads its model from the dataset.
3. ADR-126 derived: the case's packs = its dataset's model's packs; the case setting read-only.
4. One dataset per case: `investigation_datasets` becomes one row; `Principal.datasets` resolves to one
   id or a composite's members; the case-creation screen "pick the dataset, name the case, invite"; the
   mint-a-dataset fallback removed. **Composite datasets**: `datasets.kind = composite`, `members`; the
   read filter over member ids; its own target model (superset check); Studio shows Model and Runs only;
   `same_as_writer` writes cross-member links into the composite.
5. Migration `scripts.migrate_cases_to_one_dataset` (dry-run first): a composite per distinct multi-set.
6. Access tests on every new read path; the existence-leak test for composites (rule 3).

**Exit.** Every seeded case reads one dataset; the Enron and Fixture Corp cases (if multi) read a
composite; search, suggest, paths and the query builder honour it; all conformance suites green.

---

## Phase 6 · The canvas as editor, and the Map editor (L)

**Goal.** The pipeline screen matches the prototype in both modes.

**Do.** The drawer beside the canvas (`PipelineCanvas.tsx` + a new `NodeDrawer`), never replacing it;
*Preview* on any node (today's dry run up to that node, shown as the node's table, or the graph on Map
and Load); *Test* for the whole pipeline (today's Verify); *Deploy as vN*. The **Map editor**: pipeline
strip, staged columns pane, template canvas (today's `MapScreen` canvas, kept), inspector with bindings,
match on, on match, link when, SAME_AS score; drag-to-bind and the keyboard path (select both, Enter:
closing a spec gap); unmapped columns always shown; ◂ ▸ sample paging. **Guided mode**: the numbered
list with the same drawers; expert steps read-only; the mode as a per-person preference. Keyboard cases
for every action (rule 13); axe green.

**Exit.** The Prison Intelligence reports pipeline can be built from scratch in guided mode by someone
following the demo script, and edited in expert mode; `MapScreen` tests migrated and green.

---

## Phase 7 · Staging, closed catalogue (L)

**Goal.** Multi-table pipelines without code.

**Do.** Step records in the recipe schema (`staging:` list; YAML keys named in the brief §6); engine
support for Lookup (reference list on key), Join (declared key, exact or adapter-normalised, left/inner),
Filter, Derive (catalogue of operations; no expressions), Union, Dedupe; each a Knowledge Adapter with
golden files (rule 8 as amended); staged rows to Parquet as resolved rows are today; the profiler on
staged tables; **`source_refs` provenance** on every staged row and into the audit stub of what Map
creates; the save gate's rules extended (a join must name a key; a step must be fed). Drawer editors for
each step with a live sample. Tests: golden files per step; a join's provenance survives to the node;
Test and the load reject the same rows.

**Exit.** The prototype's "Visits and contacts" pipeline, minus its two expert steps, builds and runs on
the synthetic data with every created element traceable to its source rows.

---

## Phase 8 · Expert steps (L)

**Goal.** R4 and R5 with their safeguards.

**Do.** The `write_sql_transforms` right. **SQL transform**: a single SELECT over upstream node names,
run by the Vault's DuckDB over staged Parquet in a sandbox (read-only, no file/network functions, a time
and memory limit, the person's own principal), the deploy gate refusing anything else or a SELECT that
drops the `_ref` columns, a mandatory plain-words summary, disclosure in every run report. **Fuzzy match**:
left/right, the Splink-backed comparisons already in the product, a threshold that is part of the
version, output columns plus `match_score`; what it writes is a scored, inferred `SAME_AS` (never a merge),
below-threshold rows kept and counted. YAML editing in expert mode with the same gates. Tests: the
sandbox refuses `read_csv`, `http`, a second statement, a dropped `_ref`; a fuzzy step at two thresholds
yields two versions and different counts; ADR-006's conformance cases still green (no merge in storage).

**Exit.** The full prototype pipeline runs; the run report discloses both expert steps.

---

## Phase 9 · Connectors (M)

**Goal.** Sources beyond CSV.

**Do.** `Connection` types SQL (read-only login, TLS, test connection; tables or an expert query),
API (base URL, auth secret, pagination, egress allow-list request), JSON schema (file pattern, JSON path);
secrets in the deployment's secret store, never in a recipe; the Admin area's Connections screen;
connector profiles in `connectors/` as today (ADR-016). The telco-lookup API and the NOMIS-replica SQL
source exist only as synthetic fixtures (rule 9): a fixture Postgres in the test stack and a fixture HTTP
server.

**Exit.** `visit_bookings` registered from the fixture Postgres with an incremental watermark; a refresh
loads only new rows.

---

## Phase 10 · Operations and external orchestration (L)

**Goal.** R10 and R11: the admin sees what the deployment spends and can cap it; an orchestrator can drive
a pipeline through the run API without taking the load out of OspreyFlow.

**Do.**
1. **Operations view** (`apps/workspace/src/admin/Operations.tsx`, from today's `Schedules.tsx`): the
   per-run metering of phase 4 rolled up by pipeline, dataset, unit and trigger per day with a trend;
   scheduler health (skipped, missed, refused by reason, paused with reason, queue depth, all already in the
   ledger); storage (ingest root, staging Parquet, object store, each dataset's share of the graph) beside
   Admin → System; external triggers listed with their service identity and cost. Add DuckDB time and peak
   memory per SQL step and model time/tokens per Extract step to the metering (phase 8's steps exist by now).
2. **Controls:** a deployment-wide concurrency limit; per-dataset and per-unit quotas (runs per day, rows per
   run, staged bytes) refused in plain words at the run path, so every trigger obeys them; budget alerts to
   the admin's alerts at a configurable share of a quota; the engineer's Runs tab shows the quota bar.
3. **Run API hardened and versioned:** start a run (pipeline, version or latest deployed, optional
   idempotency key), run status, run report, held-row counts; a service-identity OIDC client credential
   flow; the external run id recorded in the ledger as trigger `external` with its source; a pipeline
   marked *owned externally* when its schedule is exported.
4. **CLI:** `ospreyflow run <dataset> <pipeline> --version N --wait --fail-on held|rejections>n%`.
5. **Airflow provider package** `airflow-provider-ospreyflow` (operator, sensor, connection type), built,
   signed and published from the release pipeline like the images; **DAG export** from the Runs tab
   generating a three-line DAG against it; the Prefect task and Dagster asset as thin wrappers of the CLI.
6. **Pipeline package export/import** (YAML + model version + lists + connector profile) from the Pipelines
   tab; import refuses a package whose model version the dataset does not have.
7. Tests: a retried external trigger with the same idempotency key loads once; a service identity without
   the studio role is refused in words; a quota hit refuses the run and raises the alert; access tests on
   every Operations read path (an admin of one unit does not see another unit's figures unless deployment
   admin); the exported DAG runs against the test stack's fixture Airflow (or a recorded HTTP exchange if
   Airflow is not in the stack).

**Exit.** The Prison Intelligence reports pipeline runs from a generated Airflow DAG against the dev
stack, appears in Runs as `external`, and its cost appears in Operations; a per-dataset quota set to one
run per day refuses the second run in words.
