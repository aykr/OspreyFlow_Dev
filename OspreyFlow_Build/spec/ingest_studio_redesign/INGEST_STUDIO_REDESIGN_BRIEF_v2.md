# Ingest Studio redesign: a four-step, no/low-code ingestion studio

Design brief, **draft 2.2** · 4 November 2026 (supersedes draft 1: adds R8–R12, §2 as decided, §6.5 the Map editor, §6.6 refresh policy, §6.7 external orchestration, §7.1 Operations in the Admin area, and points §10 at `BUILD_PLAN_INGEST_STUDIO.md`) · prepared for the owner (Ayan) from a working session; written
to be complete in itself so it can be handed to a Claude Code session without anything "previously
supplied".

Beside this file: wireframes `wf1_model.svg` … `wf4_runs.svg` (and `.png`), the clickable prototype
`ingest_studio_prototype.html` (open it in a browser; it is the owner-approved feel of every screen), the phased
`BUILD_PLAN_INGEST_STUDIO.md`, and the paste-ready `CLAUDE_CODE_PROMPTS.md`.

---

## 0. The owner's rulings this brief rests on (4 November 2026)

Each of these was put to the owner as a choice and answered. Each changes a standing rule; the
rule it changes is named so the ADR can be amended rather than silently contradicted.

| # | Ruling | What it changes |
| --- | --- | --- |
| R1 | The Studio follows the steps a data engineer expects: **1 define the target model → 2 register source tables → 3 map sources to the model → 4 multi-stage transforms (joins, operations) organised as a DAG.** | Supersedes ADR-108's canvas-of-doors arrangement and the five-step wizard it wrapped. |
| R2 | **POLE stays the enforced baseline** of every target model. A model starts from an accelerator pack or blank POLE; a developer may extend it, and may define **lookup lists that act as reference tables**. | Keeps `01_DOMAIN_MODEL.md` §1.1; adds reference lists as a first-class model object. |
| R3 | **One target model per dataset.** The model is owned by the dataset; every pipeline loading that dataset maps into it; a case's packs follow from the datasets it reads. | Amends ADR-126 (packs were a case setting) and removes the pipeline's own domain-model node (ADR-108 §1). |
| R4 | **The staging layer may join and transform.** In guided mode, a closed catalogue of steps. In **expert mode a developer may write SQL-style transforms.** | Overturns `09_INGEST_STUDIO.md` §9 "no joins across sources at ingest" and, for expert mode only, "no scripting". |
| R5 | **Fuzzy joins are allowed in staging** (similarity match with a threshold). | Overturns ADR-006 for that step only; this brief adds the provenance, marking and undo that make it defensible (§5.4). |
| R6 | Two modes over the same pipeline: **guided (no-code)** and **expert (low-code)**. | New. |
| R7 | The three top-level concerns are **equals**, not a dbt-first or Airflow-first home; the user picks the entry point. | New. |
| R8 | **A case reads exactly one dataset; a dataset serves many cases.** A need to analyse several datasets together is met by a **composite dataset** (a declared union of member datasets, evaluated at read time), never by a case naming several. | Amends ADR-099 decisions 3 and 6; ADR-126 becomes derived. |
| R9 | **A source carries its own refresh policy** (trigger and mode); a refresh runs every pipeline that uses the source. | Moves ADR-110's folder watch and schedule to the source; adds incremental and full-snapshot modes. |
| R10 | **Two views of one run ledger.** The Studio's Runs tab is the engineer's view (when does my pipeline run, what happened); the Admin area's Operations view is the deployment's (what is being spent, on whom, is the scheduler keeping up), with metering, quotas and budget alerts. | New; extends ADR-110's run ledger with resource figures. |
| R12 | **A target model is draft or live.** Exactly one live version serves pipelines and cases; at most one draft is edited beside it; pipelines can be tested against the draft; *Make live* is the only step that changes what runs. | New; §4. |
| R11 | **External orchestration by thin clients, never by exporting the engine.** A pipeline's definition exports as a package (YAML + model version + lists + connector profile). Execution from Airflow, Prefect, Dagster or cron goes through OspreyFlow's run API via a generated DAG, a provider package or the CLI; the map-to-graph and the load always run inside OspreyFlow. | New ADR; no change to phases 0–9. |

Nothing below reopens the recipe-as-YAML principle (`09_INGEST_STUDIO.md` §1): the pipeline is still
a declarative, versioned, diffable file, and a run is provably against the version that was deployed.
Expert-mode SQL and fuzzy steps are *declared in* that YAML, not kept beside it.

---

## 1. Why the current Studio reads as confusing (diagnosis)

From `spec/09_INGEST_STUDIO.md`, `apps/workspace/src/ingest/` and the November captures.

1. **Two mental models are stacked.** The original five-step wizard (Connect → Profile → Map → Verify
   → Publish) had a DAG canvas put in front of it (ADR-108 phase B), but the canvas nodes are doors:
   Profile and Map show a small panel whose button *replaces the canvas* with a full-screen editor, and
   "← Back to the pipeline" returns. The canvas is a map of screens, not where work happens.
2. **The verbs are in the wrong places.** Verify and Publish are header buttons, not stages. Publish does
   three things (commit a version, set a schedule, run) and holds Run now, the schedule editor and the run
   ledger, so "where do I run it?" is answered "on Publish". Checks on load has a route but no node. Held
   rows are decided in the Glass.
3. **Too many nouns.** Recipe, pipeline, draft, source, branch, dataset, case, load, run, version,
   flagged, superseded. The Studio opens inside a *case* and a recipe belongs to "the first dataset of the
   case it was made in" (ADR-099 Amendment 3), a case-shaped route to a dataset-shaped thing.
4. **Governance is front-loaded.** The Connect gate asks for handling marking, lawful-sharing code, units
   and legal basis on the first source before the person has seen a row, and offers three ways to point
   at a file. Profile is then a forced gate before the one genuinely visual step, the row template.

**What is better than Airflow or dbt and is kept unchanged:** the recipe as YAML; the row template as a
drawn mini-graph of what one record becomes; Verify as a true dry run with a rendered preview; rows
rejected, never coerced; one transaction per run under a revertible `load_id`, each link written once;
every element stamped with the recipe version that made it; access control inside every store query
(ADR-099 / rule 3); checks on load; held rows released by a person; the review queue for extracted
findings; ontology changes flagging pipelines.

---

## 2. Datasets and cases (decided, R8)

A **dataset** is a named body of data held by a unit (ADR-099): every node and link carries the datasets it
belongs to; recipes, source files, saved patterns, watches and analyst-defined types belong to a dataset. It is
the unit of storage and of ingestion. A **case** (the Conduit's *investigation*) is a view onto a dataset held
by people: members and levels (ADR-052), the working set and its history, branches (ADR-084, ADR-124),
questions and kept answers, judgements, gaps, assumptions, link notes, reports and packs (ADR-111), the
case's rules and alerts. It holds no data. It is the unit of investigation and of access. All of that already
exists; the redesign changes only the boundary between the two.

**The rule.** A case reads exactly one dataset. A dataset serves any number of cases. A branch inherits its
parent's dataset. The Studio opens on a dataset, never a case.

**Composite datasets.** When an investigation needs two bodies of data together, an Author of the owning unit
declares a composite: a dataset whose members are other datasets, evaluated at read time as a filter over the
members' ids (every element already carries a list of datasets, ADR-099 decision 2), so nothing is copied and
the composite stays current as its members load. A composite has its own target model, which must be a
superset of its members' models (the POLE baseline makes the union well defined), a Model tab and a Runs tab
in the Studio, and no Sources or Pipelines of its own. Entity resolution across members writes its `SAME_AS`
links into the composite (today "a match across two datasets is in none", ADR-099 Amendment 2 item 3).
Cross-unit sharing becomes "a composite in unit B that names a dataset of unit A", granted by A; that grant
is designed in its own ADR and is not in this brief.

**What changes.**

1. Starting a case: "pick the dataset, name the case, invite the people". The fallback that minted a dataset
   named after a case (ADR-099 decision 3) is removed; datasets are made in the Studio or as composites.
2. `Principal.datasets` resolves to one id, or a composite's member ids. "Data added to a case joins its first
   dataset" (decision 6) becomes "joins its dataset".
3. ADR-126: a case's packs are derived from its dataset's target model; the setting becomes read-only.
4. Saved patterns, hotlists and monitors, today "the calling principal's own, of the case's datasets", become
   the case's (shared with the case team as alerts already are), with "promote to the dataset" for the ones an
   engineer wants every case to inherit. **Owner to confirm** (open question 3).
5. Migration: each existing case naming several datasets gets a composite of that set, by a
   `scripts.stamp_datasets`-style script, dry-run first.

## 3. The shape: four places, one method

The Studio has four top-level tabs, in the order the method goes, and a readiness strip that shows at a
glance where the dataset stands (model version, sources registered, pipelines tested/deployed, last run).

| Tab | Question it answers | Today's equivalent |
| --- | --- | --- |
| **1 Model** | What shape is the data in this dataset? | the pipeline's domain-model node + ADR-126 packs + nothing (reference lists are new) |
| **2 Sources** | What tables feed it, from where, under what marking? | Connect + Profile + the Files tab |
| **3 Pipelines** | How does each source become graph? | the canvas + Map + Verify + Publish's commit half |
| **4 Runs** | When does it run, and what happened? | Publish's schedule and run-ledger halves + Admin's *Schedules and runs* + Reports' *Data feeds* |

Vocabulary, old → new, applied everywhere (routes, YAML keys may keep their names for compatibility,
but every label a person reads changes):

| Today | New | Note |
| --- | --- | --- |
| recipe | **pipeline** | the YAML file is "the pipeline's definition" |
| domain model (node) | **target model** (owned by the dataset) | removed from the pipeline |
| Connect (stage) | **register a source** | once per source table, not per pipeline |
| Profile (stage) | **profile** (a property of a source) | automatic on registration; shown in the Map editor |
| Map (stage) | **Map** (a node) | unchanged in substance |
| Verify (button) | **Test** (whole pipeline) and **Preview** (one node) | both dry runs |
| Publish (button) | **Deploy as vN** | commits a version only |
| Run now / schedule (inside Publish) | **Runs** tab | |
| checks on load (step) | **Load rules** (on the Load node) | |
| flagged | **needs attention** | |
| superseded | **previous version** | |

Two modes (R6), one object. **Guided mode** shows a pipeline as a numbered list of steps with forms
and a read-only picture of the DAG; it offers only the closed step catalogue. **Expert mode** shows the
canvas as the editor, a *Show YAML* view with editing, and the expert-only steps (SQL transform, fuzzy
match). A pipeline edited in expert mode opens in guided mode with its expert steps shown read-only and
labelled. The mode is a per-person preference; the expert-only steps also need a right (§7).

---

## 4. Step 1 · Model (`wf1_model.svg`)

**What it is.** The target model of the dataset: POLE core (always on) + zero or more accelerator packs
(today's `pole`, `niem`, `fibo`, `stix`, renamed in the UI "Justice and public safety", "Financial crime
and AML", "Cyber threat") + the dataset's own extensions + its reference lists. Versioned; the current
version is what pipelines map into.

**Starting point.** A new dataset chooses: an accelerator pack, or blank (POLE core only), or "copy
another dataset's model". Packs only add types or widen an edge's ends (as today, `extends: true`); a
collision with the core is refused.

**Extensions (R2).** A developer may add, to this dataset only: a property, an identifier (with a pattern),
a link type; in expert mode, an entity type, which must sit under one of the four POLE classes. POLE
types cannot be removed or renamed. An extension is the same thing as today's analyst-proposed type
(ADR-090 / ADR-099 Amendment 3 decision 2): it belongs to the dataset, is usable in every case reading
it, and an administrator may promote it to the default dataset.

**Reference lists (R2, new).** A list is a small table with a declared key column, uploaded as CSV (or
read from a source table), versioned, belonging to the dataset. It is usable (a) in a staging **Lookup**
step, (b) as the value source of a property binding in Map ("Person.wing from list Wings"), and (c) if
marked *screening*, by the monitoring rules exactly as today's screening lists (`ListSchedule`). The
existing screening-list machinery becomes one kind of reference list rather than a separate object.

**Draft and live (R12).** A target model is in one of three states and the Model tab shows them side by
side: **live** (version N, the one every deployed pipeline and every case reads; exactly one at a time),
**draft** (version N+1, being edited; at most one at a time, owned by whoever opened it, visible to anyone
with the Studio role), and **previous** (every earlier version, read-only, kept for the elements that still
record it). Editing never touches the live version: the first edit opens the draft, every edit saves into the
draft, and the live model keeps serving until **Make live** is pressed. A pipeline can be **tested against the
draft** (a Test run names which model version it used), so an engineer can prepare the re-mapping for a model
change before the change goes live, and deploy the pipeline the moment it does. Discarding a draft leaves no
trace in the version history.

**Updating a model, step by step.**

1. Open the dataset's Model tab (needs `edit_target_model`); the first edit opens draft N+1 beside live N.
2. Make the change. Allowed, and additive by design: add a property or identifier (with a pattern), add a
   link type between POLE classes, add an accelerator pack (packs only add types or widen an edge's ends),
   add or re-version a reference list, and in expert mode add an entity type under one of the four POLE
   classes. Not offered: removing or renaming a POLE core type. An extension is **retired**, never deleted:
   it leaves the Map palette and new writes, and every element already carrying it stays intact and readable.
   A rename is "add the new, retire the old", so nothing is re-labelled behind an analyst's back.
3. Read the **impact** on the draft: which deployed pipelines write a changed or retired type (from the
   recipe registry), which cases read the dataset and will see new types in their palette and Reports, which
   pipelines use a changed reference list, whether a screening list will re-screen, and whether a composite
   that includes this dataset still has a covering model.
4. Optionally test the affected pipelines against the draft and prepare their new pipeline versions.
5. **Make live.** Draft N+1 becomes live; N becomes previous. Deployed pipelines pin the version they were
   deployed against; those writing a changed or retired type are marked *needs attention* and their schedules
   and refresh runs pause with that reason (today's `pack_versions` / `ontology_version` flagging, triggered by
   the dataset's model). Pipelines writing only unchanged types are untouched.
6. Bring the flagged pipelines forward: open, adjust the template (the new palette is live), Test, deploy as a
   new pipeline version pinned to N+1; that lifts *needs attention* and resumes the schedule. A pipeline
   already tested against the draft in step 4 deploys at once.
7. Loaded data is never rewritten: every element records the model version that made it. To carry a new
   property onto existing data, re-run the pipeline over its source (idempotent by dedupe key) or wait for its
   refresh. Retired types remain queryable in cases that hold them.
8. **Rolling back is a forward step:** "Revert to version N" opens a draft with N's content and goes live as
   N+2, so the history never loses a step and the same impact view applies.

A pack upgrade (NIEM v2 to v3) is the same flow: the pack's new version is a draft, and only pipelines writing
types the pack changed are flagged. A **composite** dataset's model must stay a superset of its members': when
a member goes live with a new type, the composite is marked *needs attention* until its own draft adopts the
change ("Adopt members' changes" on its Model tab) and is made live.

**Show YAML.** The model is a file too (the dataset's overlay), reviewable and portable like a pipeline.

---

## 5. Step 2 · Sources (`wf2_sources.svg`)

**What it is.** The catalogue of **source tables** feeding the dataset. A source is one table (or file
set, or endpoint) tied to a **connection**. It is registered once and carries, at the source level: its
profile, its handling marking and lawful-sharing code, the units its rows may name, its legal basis, and
its watch (if any). Every pipeline that uses it inherits those. This is the dbt `sources.yml` idea, and
it moves today's Connect gate out of the pipeline flow.

**Connections** (admin-managed, read-only credentials, in the Admin area): Files (the ingest root,
`OSPREY_INGEST_ROOT`, as today), **SQL database** (a read-only login; tables or, in expert mode, a query),
**API** (paged JSON over HTTPS, through the deployment's egress allow-list, disclosed in run reports),
**JSON schema** (files whose records follow a declared schema; a JSON path chooses the record set). Today
only the CSV connectors exist; the connector profile pattern (`connectors/`, ADR-016) is the extension
point and the brief does not change it.

**Registering a source (guided):** choose a connection → pick the table / file / endpoint → profile runs
automatically (today's profiler, unchanged: 10,000-row sample, types, null rate, distinct count, masked
samples, pattern recognition ranked by evidence) → set marking, units, legal basis and watch. Four short
screens. Expert mode adds a SQL query as the table, a JSON path, and a connection test.

**Source page.** Profile; governance; **lineage** (which pipelines use it, which target types they
write); *Re-profile*; *Edit governance* (audited); *Open in a pipeline*.

**Folder watch** moves here from Publish: it is a property of a file source ("run every pipeline that
uses this source when a new matching file settles"), with today's semantics (ADR-110 decision 5).

---

## 6. Steps 3 and 4 · Pipelines (`wf3_pipeline_canvas.svg`)

**What it is.** One pipeline = one DAG, left to right: **source tables → staging steps → Map → (Extract,
Enrich) → Load**. The canvas *is* the editor: choosing a node opens its editor in a drawer beside the
canvas, with a live sample of that node's output (first N rows), the way dbt's IDE previews a model.
Nothing replaces the canvas. The drawer is the same component in guided mode, reached from the numbered
list.

**Node vocabulary.**

| Node | Guided | Expert | What it is |
| --- | --- | --- | --- |
| Source table | yes | yes | a registered source (§5); a pipeline may hold several; each still runs under its own branch and `load_id` |
| **Lookup** | yes | yes | add columns from a reference list on a key |
| **Join** | yes | yes | join two upstream tables on an exact or **normalised** key (E.164, prisoner number, IBAN…, via the Knowledge Adapters); inner / left; the key is declared, never guessed |
| **Filter** | yes | yes | keep rows matching declared conditions |
| **Derive** | yes | yes | a new column from a catalogue of operations (concat, split, substring, date parse / zone, arithmetic, case/when, normalise-as-adapter) |
| **Union** | yes | yes | stack two tables with the same columns |
| **Dedupe** | yes | yes | drop repeats on declared columns (today's deduplication key, as a step) |
| **Fuzzy match** (R5) | read-only | yes | similarity match between two tables with a threshold; §5.4 |
| **SQL transform** (R4) | read-only | yes | a SELECT over upstream tables, run by DuckDB on the staged rows; §5.3 |
| **Map** | yes | yes | today's row template: what one staged row becomes in the target model |
| Extract, Enrich | yes | yes | unchanged (ADR-108), fed by Map |
| **Load** | yes | yes | the dataset, the **load rules** (today's checks on load), and the branch's dedupe key |

**Staging rows are first-class.** Each staging step's output is a table with a schema the next step
reads; the profiler runs on it like a source, so the Map editor's left pane shows the *staged* columns
with their patterns, not the raw file's. Staged rows are written to Parquet exactly as resolved rows are
today (`03_CONDUIT_MIDDLEWARE.md` §5.1), so a re-run can re-map without re-reading the source.

**Provenance through staging (required by R4 and R5).** Every staged row carries `source_refs`: for
each input table, the source row's identity (its dedupe key or row hash) and its `load_id`. A Join
carries both sides; a Union carries one; a SQL step carries the refs of every input row the engine can
attribute (DuckDB's `rowid` lineage is not available, so a SQL step must `SELECT` the upstream `_ref`
columns through, and the publish gate refuses one that drops them). The element Map creates records the
staged row's refs in its audit stub beside `recipe_version` (`01_DOMAIN_MODEL.md` §2.4), so "every link
shows where it came from" survives a join.

**5.3 SQL transform (expert; R4).** A SELECT statement over the names of its upstream nodes, executed by
the Vault's DuckDB over the staged Parquet, in a sandbox: read-only, no file or network functions, no
access to any other dataset's rows, a time and memory limit, the person's own principal (so a hidden
source row is not in the table at all, by ADR-099). The publish gate refuses anything but a single
SELECT and anything that drops the `_ref` columns. The run report lists each SQL step by name with its
row counts in and out. Guided mode shows the step read-only with its SQL and a plain-words summary the
author wrote (mandatory, like the handling-override reason).

**5.4 Fuzzy match (expert; R5).** Left and right tables, the columns compared, the method (the
Splink-backed comparisons already in the product: name similarity, shared normalised identifier,
date proximity), a threshold. Output: the left table plus the matched right columns, a `match_score`,
and the pair key. Three safeguards make it defensible:

1. **It writes a link, not a merge.** Map may use the matched columns, but the identity assertion itself
   is written as a scored `SAME_AS` link marked `inferred` (rule 5), with the score, the method and the
   version's threshold in its provenance, exactly as Splink's post-load resolution does. An analyst
   confirms or undoes it in the Glass. ADR-006's "never a merge in storage" therefore still holds in the
   store; what R5 allows is the *decision to match at ingest*, recorded as inferred.
2. **The threshold is part of the version.** Changing it is a new version; a run says which it used.
3. **Below-threshold rows are kept, unmatched, and counted.** The run report says "212 of 1,204
   matched ≥ 0.85"; nothing is dropped silently.

If the owner later wants a fuzzy join to *assert* identity (no SAME_AS, columns merged into one Person),
that is a separate ruling; this brief does not design it.

**Map (unchanged in substance).** The row template; drag a staged column onto an element; match on a
normalised value; on match reference or create; link time from a column or not recorded; unmapped
columns always shown. New: a property may bind to a reference list (§4).

**Test and Preview.** *Preview* on any node = today's dry run up to that node, shown as the node's
table (or, on Map and Load, as the graph it would make, today's highest-value screen). *Test* = the
whole pipeline: the graph, the counts, the rejection report, the alerts the sample would raise, plus
what each expert step disclosed. Test must pass before Deploy (as today: "not recommended, required").

**Deploy as vN.** Commits the version: the pipeline YAML (now carrying staging steps, SQL text, fuzzy
settings, load rules), pinned model version and pack versions. It does not run and does not schedule.
"Deploy and run now" is offered as a second button for the common case.

**Show YAML.** Always available; editable in expert mode with the same save and publish gates
(`pipeline_rule_violations`, `pipeline_run_violations`, in words, as today).

---

## 6.5 The Map editor (the row template as a three-pane screen)

Selecting the Map node collapses the pipeline to a clickable strip across the top (the pipeline is never lost)
and opens the row template beneath it; the drawer becomes the inspector. The prototype shows the exact feel.

- **Left: staged columns.** Every column of the last staging step's output, with its pattern and the value from
  the current sample row; bound columns outlined; the unmapped ones counted and named. A column is bound by
  dragging it onto an element, or by clicking it and then the element (keyboard path: select both, Enter).
  Unmapped columns are either mapped or marked *ignore* with a note, never left silent.
- **Middle: the template.** What one staged row becomes, drawn on the same Sigma canvas as the Glass: POLE
  entities as shapes (circle Person, diamond Event, hexagon Object, pin Location), links as arrows, inferred
  elements dashed. The palette is the dataset's target model; a type the model lacks is added on the Model tab,
  not here. The template is always shown bound to a real row; ◂ ▸ page the sample so row 4,000's null is seen.
- **Right: the inspector.** For an entity: class and type; bindings (property or identifier ← column, with
  the live value, removable); **match on** (an identifier or a normalised value); **on match** (reference the
  existing node, or create); and one sentence, "Row N would reference or create Person [name=…]". For a link:
  from → to; **when it occurred** (a column, or explicitly not recorded); for a `SAME_AS` from a fuzzy match,
  the score column and the note that it is inferred and never a merge.
- One Map per branch; branches meet in the graph through *match on* + *reference*, never through a join.
- *Show as YAML* on any element shows that the template is the recipe, nothing more.

## 6.6 Refresh policy (R9)

Set on the source at registration (wizard step "Governance and refresh") and editable on its page.

| Part | Choices | Notes |
| --- | --- | --- |
| Trigger | Files: folder watch (each new matching file once settled; ADR-110 decision 5) or manual. SQL / API: a schedule (ADR-110's editor: hourly, daily, weekday, weekly, cron, named zone, previewed in words) or a short poll, or manual. | The scheduler, its executor, run ledger and refusals are unchanged; the schedule's owner is whoever set it. |
| Mode (SQL, API) | **Incremental**: rows past a watermark column (`updated_at`, an increasing id); the highest value seen is kept per source. **Full snapshot**: the whole table each time. | The MoJ nightly nodes/edges overwrite is a full snapshot. |
| Rows that disappear (full snapshot only) | Keep what was loaded; or supersede the elements made only by the previous snapshot. | Nothing is deleted; superseding is reversible; the previous load's audit trail stays. |

A refresh is a run of every pipeline that uses the source, each under its own load id, judged by its load rules,
listed in Runs with trigger *source refresh*. The pipeline's dedupe key makes a re-read idempotent.

**Prerequisite, from the spec:** a re-run's *events* are written again to the analytics store (ADR-109
Amendment 1, "not fixed"), so the timeline double-counts a repeated file. Incremental and full-snapshot refresh
require that fix first; it is phase 1 of the build plan.

**Connections** are created in the wizard when none fits (step "Connection details": name, engine, host,
port, database, schema, read-only user, a password stored as a secret and never in a recipe, TLS, *Test
connection*), then owned by the Admin area. An API connection takes a base URL, an auth secret and pagination,
and asks for the host to be added to the egress allow-list.

## 6.7 External orchestration (R11)

Two exports, kept distinct.

**The definition: a pipeline package.** A zip of the pipeline YAML, the target-model version it was deployed
against, the reference lists it uses (by version), and the connector profile. Importable into another
OspreyFlow deployment, reviewable in a pull request, kept in the client's own Git. YAML round-trips; Python
does not.

**The execution: the orchestrator orchestrates, OspreyFlow executes.** The pipeline's meaning lives in the
Conduit and the Vault (adapters, ontology, access control in every query, handling, write-once per link under
a load id, load rules, audit), so nothing re-implements it outside. Instead the run API (`run_recipe_as`, run
status, run report, held-row counts) is versioned and hardened, and thin clients are generated from the Runs
tab:

| Shape | What is generated |
| --- | --- |
| Airflow DAG (Python) | `OspreyFlowRunPipelineOperator(dataset, pipeline, version)` plus a sensor that waits and fails on chosen thresholds (any held rows; rejections above n%) |
| Airflow provider package | `airflow-provider-ospreyflow`: operator, sensor, a connection type (URL + service credential); published and signed from the release pipeline like the images |
| Prefect task / Dagster asset | the same shape for those engines |
| CLI | `ospreyflow run <dataset> <pipeline> --version N --wait --fail-on held`, for cron and for the provider packages to call |

Rules that hold for every external trigger: the client authenticates as a **service identity** through the
deployment's OIDC (client credentials) and the run acts as that principal, so ADR-110's refusals apply (a
service identity that has lost its studio role, Editor level or clearance is refused in words); the external
run id (Airflow `dag_id`/`run_id`) is the **idempotency key**, so a retried task cannot load twice, and is
recorded in the run ledger as trigger `external`; a pipeline whose schedule is handed to an orchestrator is
marked **owned externally** so that nobody sets both; a generated DAG pins a deployed version or "latest
deployed", chosen at export. The same operator covers *data in*: the orchestrator lands a file in the ingest
root or a bucket the source reads, then triggers the source refresh. Staging SQL and fuzzy-match steps are not
exportable for external execution: they run in the Vault so that the sandbox, `_ref` provenance and the
person's principal apply.

## 7. Step 4 · Runs (`wf4_runs.svg`)

**The grid.** One row per deployed pipeline, one cell per run, by day (Airflow's grid view): succeeded,
needs a person (rows held or a refused scheduled run), scheduled-not-yet-run. Click a cell for the **run
report**: rows read; staged (after joins, with fuzzy match counts); created / referenced by type;
rejected (grouped by cause); held for review (with the rule); alerts raised; expert steps disclosed;
trigger, owner, duration. Buttons: *Open held rows* (today's Glass tab, now reachable from here with
the same rights: release needs Author + Loader, reject needs Author and a reason), *Rejection report*,
*Revert this load* (today's `revert_load` function, given its screen; `revert_loads` right).

**Run now ▾** picks a pipeline (and, for a file source, which file). **Schedules and watches** is
today's schedule editor (ADR-110: hourly / daily / weekday / weekly / cron, named zone, preview of the
next five runs, refusals in words) and the folder watches, listed per pipeline with the next run or
the pause reason. Nothing in ADR-110's executor changes.

**Data feeds** in the Reports view keeps reading the run ledger; this tab is the engineer's view of the
same ledger.

---

### 7.1 Operations in the Admin area (R10)

Today's Admin "Schedules and runs" becomes **Operations**: the deployment's view of the same run ledger the
Studio's Runs tab reads. Gauges, then controls.

**Metering, recorded on every run** (on the existing `PipelineRunReport`, so the engineer sees the cost of
their own pipeline too): wall time; rows read and staged; bytes written to Parquet and to the object store;
graph writes (nodes and links); DuckDB time and peak memory per SQL step; model calls, time and, for a
hosted engine on a sendable dataset, tokens per Extract step.

**Rolled up** by pipeline, dataset, unit and trigger (manual, schedule, watch, source refresh, external) per
day, with a trend, so a growing source or an over-frequent schedule is visible before it is a problem.

**Scheduler health:** slots skipped because the previous run was still going, missed after downtime, refused
by reason, paused schedules with their reason, and the queue depth when several sources refresh at once. The
executor already records every one of these outcomes; this is their screen.

**Storage:** the ingest root, the staging Parquet area, the object store and each dataset's share of the
graph, with growth over time, beside Admin → System's component health.

**Controls:** a deployment-wide concurrency limit on runs; per-dataset and per-unit quotas (runs per day,
rows per run, staged bytes) refused in plain words when hit; budget alerts on the admin's alerts before a
quota bites. The engineer's Runs tab shows the same quota as a bar on their pipeline, so a refusal is never a
surprise. External triggers are listed with their service identity and cost, since an Airflow-driven
deployment is where an admin most needs this view.

## 8. Access, modes and rights

- Studio roles stay (`StudioRole.SOURCE_AUTHOR`, Loader, …; `09_INGEST_STUDIO.md` §8). Registering a
  source is SOURCE_AUTHOR; editing a model is a new right `edit_target_model` (an Author of a case
  reading the dataset, or the dataset's owning unit's data engineer role); reference lists marked
  screening keep today's list rights.
- **Expert steps need a right** (`write_sql_transforms`), granted by an administrator, separate from
  the mode preference. Without it, expert mode shows the canvas and YAML but not SQL or fuzzy steps.
- A dry run, a preview and a SQL sandbox all read with the person's own principal: a row they may not
  read is absent, not masked (ADR-099). Sample values are shape-masked by marking as today.
- Every write stays within the Studio's dataset; the Load node cannot name another.

---

## 9. What changes in the spec and the ADRs

| Document | Change |
| --- | --- |
| `09_INGEST_STUDIO.md` | §1 principle kept; §1 node vocabulary extended with staging steps; §2 Connect becomes §5 Sources (per-source governance); §3 Profile becomes a source property; §5 Verify → Test/Preview; §6 Publish → Deploy, schedule and runs moved to Runs; **§9 rewritten**: "no joins across sources" → "joins on declared keys in guided mode; SQL and fuzzy match in expert mode, with provenance, disclosure and the safeguards of §5.3–5.4"; "no scripting" → "no scripting in guided mode; a sandboxed SELECT in expert mode". |
| ADR-006 | Amendment: a fuzzy-match staging step may decide a match at ingest, recorded as an inferred, scored `SAME_AS` link, never a merge; threshold versioned; below-threshold rows kept. |
| ADR-108 | Superseded in part: the canvas is the editor; the domain-model node is removed (the dataset's model); Verify/Publish buttons replaced by Test/Preview/Deploy. |
| ADR-126 | Amendment: a case's packs are derived from the target models of its datasets; the case setting becomes read-only. |
| ADR-099 Amendment 3 | Amendment: Studio recipes and source files belong to the dataset the Studio is open on, not "the first dataset of the case". |
| ADR-110 | Unchanged; its screens move to Runs and Sources. |
| `01_DOMAIN_MODEL.md` | New objects: `TargetModel` (dataset_id, version, packs, extensions), `ReferenceList` (dataset_id, key column, version, screening flag; absorbs `ListSchedule`), `SourceTable` (connection, location, profile, governance, watch), staging step records in the recipe schema, `source_refs` on the audit stub. |
| New ADR | "The Ingest Studio as a four-step studio" recording R1–R9 and this brief. |
| New ADR | "Operations and external orchestration" recording R10–R11 (phase 10). |

---

## 10. Build order

See `BUILD_PLAN_INGEST_STUDIO.md` beside this file: ten phases, each one Claude Code session or less, each
leaving the product working, with a paste-ready prompt per phase in `CLAUDE_CODE_PROMPTS.md`.

## 11. Open questions for the owner (not blocking phases 0–3)

1. Should a fuzzy match ever be allowed to *assert* identity (merge columns into one Person) rather than write
   an inferred SAME_AS? This brief says no.
2. Expert-mode SQL dialect: DuckDB SQL as-is (recommended), or a restricted subset?
3. Saved patterns, hotlists and monitors: move to the case (recommended, §2 item 4) or stay per dataset?
4. Guided mode the default for every new user, expert opt-in per person? (Recommended yes.)
5. Cross-unit composites: who grants, and is the grant per composite or per dataset? Its own ADR.
