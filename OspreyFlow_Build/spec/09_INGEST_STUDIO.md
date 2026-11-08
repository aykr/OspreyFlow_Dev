# 09 — The Ingest Studio

The capability that turns a file, a feed or a seized device into graph. It has a visual harness
because the mapping problem is genuinely visual, and because the people who know what a source
means are analysts and data officers, not the platform team.

Read `01_DOMAIN_MODEL.md` §1.1 first for POLE, and §7 for the Knowledge Adapters. This document
specifies the studio; `03_CONDUIT_MIDDLEWARE.md` §5 specifies the pipeline it drives.

## 0. The redesign under way (ADR-140, 5 November 2026)

The Studio is being rebuilt as a four-step studio — **Model**, **Sources**, **Pipelines**, **Runs** —
opened on a dataset, never a case, with a guided (no-code) and an expert (low-code) mode over one
pipeline. The decision is **ADR-140** (the owner's rulings R1–R9 and R12 of 4 November 2026 and R13,
R15–R17 of 5 November); operations and external orchestration are **ADR-141** (R10, R11, R14). The
design reference is the brief, `spec/ingest_studio_redesign/INGEST_STUDIO_REDESIGN_BRIEF_v2.md`, with
the clickable prototype `spec/ingest_studio_redesign/ingest_studio_prototype.html` and the wireframes
beside it; where the brief and ADR-140 differ, the ADR governs.

**How to read this document meanwhile.** §9 already states the rules as ADR-140 changed them. Every
other section describes the Studio **as built** and is rewritten in slices as each redesign phase
lands, as ADR-108's sections were. Where a section below conflicts with ADR-140 — the Studio working
within a case (§1), the domain-model node (§1, §1.1), the Connect gate on the first source (§2),
Verify and Publish as buttons (§5, §6), the schedule on Publish (§6) — it describes what runs today,
and ADR-140 describes what is being built.

## 1. The principle: the studio edits a recipe

The studio is an editor for a declarative **ingest recipe** — a YAML file. It is not a UI that
accumulates hidden state.

**It works within a case** (ADR-099 Amendment 4 decision 5): with no case open it says so rather than
calling routes that belong to one. A recipe or source file belongs to the first dataset of the case
it was made in, and is listed, verified, published and run only in cases reading that dataset
(Amendment 3 decision 3). The connector and transform catalogues stay global; they describe the
system, not a dataset's data.

This is the design decision everything else follows from. A recipe can be reviewed in a pull
request, diffed, copied between deployments, written by hand when that is faster, and produced
by the studio when it is not. An ingest configuration that exists only inside an application
database is one that nobody can audit and nobody can move.

```
            ┌─ source ─ profile ─ map ─┬─ load
domain model┤                          ├─ extract ─ load
            └─ source ─ profile ─ map ─┴─ enrich ─ load
```

**The recipe carries a pipeline graph — ADR-108.** Since phase B the Studio *is* a canvas: a typed,
acyclic graph of declared stages, not a wizard. Its node vocabulary is closed (rule 8 — every
transform remains a Knowledge Adapter with golden files, never an expression language):

- **domain model** — exactly one, the pipeline's root: the POLE core, or the core plus one domain
  pack (§1.1).
  - **Separate from the case's packs.** A pipeline's domain model is not a case's domain packs
    (ADR-126): a case can read several pipelines' data, and its packs are chosen by an Author. A
    pipeline's choice sets neither.
- **source** — a connector profile and a location. A pipeline may hold several; each runs as its
  own branch under its own `load_id`, so each stays independently revertible (§9.1 discipline).
  Every branch runs the recipe's one committed row template — per-branch templates are future work,
  disclosed in the run report by each branch naming the same recipe version. The **first** source
  carries the draft itself: its panel opens the Connect gate whole (§2 — file, connector, handling
  marking, legal basis). A further source's panel sets only its connector profile and location; it
  is read under the first source's marking and legal basis.
- **profile**, **map** — the stage editors of old (§3, §4). Choosing the node shows a short panel
  whose button ("Open profile", "Open map editor") replaces the canvas with the full editor;
  "← Back to the pipeline" returns to the canvas. Their routes, rules and tests are unchanged.
- **extract** — unstructured extraction over the Documents its upstream branches created, fed by a
  map and never by raw bytes. Its config declares the library (`stanza`, `spacy` or `transformers`
  run today; `model`/`whisper`/`vision` are refused at publish until the runner runs them), the
  media kind (text today), and where findings go — the **review queue** (the default; §7) or
  **inferred graph elements** written directly, both `inferred`, never asserted (rule 5; ruling Q1).
  Findings inherit the source document's handling and legal basis; marking **below** the source
  needs a mandatory written reason, is Author-gated at publish, and is counted loudly in the run
  report (ruling Q2).
- **enrich** — geocoding of the places its upstream branches created: the local gazetteer first
  (a scored, `inferred` `SAME_AS` edge — rule 6, never a merge), and online only through the
  deployment's configured allow-list (`OSPREY_ONLINE_GEOCODER`), every online call disclosed in the
  run report (ruling Q5). An online point lands in the analytics geometry partition and the node is
  superseded with its `geometry_ref` — a new revision, never an in-place edit.
- **load** — where a branch's rows become graph, through the engine unchanged. Its panel has no
  settings: it names the case dataset the rows are written into.

**Verify and Publish are not nodes.** They are the canvas header's two buttons, beside the
pipeline's name, version and status: Verify (§5) dry-runs the whole recipe, Publish (§6) commits it,
schedules it and runs it.

### 1.0 Working in the Studio (as built, 6 November 2026; ADR-140 Amendment 2)

The Studio (`apps/workspace/src/ingest/IngestStudio.tsx`) is **four places with one method**, in the
method's order — **1 Model**, **2 Sources**, **3 Pipelines**, **4 Runs** — under a **readiness strip**
(the target model, the number of registered sources with any file a pipeline reads that no source
registers named beside it (ADR-140 Amendment 6), the pipelines with how many drafts have not passed Test,
and the last run). It opens on **3 Pipelines**; the person picks the entry point (ruling R7).

- **The dataset switcher**, at the top, names the dataset the Studio works on. Until one dataset per case gives
  the Studio routes of its own (ADR-140 Amendment 7, ADR-143 decision 1), every Studio route is still a case's (ADR-099 Amendment 4 decision 5), so the
  switcher works *through a case* (ADR-140 Amendment 2, the owner's ruling "Dataset label, case behind"):
  it offers each dataset one of the person's cases **loads into** (its first, ADR-099 decision 6), and
  choosing one opens the case that loads into it — the current case when it does, else the case of the
  higher level first (`studio/datasets.ts`). A dataset a case only reads is not offered: through
  that case a load would go into another dataset than the label names. The line beside the switcher names
  the case the Studio is working through. Nothing is widened: the routes, roles and access checks are the
  case's, as before.
- **1 Model** shows the target model in words — the POLE core and the case's packs (ADR-126) — until
  the target model per dataset makes it the dataset's own (ADR-140 Amendment 7).
- **2 Sources** (ADR-140 Amendments 4 and 5) lists the dataset's **registered sources** — each a file
  registered once, with its marking, units, legal basis and refresh — and *Register a source* (Connection,
  File, Governance and refresh, then Register, after which its profile shows). A source's page has its
  profile (computed for the reader, never stored), its governance with an audited *Edit governance*
  (deployed pipelines reading it then need attention; drafts follow and must be tested again), its
  lineage, *Re-profile* and *Open in a pipeline*. The page's profile is masked by the source's own
marking: a pipeline that marks rows higher describes its elements, not the file, and a file holding
data above its source's marking is remedied by raising the source's (Amendment 6, the owner's ruling). Below, the unstructured path (*Add files*, ADR-094
  step 3). A pipeline's first source node chooses a registered source (*Use this source*), so no marking
  is asked in the pipeline; *The draft's own settings* keeps the deduplication key until the canvas becomes the editor (ADR-140).
- **3 Pipelines** is the pipelines home and canvas below: name a pipeline, open one, edit it beside its
  drawer (below; ADR-140 Amendment 8). The pipeline header's buttons are **Guided** and **Expert** (the mode),
  **Load rules** (§5a), **Test** (§5) and **Deploy** (§6), each opening in the drawer.
- **4 Runs** (`ingest/runs/RunsTab.tsx`) is the grid of deployed pipelines by day, read from the run
  ledger (ADR-110 decision 6): a cell per day — succeeded; *needs a person* (rows held, or a run failed,
  was refused or was blocked); scheduled, not yet run (today, with a schedule or watch set); skipped or
  missed; or no run — each named in words for a screen reader and coloured from the tokens. A cell opens
  that day's run reports; a run that held rows opens the held rows (Monitoring's panel, the same rights);
  a holder of `revert_loads` is shown each load's revert **as the operator's command**, never a button,
  since a revert runs with the Conduit stopped (ADR-127 Amendment 9; ADR-140 Amendment 2). *Pipeline to
  run or schedule* with **Run now or schedule** opens a deployed pipeline's run controls — **Run now**,
  the schedule editor and folder watch (ADR-110 decisions 5 and 7), pause and resume, and its runs — and
  *Schedules and folder watches* lists every deployed pipeline's.

**The words a person reads** (ADR-140 decision 2; `ingest/studio/vocabulary.ts`): a recipe is a
*pipeline*; Verify is **Test**; Publish is **Deploy as vN**, which commits a version and **neither runs
nor schedules it** (it carries whatever schedule the draft holds), with **Deploy and run now** beside it;
checks on load are **load rules**; *published* reads *deployed*, *flagged* reads *needs attention*,
*superseded* reads *previous version*. The Admin area's *Schedules and runs* is **Operations** (ADR-141).
Routes, YAML keys and stored statuses keep their names.

The pipelines home and canvas are as built on 11 October 2026:

- **Name a pipeline** and press *New pipeline*: a draft is created on the generic CSV connector with
  the canonical chain drawn, and opens on its canvas.
- **The list** is the case's recipe registry (`GET …/ingest/recipe-registry`) at every status but
  a previous version — each row "label · vN · status" with *Open*. A deployed pipeline stays here to be
  reopened; one needing attention (§6, ontology moved) to be deployed again. Listing drafts only lost a
  pipeline from the Studio the moment it was deployed (found live, 11 October 2026;
  `PipelineStudio.test.tsx` "keeps a published pipeline listed, and opens a recipe from before pipelines
  at Publish").
- **Open** puts a draft, or any recipe with a pipeline, on its canvas. A deployed recipe written before
  pipelines has no canvas of its own: it opens at Deploy, whose back returns home.

On the **canvas**, the *Pipeline stages* toolbar holds **+ Source** (a whole source → profile → map →
load branch), **+ Extract** and **+ Enrich** (each after the last map) and **Remove selected** (never
the domain root). Every edit is saved as it is made (`PUT …/ingest/recipes/{id}/pipeline`); the save
gate's refusals are shown above the canvas in its own words.

**The drawer and the two modes (as built 7 November 2026; ADR-140 Amendment 8, ADR-108 Amendment 6, ADR-140
decisions 3 and 14).** Choosing a step opens its editor in the **drawer** beside the pipeline
(`ingest/dag/NodeDrawer.tsx`); nothing replaces the pipeline, and no hosted screen has a "Back to the
pipeline" (the drawer's **Close** goes back to the step, or lets it go).

- **The drawer of a step** has two views. **Settings** is the step's editor: the domain pack (§1.1), the
  first source's registered source and *The draft's own settings* (the Connect gate whole, §2), a
  further source's connector and location, *Open profile*, *Open map editor*, the extract's library,
  media and where findings go, the enrich's geocoder, and the load's *Open load rules*. **Preview** is
  today's dry run up to that step, at the person's own clearance, writing nothing
  (`ingest/dag/NodePreview.tsx`): a source or profile step shows the rows it reads, from the Map sample
  rows, row 1 on until the last or ten rows, and says it is a sample of how many and whether the source
  has more; a Map or Load step shows the graph it would make, with its counts and rejected rows, from
  `POST …/ingest/recipes/{id}/preview-graph`: the dry run Test runs (§5), which **marks nothing**. The
  draft is not marked verified, no file is recorded for *Run now*, and the audit row is
  `preview_studio_recipe_graph`, never Test's. So a Preview never counts as Test and never satisfies
  Deploy (`tests/services/api/test_studio_preview_routes.py`; the first build called `verify` itself,
  found by the review of L1.2). An Extract or Enrich step says it has no preview yet. **Who may preview:**
  the table Preview reads the sample rows, so it needs `edit_pipelines` and viewer level on the case;
  the graph Preview needs what Test needs, `verify_pipelines` and editor level, and a person without
  the right is told so in words. The server's own masking is the Preview's, so a row the person may not
  read shows only its shape (ADR-140 rule 3; `tests/ingest/test_node_preview_access.py`). Until phase
  7's staging steps, nothing lies between a source and Map, so "up to that step" is the source's rows.
- **The pipeline's own screens** (*Load rules*, *Test*, *Deploy*, the profile and the draft's own
  settings) open in the same drawer, wider, each the existing screen hosted whole.
- **Guided and expert mode** (ADR-140 decision 3; Amendment 1.3). **Guided**, every person's default,
  shows the steps as a **numbered list** in the order they run, each opening the same drawer, beside a
  picture of the pipeline with nothing to press. **Expert** shows the canvas as the editor. A step
  guided mode does not offer (an expert step, once SQL transform and Fuzzy match are built, ADR-140 decisions 12 and 13) is listed, labelled "Expert step, read-only here"
  and opened read-only, never hidden, and guided mode's *Remove selected* refuses it. The mode is a per-person preference **kept in the person's browser**,
  keyed by their user name (`ingest/dag/studioMode.ts`; the owner's ruling Q1 a, 7 November 2026): with
  no preference store on the server, a second browser starts in guided mode again, and a browser that
  refuses storage stays guided. Everyone may switch to expert mode until `write_sql_transforms` exists
  (the owner's ruling Q3 a): the right gates the SQL and fuzzy steps once they are built (ADR-140 decisions 12 and 13).
  *Show YAML* is not yet built.
- **Map** opens the **Map editor** (`ingest/map/MapEditor.tsx`, §4): the pipeline collapses to a
  **strip** across the top, each other step a button, Map said as where the person is (not a button);
  a step on the strip goes back to the pipeline with that step chosen in its drawer.

**Two gates, both in words (rule 2).** Saving a pipeline refuses a graph that breaks the rules
(a cycle, a second domain root, a source reaching no load, an extract not fed by a map, an unknown
pack — `pipeline_rule_violations`); deploying refuses stage *configuration* the runner cannot run
(`pipeline_run_violations`): an unrunnable library or media kind, an unknown geocoder, a handling
override with no reason. Nothing is deployed and silently part-run.

**A v1 recipe is read as its canonical chain** — `domain model → source → profile → map → load` —
derived at read time and never stored back, so a recipe written by the old wizard is byte-for-byte
what it always was. The deployed YAML carries the pipeline, so a run is provably against exactly
what was deployed. The run of a pipeline answers a `PipelineRunReport`: every branch's own
`LoadReport`, every extract and enrich stage's own account, refusals included.

**Tests:** `IngestStudio.test.tsx` (the four places, the strip, the switcher, Sources),
`dag/PipelineStudio.test.tsx` (the drawer beside the pipeline, the two modes, an expert step read-only),
`dag/NodePreview.test.tsx` and `dag/studioMode.test.ts`, `tests/ingest/test_node_preview_access.py` (a
Preview never shows a row the reader may not read, shown red on both read paths),
`runs/RunsTab.test.tsx` and `runs/runsGrid.test.ts` (the grid, a report, held rows, the revert command
only for `revert_loads`), `studio/datasets.test.ts`, `publish/PublishScreen.test.tsx` "Deploy" (deploys
without running or scheduling; deploys and runs); keyboard `keyboard/ingest-studio.spec.ts` with
`INGEST_STUDIO_ACTIONS` (rule 13); the axe scan of `keyboard/ingest-studio-harness.html` in both themes
and GOV.UK, with Model, Sources, Runs, a report and its held rows, and, since ADR-140 Amendment 8, a step's drawer
in each mode, both Previews, Test, Deploy, an expert step and the Map editor with a column chosen.

### 1.1 Domain packs (ADR-108 phase D)

The domain-model node names the ontology overlay the pipeline is built against: the POLE core
(`pole`), or the core plus one pack — financial fraud and AML (`fibo`), justice and public safety
roles (`niem`, role-edges with validity intervals per ruling Q4, since ADR-117 incidents and
the custody links: shared cell, co-defendant, conflict and visit, and since ADR-120, pack version
3, establishments, the place links held at, part of, adjoins, used by and occurred at, the
throw-over incident category, and passes items to, which is Probabilistic and so never written by a
recipe), or cyber threat analytics (`stix`). A pack only ever *adds* entity and edge types or
widens an existing edge's ends (`extends: true`); a collision with the core is refused at load. The
catalogue is served by `GET /v1/ingest/packs` and offered in the Studio's domain panel.

A published recipe pins the version of every pack its pipeline names or that defines (not merely
widens) a type its row template writes (`pack_versions`, ADR-120 D10 and Amendment 1), beside
`ontology_version`. A pack bump flags every published recipe pinning that pack, as a core bump
flags every recipe; a recipe that names and writes no pack is unaffected. A recipe published
before ADR-120 is not flagged blind: it is stamped once with each pack's last version before that
record (NIEM 2, FIBO 1, STIX 1), so the NIEM bump to version 3 flags exactly the recipes naming
NIEM or writing its types.

## 2. Stage 1 — Connect

Connectors are **profiles**, following the same pattern as map providers (ADR-016): a validated
YAML file in `connectors/`, so adding a new carrier's CDR layout is a file rather than a release.

**A source file is read only from inside the ingest folder** (`OSPREY_INGEST_ROOT`), wherever its
location came from — the picker, an upload, the folder watch, or a location a client sends on a
draft or a run. The location is resolved (a `..` walk, a link to elsewhere) before it is judged,
and one outside the folder is refused before anything is opened, in words that neither name the
path nor depend on whether it exists (the security review, 18 October 2026: a pipeline author could
read any file the server could; `tests/services/api/test_source_confinement.py`). **And only one of
the recipe's own dataset's files** (ADR-099 Amendment 3): one directly in the folder or its
`uploaded/` folder (placed before that amendment, offered to every case), or in the dataset's own
folder under either, exactly the files the dataset's listing offers. Another dataset's file is refused
at Connect and at the pipeline's save, in words, and every read of a source (Profile, Map, a step's
sample, Test, Preview, a run and the hash *Run now* is held to) passes the same check for the
recipe's dataset, so a pipeline saved before the check cannot read one either (ADR-140 Amendment 12,
the orchestrator's review; `tests/services/api/test_studio_staging_routes.py`).

### Structured connector catalogue

| Group | Sources | Notes |
| --- | --- | --- |
| Communications | CDR and IPDR from carriers; subscriber and toll reports | One profile per carrier layout. Header and column variance is the norm, not the exception |
| Mobile device | Cellebrite UFDR, XRY, generic forensic report exports | Prefer CASE/UCO where a tool emits it — it is the interchange standard and saves a profile per tool version |
| Financial | Card transactions, bank statements, ISO 20022 (`camt`, `pain`), SWIFT MT, crypto exchange exports | |
| Vehicle and movement | ANPR, telematics, travel and border records | High volume; almost always the largest event table |
| Records | Custody, incident, intelligence and case management exports | Usually CSV or XML out of a records management system |
| Generic | CSV, TSV, JSON, JSONL, XML, Parquet, Excel, SQL table or view | The fallback that always works |

### Connections beyond files (ADR-140 Amendment 13, redesign phase 9, as built 8 November 2026)

An administrator names a **SQL**, **API** or **JSON** connection (*Admin › Connections*; `POST
/v1/admin/connections`). A connection holds its settings and **the name of its secret, never its
value**: the value is the deployment's, `OSPREY_CONNECTION_SECRET_<NAME>` in `deployment.env`, read only
when a read needs it and never stored, audited or answered.

- **SQL** (PostgreSQL): host, port, database, a login and its secret, TLS (`require` or `verify-full`;
  a server without TLS is refused). The login must be **read-only**: *Test connection* and every read
  refuse a superuser, a login owning a table, or one with a write privilege on any table it can see,
  and the read runs in a `READ ONLY` transaction. A source names a table or view and, optionally, its
  columns; never an expression (a sandboxed SELECT is expert mode's, L1.5).
- **API**: an HTTPS base URL, no sign-in or a bearer secret, and paging by `page` or by a next link
  named at a dotted path (which must keep the base URL's scheme, host and port). Its host must be on the deployment's
  egress allow-list, `OSPREY_CONNECTOR_EGRESS`, which only an operator sets.
- **JSON**: files in the dataset's folder whose names match a pattern, their records at a dotted path.

**Each read lands as the source's one file**, `uploaded/<dataset>/<source>.csv`, written to a
temporary name and renamed into place. Registration checks everything first, then reads once into a
new file (a name whose file exists is refused, never overwritten) and registers the source on it; a
refused registration takes the file back. From there it is a file source like any other: its folder
watch runs its deployed pipelines on each new read, a run keeps what it read as its load's raw rows,
and the watermark, the confinement and the rule gate apply as built. An incremental SQL source reads
only rows past its **cursor** (the highest watermark value it has read) and adds them to its file,
whose earlier rows may not have been loaded yet; a read that finds nothing leaves the file. Each run's
own watermark then reads only what that pipeline has not loaded. A read holding more than 500,000 rows, or an API giving more than
1,000 pages, is refused whole (rule 2). *Refresh now* on the source page reads again; a scheduled poll
of a SQL or API source waits on the poll floor (R17) and is not built.

### Unstructured sources

| Group | Formats |
| --- | --- |
| Documents | PDF, DOCX, RTF, TXT, EML and MSG, HTML |
| Images | JPEG, PNG, TIFF, HEIC, and scanned document images |
| Audio and video | WAV, MP3, M4A, MP4, and interview recordings |
| Archives | ZIP and tarballs, unpacked one level with each member treated on its own merits |

Connect asks three things regardless of source: where the data is, what the handling marking on
it is, and what the legal basis for processing it is. None can be answered later — a source loaded
without a handling marking cannot be safely exported, and a source loaded without a legal basis
cannot be defended. **The classification within the handling marking is the one part that may be
left blank (ADR-068, owner ruling of 3 October 2026): a blank classification is recorded as the
scheme's lowest level, `PUBLIC` for the UK scheme, and Connect says so beside the box.** The
server makes this true on both the create and the edit route, so a draft never carries an empty
marking whichever client wrote it. A blank marking is therefore the *least* protective one; that
was the owner's choice and is why Connect shows "Left blank: recorded as PUBLIC" rather than
saying nothing.

### Where the data is, for a rendered deployment — the ingest root

**Owner ruling R6, 27 September 2026.** "Where the data is" was, until this ruling, a path the
analyst had to already know and type, and in a rendered deployment there was no path that worked:
`POST /v1/ingest/recipes` (now `/v1/investigations/{id}/ingest/recipes`) takes a `source_location` the
*Conduit's own container* must be able to read, and nothing was mounted there — making eight acceptance rows (B1–B3, B6–B8, B13–B18)
unperformable through the analyst's own door, not because they were hard but because there was no
door.

The deployment therefore has a fourth storage root, `components.storage.ingest`
(`05_DEPLOYMENT.md` §2.1's Components screen, beside data, staging and backups), **bind-mounted
read-only into the Conduit for every profile**. Connect's "where the data is" is then a
*selection*, not a typed path:

```
GET /v1/investigations/{id}/ingest/source-files
```

- **Datasets (ADR-099 Amendment 3):** asked of a case. Besides the root and `uploaded/`, it lists the
  flat folder of each of the case's datasets, under the root (`<root>/<dataset>/`, an operator's
  drop) and under `uploaded/` (where an upload made in the case lands), each file marked with its
  dataset. The root's and `uploaded/`'s own files are those placed before the amendment, in no
  dataset; they are offered to every case, marked so, until an operator moves one into a dataset's
  folder (a raw file is not yet any dataset's data: what a load writes from it is stamped with the
  case's dataset). A dataset id that is not a plain folder name is never joined onto the root.
- **Authorisation:** `StudioRole.SOURCE_AUTHOR` — the same role that gates creating the draft the
  file will be attached to. Listing what you are about to point a draft at is that action one step
  earlier, so a principal who cannot create the draft has no use for the list.
- **Returns:** the files directly in the root, in `uploaded/`, and in each of the case's dataset
  folders (`<root>/<dataset>/`, `uploaded/<dataset>/`) — name, `source_location` (the container
  path), size and modified time, most recent first, each marked with its dataset or as in none.
- **Refuses:** anything outside the root (each entry is resolved *before* being compared against
  the resolved root, so a symlink pointing out of the mount is refused rather than offered),
  subdirectories, and dotfiles. A missing root is an empty list, not an error — Docker creates a
  bind-mount source that does not exist, so "the operator has not staged anything yet" is a normal
  state.

The analyst picks one and continues to Profile → Map on the existing canvas;
`ConnectDraftInput.source_location` is the chosen file's container path, so nothing about the rest
of the Studio changes. The mount of the root itself stays read-only: whatever puts evidence on the
host owns its contents.

**Upload from the analyst's computer (ADR-067, which amends R6; owner ruling of 3 October 2026,
"I need a file picker, not just the bar saying file path").** R6 deferred a browser upload past the
milestone. The owner has since asked for it, so Connect now has a **Choose file…** button that opens
the system's own file picker and uploads the chosen file:

```
POST /v1/investigations/{id}/ingest/source-files
```

- **Request:** the file's bytes as the raw request body (`application/octet-stream`), its name in the
  query string (`?name=`). Nothing is parsed as a form.
- **Authorisation:** `StudioRole.SOURCE_AUTHOR`, as for the listing, checked before a byte is read.
- **Where it lands:** `<ingest root>/uploaded/<dataset>/<name>`, the dataset being the case's first
  (ADR-099 Amendment 4 decision 4), under the one sub-folder the Conduit may write to.
  The renderer mounts it writable *over* the read-only root, so operator-placed evidence is still
  not writable. The listing shows both, the uploaded ones marked `uploaded`, and offers a file only
  under a name an upload would be accepted under (below): a file the operating system or a sync
  tool leaves in the folder, such as macOS's `Icon\r`, is not offered (found 9 October 2026).
- **Refuses (each with a sentence the Glass shows as it is):** a name with a folder part, a leading
  dot, a control character or more than 200 characters (400); an extension outside the list the
  connectors read (415); a name already present in the root or in `uploaded` — nothing is ever
  overwritten (409); an empty file (400); a file over `OSPREY_INGEST_MAX_UPLOAD_BYTES`, default
  512 MiB (413); an ingest folder the server cannot write, which is a deployment without the writable
  `uploaded/` mount (503, saying an operator must make it writable, not a bare server error). The size is counted as the body streams, so the limit stops the read; the declared
  length is checked first so an honest oversized upload is refused unread.
- **Written safely:** to a hidden part-file first, then linked into place only when complete, so a
  half-written file is never offered. A refused upload leaves nothing behind.
- **Audited:** `upload_ingest_source_file` with the name and the size, never the contents.

Typing a path or address stays available behind "Or type a path or address", for what a file
cannot cover (an `s3://` address, a developer's local path). Map's two recorded gaps (keyboard
binding, proposed templates) remain post-milestone.

## 3. Stage 2 — Profile

Automatic, and the studio does not let you map until it has run. For a structured source it
reads a sample — 10,000 rows or the whole file, whichever is smaller — and reports per column:

- Inferred type, and the confidence in that inference
- Null rate and distinct count
- Five sample values, **shape-masked** when the source's handling marking requires it
- **Pattern recognition against the Knowledge Adapters**: a column that looks like E.164 or a UK
  national number, an IMEI passing its check digit, an IBAN, a timestamp and its apparent
  timezone, a postcode, a British National Grid reference, an easting/northing pair
- Each share (a type's confidence, a pattern's match rate) is shown so that it never claims all or
  none when that is not so: 239 of 240 is "99.6%", not "100%", since the missing row is the one
  Verify will reject (found 9 October 2026)
- **Pattern matches are ranked by the evidence they carry, not the raw rate.** Each adapter
  declares a coincidence rate — of values with the right character shape, roughly how many it
  would accept anyway (`imsi` accepts any 15 digits: 1.0; a Luhn-checked adapter: 0.1) — and the
  order is by `match rate × (1 − coincidence rate)`. The displayed rate is never adjusted. Raw
  rate alone ranked `imsi 100%` above `imei 92%` on a column of IMEIs, so the first suggestion
  was the wrong identifier exactly when the data was good (found 9 October 2026; the test is
  `test_profiler.py::test_a_checksum_backed_match_outranks_a_shape_only_match`)

**What shape-masking means, since "redacted" was never defined.** At profiling time there is no
column-to-property mapping yet, so per-property sensitivity cannot apply — the only marking
available is the one set on the source at Connect. The rule is therefore source-level: a
principal cleared for the source's marking sees sample values in full; anyone else sees a mask.

The mask preserves **character class and position, never content**:

| Input character | Rendered as |
| --- | --- |
| Letter (Unicode-aware, not ASCII-only) | `A` |
| Digit (Unicode-aware) | `#` |
| Anything else | itself, literally |

`+44 7700 900461` → `+## #### ######` · `WILSON` → `AAAAAA` · `A2435AB` → `A####AA` ·
`2021-03-10` → `####-##-##`

Class preservation is the part that does the work. Masking every alphanumeric to a single symbol
renders `AB1234` and `123456` identically, which means the sample no longer shows a type
mismatch and the "spot a malformed column" claim quietly transfers onto the separate
`pattern_matches` field. Keeping letters and digits distinct puts that signal back in the sample
itself, where an analyst scanning a column will actually see it, and discloses nothing: `A####AA`
tells you the shape of a prison number without telling you whose.

Two limits, because a positional mask over free text leaks more than it looks:

- **Cap the mask at 32 characters** and append an ellipsis with the true length. A masked
  paragraph otherwise discloses word lengths and every punctuation mark in order, which for a
  short free-text field can be close to reading it.
- **For a column the profiler classes as free text**, show a character-class summary and a
  length distribution instead of a positional mask. Structure is the point of the mask, and free
  text has none worth showing.

Values are never simply hidden. A profiler that shows nothing cannot be checked, and an
unchecked mapping is how a source silently fragments the graph.

**Source-level masking and per-node access control are independent minimums.** This masking is
computed once, at profiling time, against the source's own handling marking set at Connect — it
is not the same check as the `AccessFilter` gate applied to a written node's own
`handling_classification`/`handling_code` once elements exist (§8, `01_DOMAIN_MODEL.md` §2.2). A
looser per-element `handling` override set later in Map never loosens what Profile already masked
here for a principal who could not clear the source: the sample was computed once, against the
source-level marking, and is not retroactively recomputed because one element ends up less
restrictive than the source default.

Pattern recognition is what makes the mapping stage fast. A CDR from an unfamiliar carrier
arrives and the profiler has already worked out that column 3 is an A-party MSISDN, column 7 is a
duration in seconds, and column 11 is a cell identifier. The analyst confirms rather than
constructs.

The profile also flags what will hurt later: mixed timestamp formats in one column, a timezone
that cannot be determined, an encoding that is not UTF-8, rows whose column count varies, and
apparent duplicate records. Each is shown with a count and a sample, and each becomes a decision
in the mapping stage rather than a silent default.

## 4. Stage 3 — Map

### The central problem

One source row rarely becomes one entity. A single CDR row produces two `Endpoint` nodes, an
`Event`, a `COMMUNICATED_WITH` edge and often two `Location` nodes for the cell sites. A form
that maps columns to fields cannot express that, and this is where most ingestion tooling fails.

So the mapping surface is a **row template**: a small graph that the analyst draws, describing
what one record becomes. The studio renders it with the same Sigma canvas used everywhere else,
so the template looks like the thing it will produce.

```
┌───────────────────────┬──────────────────────────────────────────┬──────────────────────┐
│ SOURCE FIELDS         │  ROW TEMPLATE — what one record becomes  │ INSPECTOR            │
│                       │                                          │                      │
│ ▸ a_party    MSISDN   │                                          │ Endpoint · A-party   │
│   07960112334  (98%)  │      ⬡ Endpoint ──COMMUNICATED_WITH──▶ ⬡  │ ──────────────────── │
│ ▸ b_party    MSISDN   │      A-party          ◆ Event          B  │ POLE class  Object   │
│   07468555891  (97%)  │         │              │                  │ Type        Endpoint │
│ ▸ start_time  datetime│         │              │                  │ Kind        msisdn   │
│   2014-03-11 19:42:01 │         └──USES?───┐   └──AT──▶ 📍        │                      │
│ ▸ duration    integer │                    │        Location      │ value_raw            │
│ ▸ direction   enum    │              (unmapped)     (cell site)   │   ← a_party          │
│ ▸ cell_id     string  │                                           │ value_normalised     │
│ ▸ imei        IMEI ⚠  │  [+ entity]  [+ link]                     │   msisdn(a_party)    │
│                       │                                           │                      │
│ ⚠ 3 fields unmapped   │                                           │ Match on             │
│                       │                                           │  ● value_normalised  │
│                       │                                           │ On match             │
│                       │                                           │  ● reference ○ create│
└───────────────────────┴──────────────────────────────────────────┴──────────────────────┘
      Row 1 of 10,000 sample    ◂ ▸                            [Save draft]
```

### Interaction

- **Drag a source field onto a template element** to bind it, **or choose both** (built under ADR-140 Amendment 8,
  7 November 2026, closing the gap this bullet disclosed). Each column in the source fields pane has a
  **Choose** button; a chosen column is outlined, says so, and stays chosen until it is bound or let go
  (**Let go**). While a column is chosen, every field binding in the inspector (a property's, a link's
  property, a link's *When it occurred*) offers **Bind ‹column› here**, named with what it binds
  ("Bind caller here: name"); **Enter** on it, or a click, binds the column through the same path a drop
  takes, and lets the column go. "Select both, Enter" is therefore: Enter on the column's *Choose*, then
  Enter on the binding's *Bind here*. A literal binding offers no *Bind here*. Bound columns are outlined
  and read "bound", never faded (an opacity put their words below 4.5:1, found by the first axe scan of Map with a column bound, ADR-140 Amendment 8).
  `keyboard/ingest-studio.spec.ts` "a column is bound in the Map editor by choosing it and the binding,
  then Enter" and `map/FieldBindingEditor.bind.test.tsx` prove it.
- **The profiler proposes a starting template** — *not built* (§2 records both as post-milestone).
  When built, every proposal is visibly a proposal until confirmed.
- **Map saves; it does not verify.** The editor's one action is *Save draft*; Test is the pipeline
  header's (§1.0), reached from the strip across the top (ADR-108 Amendment 6.1; ADR-140 Amendment 8).
- **A SAME_AS link's score** (brief §6.5) is not in the inspector: only a fuzzy match makes one, and
  the score column comes with it once Fuzzy match is built (ADR-140 decision 13; the owner's ruling Q2 a, 7 November 2026).
- **A link's time is chosen, never assumed.** *When it occurred* is **Not recorded** or **From a
  column**, and only a column chosen there is saved; the editor once displayed a default binding it
  never saved (found live, 11 October 2026; `ElementInspector.content.test.tsx`).
- **An entity offers its type's identifiers as well as its properties** (identifiers first, each once):
  a Device's IMEI is declared only as an identifier, and Map offered a Device nothing to set until
  9 October 2026.
- **An element's ref is its name in the recipe and can be changed.** Renaming an entity carries its
  links' ends with it; a ref another entity already holds is refused, since a link's end would
  then be ambiguous (a rename was silently dropped until 9 October 2026).
- **The Map canvas paints from the themed palette (ADR-070)** and redraws when the theme changes, so
  every element, label and link stands out from the canvas in either theme (a link's chosen start
  was painted the dark theme's text colour, and vanished in the light theme, until 9 October 2026).
- **The source fields pane names the registered source** the pipeline reads, and its version (ADR-140
  Amendment 6), or says that none reads the file. Its fields are the pipeline's own profile, never the
  source's: a pipeline may mark rows above its source (ADR-127 decision 3), and only its own profile
  masks for that (`MapEditor.source.test.tsx`, migrated from `MapScreen.source.test.tsx` under ADR-140 Amendment 8).
- **Unmapped fields are shown, always.** A field nobody mapped is either unimportant or the most
  important thing in the file, and silence is how the second case gets missed. Mark it
  `ignore` deliberately, with an optional note, or map it.
- **Scroll the sample.** The template is always shown bound to a real row, and the analyst can
  page through. Abstract mappings hide the case where row 4,000 has a null where row 1 did not.

### Per-element settings that carry the weight

**POLE first, then narrow.** Adding an element asks for the POLE class — Person, Object,
Location, Event, Organisation — then offers the concrete types under it. This is what makes the
studio usable by someone who knows policing data and not this schema.

**Match on, and on match.** Every entity template declares the identifier it matches on and what
to do when it matches: `reference` an existing node or `create` a new one. This is the single
most consequential setting in the studio and it is why entity resolution behaves. An `Endpoint`
matches on `value_normalised` and references; a `Person` from a witness statement matches on
nothing deterministic and creates, leaving Splink to link it later (`01_DOMAIN_MODEL.md` §4).

**A binding may take more than one column.** Some transforms are inherently multi-column — a
coordinate pair, an easting and northing, a separated date and time, a given name and family name
in two fields. A `FieldBinding` therefore accepts a list of source fields, and each adapter
declares the arity it expects; the studio offers only the columns that arity needs. Do not cap
the list at two: a British National Grid reference split across a letter pair and two numeric
columns is three, and the next format will be four.

**Transforms are Knowledge Adapters, not free expressions.** A field binding may pass through
`msisdn()`, `imei()`, `datetime(tz=...)`, `person_name()`, `address()`, `iban()` and the rest. A transform whose result is structured
is bound one part at a time, `person_name(part=family)` (ADR-104); Map offers each part, never the bare
transform, and a recipe naming none is refused when saved.
There is no scripting language in the studio. The moment you allow arbitrary expressions you have
created an unreviewable, untestable transformation layer that nobody can audit, and the usual
result is the same normalisation logic implemented four slightly different ways. If a source
needs a transform that does not exist, that is a new adapter with a golden test file, written
once and available to everyone.

The staging steps (§9) obey the same rule (ADR-140 Amendment 11). A Join's or a Lookup's
`normalise` names an adapter from the same registry, one that reads one column into one value of
text (`derive.text_adapters`: `msisdn`, `postcode`, `account_ref`…). It is never `split`, which gives
a list; nor a many-column adapter such as `grid_ref`; nor one whose result is structured
(`datetime`, `person_name`, `address`, `card`), which Map binds one part at a time. A Derive names
an operation from **Derive's catalogue** (`knowledge_adapters/derive.py`):

- `concat`;
- `split`: one part, by position, of what the `split` adapter gives, so Derive and Map never
  disagree about a cell;
- `substring`;
- `date_parse`: date order and zone declared;
- `arithmetic`: add, subtract, multiply or divide two columns, or a column and a constant. A sum,
  difference or product is exact or refused, never rounded. A quotient is given to 28 significant
  figures. A result past 1E±100 is refused;
- `case_when`: declared values to declared results;
- `normalise`: a text adapter, as above.

Each operation's settings are typed, and a key it does not read is refused, as is a wrong number of
columns. Each operation has a golden file under `tests/knowledge_adapters/golden/derive/` that shows
its refusals as well as its values. A refusal names the cause, never the cell's value. A setting or
a cell an operation cannot read rejects that row; it never stops the run. An operation outside the
catalogue is refused by the recipe's schema and by the adapter alike.

**Provenance and handling.** Set per source in stage 1 and overridable per element; a column can carry
the handling — a records-management export often has its own classification column — but not the
provenance, which is refused at Map save. Stage 1 declares which column carries each handling part
(`handling_columns`), so Profile masks a row by its own marking before Map exists; a Map binding
must name the declared column, and every entity and link the recipe writes, one matched by reference
included, must bind it. A column binds a
marking per element, part by part (classification, handling, action and sanitisation codes,
originator, owning unit). A row whose bound marking is looser than the element's default in any part,
names a code the scheme does not define, or names a unit the recipe does not declare (`units`) is
rejected with its cause; an empty cell takes the default (ADR-127 decision 3, Amendment 2;
`tests/ingest/test_handling_from_columns.py`). Everything loaded structurally is `asserted`;
everything derived by a model is `inferred`.

The engine's `_handling()`/`_provenance()` (`services/ingest/engine.py`) are pure — recipe
defaults and a row index in, a `Handling`/`Provenance` out, no open transaction required — which
is exactly what lets Map (and Verify, §5) show what an element's handling and provenance *would*
be before any write happens: `services/ingest/engine.preview_handling_and_provenance()` wraps
them for this purpose and is the one path both this stage's live preview and Verify's dry run
call, rather than each re-deriving it. The per-element override is built: `RecipeEntity` and
`RecipeEdge` carry `handling`/`provenance` overrides (`packages/schemas/ingest.py`), the write path
and the preview merge an element's override over `recipe.defaults` before validating
(`engine._merge_override`), and Map's element panel shows the override with its live preview
(`ElementInspector.tsx`). An override may only tighten the source's marking, never loosen it —
refused at save (`studio_map.validate_handling_tightens`).

**Conditional elements.** An element can be conditional on a field value, which is how one
recipe handles a file whose rows are not homogeneous — a device extraction where a row is a call,
a message or a contact depending on a type column.

### Content the model can read (ADR-094)

A link with a time can name the column holding its text: *Text the model can read* (none,
**message text** or **document text**) and *Column holding the text*, in the link's panel in Map.
The recipe records `content: {kind, field}` on the link. Each row's text is kept on that link's
event, never on the graph link, as the `excerpt` an Enron email carries: the whole text (ADR-095
decision 5; `truncated` stays on the event and is false), with `content_kind`. A link with no time has no events, so marking its
text is refused (`recipe_rule`). The marked column counts as mapped. The synthetic SMS export
(`carrier-a-sms.csv`, written by `scripts.seed_ingest_folder`) and its recipe
(`tests/scenarios/fixtures/sms_recipe.yaml`) are the demo of it. Tests:
`tests/ingest/test_message_content.py`, `ElementInspector.content.test.tsx`, `rowTemplate.test.ts`.

### Content an entity holds (ADR-094 step 2)

An entity row can name a column as *Content this holds*: **document text**, an **image file** or a
**video file**, the file named by a path relative to the export's own folder. A path that is absolute
or steps outside that folder, or a file of the wrong kind for what it is marked as, rejects the row;
a file that is not there is reported in the load report and the entity is loaded without it. The
text or file is kept in the deployment's media store (`ports/media.py`, `adapters/media_objectstore`),
never in the graph; a `Document` is written naming it (`media_kind`, `object_ref`, a title: the file's
name or the text's first words), one per file however many entities hold it, and each holder is
linked to it by `HOLDS`. A recipe that marks held content is refused at run if the run has no media
store. Tests: `tests/ingest/test_held_content.py`, `tests/conformance/media_store`.

**A `Document` holds its own text (ADR-127 decisions 1 and 2).** A `Document` entity row may name a
column as its own *document text*. The text goes to the media store and the `Document` itself carries
`object_ref` and `media_kind: text`: no second node and no `HOLDS`. Its title is a bound `title` if
there is one, otherwise the text's first words; its `object_ref` and `media_kind` cannot be bound. Because the `Document` is the row's own entity, every
link in the row can name it, so one report row gives the report and its `MENTIONED_IN` links from the
people, number and areas it names. A row whose text cell is empty is rejected, naming the field. A
`Document` holds only its own text: an image or video file on a `Document` entity is refused at Map
save. A `Document` matched by reference is not rewritten by the row. Every link must name an entity the
row declares: one naming an undeclared reference is refused at Map save and at run, while a declared
entity skipped on a row by its `when` condition simply has no links on that row. Tests:
`tests/ingest/test_document_holds_its_own_text.py`, `test_document_holds_its_own_text_live.py`.

### Files: the unstructured path, built for images, videos and text (ADR-094 step 3)

The studio's **Files** tab (beside *Pipelines*, shown once the studio has a case to load into) adds images, videos
and text files straight to that case, each a Document in the media store, read and extracted from
by its kind; the same dialog is reached from the canvas, standing alone (*Add files* under the strip
over the canvas) or held by a node (*Add files held by this…* in the menu of a node `HOLDS` allows).
Each upload needs a handling marking, offered from the deployment's own scheme and one the uploader
could read, and a legal basis, kept in the audit (§2: neither can be answered later). A file of
another kind, a holder `HOLDS` does not allow and a holder not in the view are refused before
anything is kept. `POST /v1/investigations/{id}/documents`. **Not built from §7's description:** the
extraction profile (which POLE classes, confidence floors, audio options) — extraction runs the fast
recogniser by default and the deployment's extraction model on request (ADR-098), over every
non-Document type — and PDF, DOCX and the other document formats,
which need a text reader this build does not have. Tests: `test_document_content.py`,
`test_document_upload_route.py`, `AddFiles.test.tsx`, `IngestStudioFiles.test.tsx`,
`keyboard/add-files.spec.ts`. The synthetic phone extraction (`demo_fixtures/phone_extraction.py`,
written by `scripts.seed_ingest_folder` with pictures drawn by ffmpeg and speech by macOS `say`) and
its recipe (`tests/scenarios/fixtures/phone_extraction_recipe.yaml`) are the demo of held content.

### A run stores its events

A recipe run from the studio writes its nodes and links to the graph and, once that commits, its
events (each timed link's occurrence, with any text it carries) to the analytics store, as every
seed's do. Until 5 October 2026 the run dropped them, so nothing loaded through the studio reached
the timeline, *Show messages* or extraction. Test: `tests/ingest/test_studio_run_events.py`.

Its places go to the analytics store the same way. A `Location` holds a `geometry_ref`, never its
coordinates (`03_CONDUIT_MIDDLEWARE.md` §5.1); after the run commits, each point a `geometry_ref`
binding gives is loaded into the geometry partition under that ref (version 1, the site grid's),
unless the ref is already there, marked with its entity's handling
(`services/ingest/geometries.py`). Until 9 October 2026 nothing wrote them, so a place loaded
through the studio carried a ref that resolved to nothing and was never on the map. A coordinate
pair needs its source's coordinate system, which the studio takes only from the connector
profile; `connectors/cell-site-csv.yaml` (`EPSG:4326`) is the first layout to declare one. Test:
`tests/ingest/test_studio_run_geometries.py`. Open: the existing refs are read back as the loader,
so a ref already loaded at a marking the loader cannot read is not seen, and its insert would
collide on the partition's key after the graph has committed.

### Which relationship types a recipe may write (ADR-081 step D)

A relationship the studio writes from the source's own records is **Direct**: a loaded record
stands behind it. Map refuses to save a recipe whose link names a Probabilistic type, `SAME_AS`
(the resolution engine's alone), `NOT_SAME_AS` (an analyst's judgement) or a type the ontology does
not have, with `422 recipe_rule` naming each problem, which Map shows in those words; the engine
refuses the same recipe again when it runs, before anything is written
(`services/ingest/recipe_rules.py`). A type an analyst proposed (ADR-090) may be named only once it
was promoted as Direct; one promoted as Probabilistic is refused, and a pending, rejected, withdrawn
or retired type is never accepted, checked at save and again at run (ADR-090 Amendment 1 decision 2,
ADR-081 Amendment 3). Tests: `tests/ingest/test_recipe_rules.py` and the Map save case
in `test_studio_map_routes.py`.

### The unstructured path is a different screen

Column mapping makes no sense for a PDF. For unstructured sources, stage 3 is an **extraction
profile**:

- Which POLE classes and concrete types to extract, as a checklist over the ontology.
- The schema handed to the model for constrained decoding, generated from that selection.
- Per-type confidence floor below which a candidate is discarded rather than queued.
- Which Knowledge Adapters run over extracted values — an extracted phone number normalises
  exactly like a structured one.
- For audio: language, whether to diarise, and whether speaker turns become candidate `Person`
  entities. They are always `unresolved` — a diarised speaker is a voice, not an identity.
- For images: OCR, scene description and object detection.

**Face matching and biometric identification are out of scope and are not a configuration
option.** They carry a legal basis, a governance regime and a public-confidence cost entirely
different from text extraction, and they are not something to inherit by default because a vision
model happens to be present. If a deployment needs them, that is a separate capability with its
own authorisation, not a checkbox in an extraction profile.

## 5. Stage 4 — Verify

A dry run over the sample that produces no persistent writes and three outputs.

**How the clearance scoping in §8 is actually enforced.** An `on_match: reference` lookup during
the dry run goes through the same `GraphPort.find_node` call the real write path uses
(`services/ingest/engine.py`'s `_write_entity`), passing the author's own `Principal` — never a
privileged or bypassing lookup. The lookup is also limited to the case's datasets, so a value held only by another dataset is
not found and a new node is made for it in this one (ADR-099 Amendment 1 decision 5). `GraphPort` is
where `AccessFilter` is injected — access control lives in the adapter, never
applied after retrieval, and an unauthorised principal must not be able to detect a filtered
node's existence via path length, degree count or histogram bucket — so this is what makes "an author cannot use a dry run to see material they could not
otherwise see" (§8) mechanically true rather than a convention someone could get wrong: the
author sees exactly what `AccessFilter` would return them on any other read, existence-leak
protections included. An element the recipe would `create` never touches `AccessFilter` at all —
it doesn't exist yet — and its previewed handling/provenance come from
`preview_handling_and_provenance()` (§4), not from a graph read.

**The graph it would make**, rendered in the ordinary canvas. This is the highest-value screen in
the studio: a wrong mapping is usually obvious at a glance and almost never obvious in a table.
Five hundred rows producing a thousand disconnected pairs means the `Endpoint` match setting is
wrong. A hairball around one node means a service number needs excluding.

**Counts.** Nodes and edges by type, how many referenced an existing node and how many created
one, how many rows were deduplicated, how many were rejected.

**The rejection report**, grouped by cause with samples: undeterminable timezone, a normaliser
failure, a required property absent, a value failing its ontology constraint. Rows are rejected,
never silently coerced. A run with rejections can be published — but the count is recorded
against the load and shown in the source's history, because an analyst looking at this data in
six months needs to know 4% of it never arrived.

**A value the ontology refuses rejects its row.** Each entity's and link's values are checked
against the types the ontology declares while the row is resolved, before the dry run simulates it
or the load writes it, so Verify and the load reject the same rows: *Person.date_of_birth is not a
valid date*, naming the property and its type, never the value. Until 9 October 2026 such a value
raised from deep in the dry run (Verify answered 500) or part-way through the load's transaction.
Whether a required property is present is not checked here, since an entity that references a
stored one may leave it out. Test: `tests/ingest/test_wrong_type_rejects_the_row.py`.

A cause names the adapter, the field and why ("msisdn: cannot normalise field 'a_party' — a phone
number has no letters in it"), never the value: the value is in the row's sample. So one cause is
one group however many values fail it, and for a principal not cleared for the source the samples
are shape-masked like every other value the run would create, column names kept (both found 9
October 2026, when the report quoted each bad value and listed rejected rows in full under a note
that values were masked).

**Verify must pass before publish.** Not "verify is recommended".

**Verify and Run read the same file (ADR-127 Amendment 47, build order step 30).** Verify reads the
files a run reads — each source branch's, a source node's own file before the recipe's
(`services/api/run_source.files_a_run_reads`, which the runner uses too) — and records each with the
SHA-256 of its bytes. *Run now* is held to that record: before anything is read into a store, a run
whose files are not those files byte for byte, or which names a file Verify did not check, is refused
(409 `source_changed_since_verify`) in words naming the files by their file names and asking for
Verify again; nothing is loaded. A version no Verify recorded (published before the rule, or by a
seed) runs as before; scheduled and watched runs read each new export by design (§6) and are not held
to it. Test: `tests/services/api/test_verify_and_run_read_one_file.py`.

**The alerts the sample would raise (ADR-133 decision 6, stage (d)).** Beside the rejection report,
Verify judges the sample with the pipeline's checks on load (§5a), each rule as its own author, as
the load would — and writes nothing: its alert store, quarantine and signature set refuse every call
(`services/api/load_checks.py`). It judges only the rows the person verifying may read in full, and
names only entities the sample shows them (rule 3). A check a dry run cannot judge — one reading
money movements or counting events, which a dry run does not make, or one reading links in the
stored graph — is listed with why, never left out. Test: `tests/services/api/test_load_checks.py`.

### 5a. Checks on load (ADR-133 decision 6, as built 1 November 2026)

Each pipeline has a "Checks on load" step. The data engineer chooses which load-time rules — the
case's, and the whole deployment's — apply to this source, and what a hit does here: **load with an
alert**, or **hold the rows** for a reviewer (before commit only; ADR-109 ruling 1). Engineers attach
rules; they do not write them: the step names rules by id, and writing a rule needs the analyst's
`keep_watches` right as well as `deploy_rules`. A whole-deployment rule applies to every pipeline and
cannot be left off one (the step may make it hold, never loosen one its author wrote to hold); a rule
just for its author is their own watch and is not offered. Until an engineer chooses, every case rule
judges the pipeline's loads, as before the step existed. The choice is kept per pipeline
(`recipe_load_checks`), audited, and read at each run, scheduled or not, and at a release of held rows.

## 6. Stage 5 — Publish

The recipe is written, versioned, and optionally scheduled.

```yaml
# recipes/cdr-carrier-a.yaml
id: cdr-carrier-a
version: 4
label: "Carrier A — call detail records"
connector: {profile: cdr-generic-csv, delimiter: ",", encoding: utf-8, header_rows: 1}
ontology_version: 17

defaults:
  provenance: {state: asserted}
  handling: {classification: OFFICIAL-SENSITIVE, handling_code: P, originator: unit-42}
  legal_basis: "RIPA s22 acquisition — authorisation 2026/0114"

deduplicate:
  key: [a_party, b_party, start_time_sec, duration, direction]

row_template:
  entities:
    - ref: a
      pole_class: object
      type: Endpoint
      match_on: value_normalised
      on_match: reference
      properties:
        value_raw: {field: a_party}
        value_normalised: {field: a_party, transform: msisdn}
        endpoint_kind: {literal: msisdn}
    - ref: b
      pole_class: object
      type: Endpoint
      match_on: value_normalised
      on_match: reference
      properties:
        value_raw: {field: b_party}
        value_normalised: {field: b_party, transform: msisdn}
        endpoint_kind: {literal: msisdn}
    - ref: cell
      pole_class: location
      type: Location
      match_on: cell_identifier
      on_match: reference
      when: {field: cell_id, is: not_null}
      properties:
        cell_identifier: {field: cell_id}
  edges:
    - type: COMMUNICATED_WITH
      from: a
      to: b
      temporal: {at: {field: start_time, transform: "datetime(tz=Europe/London)"}}
      properties:
        duration_s: {field: duration}
        direction: {field: direction, map: {I: inbound, O: outbound}}
    - type: PRESENT_AT
      from: a
      to: cell
      when: {field: cell_id, is: not_null}

unmapped_fields:
  - {field: imei, action: ignore, note: "Handset identifier not reliable in this feed"}

schedule: {cron: "0 6 * * *", watch: "s3://ingest/carrier-a/*.csv"}
```

Publishing writes the recipe to version control, not only to the database. The studio is the
editor; the repository is the record.

### After publish

- **Staged before it is graph.** Every resolved row is written to Parquet in object storage and
  read back before a single node or edge is written (`03_CONDUIT_MIDDLEWARE.md` §5.1). This is
  what makes a failed graph write retryable with no data loss, and what makes re-resolution
  possible without re-uploading the source file.
- **Re-runnable.** The same recipe against a new file, or the same file again — the deduplication
  key makes a re-run idempotent. A new file is loaded by a schedule or a folder watch, or by *Run now*
  once Verify has checked it (§5, "Verify and Run read the same file").
  A load's report counts what it made: *edges created* is the links it created, so a second call
  between the same two parties (merged into the first link) is not counted again, and a re-run of
  the same file reports none. It agrees with Verify's *would create* and with the store (the
  report once counted every edge write, 236 for 141 links, until 9 October 2026).
  **The run's events too, for a recipe with `deduplicate`** (ADR-109 Amendment 8): a re-run of the
  same file into the same case skips every row whose key the case kept (ADR-127 decision 5), so no
  event reaches the analytics store again and the timeline does not double
  (`tests/ingest/test_rerun_events.py`). A recipe **without** `deduplicate` loads every row every
  time: its links gain an occurrence and its events load again, together, so the timeline and the
  occurrence counts agree; it is not idempotent and says nothing otherwise.
- **Judged by the case's rules (ADR-109 ruling 1).** A run is judged by its case's typology rules
  at the point each declares (`03_CONDUIT_MIDDLEWARE.md` §3.8a, §5.1). The run report carries
  `rows_held` and `rule_notes`: what each rule raised, and any rows a failing pre-commit rule held
  for review — they reached no store, their places included. Publish's *Load result* shows both:
  "Rows held for review: N" and *What the case's rules did*, in the rules' own words (a fully held
  load once read as a load that made nothing; `PublishScreen.test.tsx`).
  **Held rows are decided in the Glass, not the Studio:** the Alerts place's *Held rows* tab
  (`02_GLASS_FRONTEND.md` §3.3) lists them, Editor and above, only rows whose marking the reader can
  read, each with the rule that could not judge it and why. **Release and load** needs the case
  Author level and the studio role Loader; released rows are loaded under a new load id with their
  provenance as it would have been, judged again by the rules, and never held again (the release is
  the human judgement a failing rule waited for — `fail_closed=False`). **Reject** needs the Author
  level and a written reason. Worked example, 11 October 2026: the onboarding pipeline's two rows
  were held because the run route never gave the rules the screening list; released after the fix
  (`364ba2e`), they were judged again and raised the three alerts the rules exist for.
- **Versioned, with loads attributed.** Every loaded element records which recipe version
  produced it (`load_id`/`recipe_id`/`recipe_version` on its audit stub — `01_DOMAIN_MODEL.md`
  §2.4). When a mapping error is found in month six, the affected elements are identifiable by
  query rather than by guesswork.
- **Ontology-aware.** An ontology change that invalidates a recipe flags it and blocks scheduled
  runs until someone opens it. Recipes never silently adapt.
- **Revertible.** A load is a unit. Revert is a function in `services/ingest` (`revert_load`),
  tested directly against a live `GraphPort`, not a CLI command — this build has no `osprey`
  unified CLI. It supersedes everything the load created, leaving the audit trail intact.
  Reverting a load is not yet reachable from the Admin area; it is a function call today, and gets
  its own screen there (the `revert_loads` right, ADR-112, already names who may).
- **Written once per link (ADR-058 Amendment 11; ADR-127 Amendment 19).** A run combines its rows' writes in
  the engine, one per link, and writes them through `upsert_edges` inside the run's one graph transaction, so
  ADR-109's pre-commit rules can still judge the load whole and roll it back. ADR-058 D2's bulk-load capability,
  which commits per chunk, stays the seeds' path (ADR-058 Amendment 10). A run without a handling scheme writes
  each link as it is held.

### The recipe registry, and how "flags the affected recipes" (above) actually happens

"Publishing writes the recipe to version control, not only to the database" already implies a
database record; this section gives it a shape. A Postgres-backed `studio_recipes` table (the
same Postgres instance the Conduit's audit stream already uses) tracks one row per recipe
version: `recipe_id`, `version`, `ontology_version`, `pack_versions` (ADR-120 D10), `label`, `status`
(`draft`/`published`/`flagged`/`superseded`), `content` (the in-progress recipe as JSON, populated
while `draft`), `git_path` (set once published), `owning_unit`, `created_by`, `published_by`,
`schedule_cron`/`schedule_watch`, `created_at`/`published_at`, and `dataset_id` (ADR-099 Amendment 3:
the first dataset of the case it was made in, kept by every new version; null for a recipe made
before, which stays readable in every case of its owner, Amendment 5).

- **A draft is a row, not client state.** Stage 3's "create and edit draft recipes" (§8) spans
  sessions and sometimes people — an author drafts, an approver publishes later — so a draft
  lives in `content` on a `status='draft'` row with no `git_path`, not only in the Glass's own
  working state. Publish serialises `content` to YAML, commits it to `recipes/<id>.yaml`, and
  flips the row to `status='published'`.
- **The reverse index this section's opening paragraph promises** — an ontology edit "flags the
  affected recipes and blocks their scheduled runs" — is a routine that runs whenever the ontology
  is reloaded: `UPDATE studio_recipes SET status='flagged' WHERE status='published' AND
  ontology_version != :current` (until ADR-120, the whole routine; the pack condition below now
  joins it in the same statement). This is what makes the flagging proactive (at the moment the
  ontology changes) rather than scanning every recipe file in the repository on every reload.
  Since ADR-120 D10 and its Amendment 1 the row also holds `pack_versions` (`JSONB`: the version of
  every pack the recipe names or that defines (not merely widens) a type it writes, stamped at
  publish, never an extra pin; an empty map for a recipe that names and writes none), and the same
  routine also flags a published recipe any of whose pinned pack versions differs from the loaded
  pack's. A row published before ADR-120 is stamped once at start-up (`reconcile_recipe_pins`,
  before the flagging) with the last version before that record of each pack it names or writes.
- **`StaleRecipeError`** (`services/ingest/engine.py`) is the separate, reactive last-line guard at
  actual run time — the registry is what surfaces the problem before someone tries to run a flagged
  recipe, not a replacement for the run-time check. A flagged Studio recipe is refused before it
  reaches the engine by `RecipeNotRunnableError` on every run path; the release of held rows checks
  clearance, not status, so there the engine's own checks are the guard (ADR-120 Amendment 2). Since
  ADR-120 D10 `StaleRecipeError` also refuses a recipe that names or writes a pack and is not
  pinned, pins it at a version other than the loaded pack's (an empty map, or a map without that
  pack, included), or names or writes a pack the ontology it is handed does not carry; any other pin
  is ignored. Only a real run is checked (`check_recipe_pins`): the dry run and the Verify and Map
  previews of an unpinned draft are not.
- **A re-commit carries the pins it was published with, and a run falls back to the row's.** A
  schedule change (the Publish screen's or the administrator's) re-commits a published recipe's YAML
  with the row's stored `pack_versions`, never recomputed against a newer pack, and with none if the
  row has none (for example one flagged before ADR-120); on a row with a mapping and no
  `ontology_version` it saves the schedule and does not re-commit. A run of a published recipe loads
  its committed file through `load_published_recipe`, which takes the row's pins when the file
  carries none (a file committed before ADR-120); pins in the file always win (ADR-120 Amendment 2).

### Scheduled runs (ADR-110, as built 13 October 2026)

**A source's refresh** (ADR-110 Amendments 6 and 7). A registered source with a
folder watch runs every deployed pipeline that reads it. Each pipeline takes each arriving file once,
recorded under the trigger `source_refresh`:
- it runs as the policy's owner, through the pipeline's case when that case loads into the dataset,
  else through a case of the owner's that does;
- it has the checks below, and its own watch is set aside;
- a pipeline needing attention is recorded *blocked*, and a keyless one *refused* in words;
- three refusals in a row pause the source's policy, not the pipeline.

**A full snapshot with *withdraw*** (ADR-110 Amendments 8, 9 and 15). Each kept row key records
what its row wrote, its events by id among it. The keys a snapshot no longer carries are its dropped
rows. **Only their own events** (their timeline and analytics rows) are withdrawn, by the ids their
keys record, and never another row's on the same link (Amendment 15, the owner's ruling "Only the
rows' events"). **The graph is never touched**: a dropped row's nodes and links stay, whether or not
another row still holds them, until its load is reverted. Whether a link or a node could go depended on other
cases' rows and loads, which the loader may not read, so whether it stayed or went would tell them
so (rule 3's hidden degree). The withdrawal asks only which of this pipeline's kept keys in the case
the snapshot no longer carries. The run says in words how many rows it withdrew, and how many
dropped rows were loaded before rows recorded the events they wrote and were left in place, their
events too; there is no fallback to their links' events. The run's metering counts no withdrawal.
What the withdrawal changes never depends on anything the loader may not read
(`tests/services/api/test_snapshot_withdrawal_tells_nothing_live.py`). A row that comes back matches
its nodes and merges into its own link, so it creates nothing. Reverting the refresh restores the
rows' events and their keys, and is refused while a row it withdrew has been loaded again; a refresh
recorded before Amendment 15, whose record lists withdrawn nodes and links, restores those too. A
pipeline reading more than one source cannot withdraw until the canvas becomes the editor (ADR-140).

A row that comes back merges into its own link, and that merge is the row's own (Amendment 16): its
load keeps the link as it was stored and its revert puts it back exactly, refused in words once the
link was written since. So the returning row's load, the refresh that withdrew it and the load that
first kept it revert in that order. Two limits stand (Amendment 15). A row dropped again after coming
back is left in place, its events too, in words, until the owner rules. And a failure to set the events aside after the record is in fails the run in words; the keys are
already aside, so the refresh's revert reconciles them. That path is not tested. A cross-case link
merge was examined in Part A2 and is not real on main, by its tests. A Studio load is stamped with
its case's dataset and its loader confined to it, through *Run now* and through the scheduler's slots
and its run now, so two cases each reading one dataset never share a link. A source refresh's run takes the same
path but is not driven by those tests. Two cases loading into one dataset share it by design
(ADR-102 Amendment 3), and read it alike. Until Part C, the stamp is the case's first dataset, not
the pipeline's own (Amendment 17).

**An incremental refresh** (ADR-110 Amendment 10). The source names a watermark column. Each load
records the highest value it read, and the next refresh by the same pipeline into the same case
reads only rows past the latest such value from a succeeded run that has not been reverted. Values
compare as numbers, as instants, or as text, settled by the first read; a later value that cannot be
compared that way refuses the run, naming its row. Rows at or below the watermark are not read and
are counted; rows with no value are read, counted, and kept from loading twice by their key. A load
is not reverted while a later refresh has read past it. A pipeline reading more than one source
cannot refresh incrementally until the canvas becomes the editor (ADR-140).

**On the source's page** (ADR-110 Amendment 13) the policy is said in words: when it reads, how each
file is read, whom it runs as, and whether it is paused and why. A person holding `schedule_pipelines`
pauses it, with a reason, and resumes it; neither is an edit of the source. **Moving the watches**
(Amendment 11): `scripts.migrate_sources` moves each pipeline's own folder watch onto the source it
reads, with its owner, its time and its pause, and leaves its cron on the pipeline; a source watched
under different patterns or for different owners, or read by a keyless pipeline, is left and named.

**What a run cost** (Amendment 12): every run records its wall time, the rows it read, the bytes it
put to the object store and the elements it wrote to the graph, on its report and in the ledger.
Rows staged and bytes to Parquet are *not measured* for a run without staging steps, and are said
so, never shown as 0. A staged load counts both (§9); they reach the run report when the Studio's
run route runs a staged pipeline. The run report, the Runs tab and Admin's run rows show them after
the counts, and withhold them where the counts are withheld.

A published recipe may run on a schedule. **The editor** (the Publish screen's *Schedule* panel)
offers every hour, every day, every weekday or every week at a time, in a named time zone (Europe/
London by default), or an advanced cron expression; before anything is saved the Conduit explains it
in words with its next five runs (`POST /v1/ingest/schedule-preview`), and a schedule it could not keep
— not five fields, an unknown zone, more often than every 15 minutes — is refused in words. **The
owner** is whoever last set the schedule (holding `schedule_pipelines`), and **the case** is the one it
was set in: a scheduled run acts as that person, through the case's datasets and rules, exactly as
their *Run now* there would (`run_recipe_as`, the one run path). **The executor** ticks each minute on
every replica; the replica that claims a slot runs it; after downtime only the latest due slot runs and
the others are recorded *missed*; a flagged recipe's slot is *blocked*; an owner who can no longer
sign in, no longer holds `schedule_pipelines`, is no longer an Editor of the case, or is cleared below
the source is *refused* in words, and three refusals in a row pause the schedule with the reason; a
slot due while the last run is still going is *skipped*. **Daylight saving**: a schedule naming its
hours runs a repeated October wall-clock time once; an hourly one runs both real hours; a missing March
time runs once at the end of the gap. **The run ledger** (`recipe_runs`) records every run, manual or
scheduled, and every slot that did not run, with the counts and the failure in words; the Publish
screen lists the recipe's runs, the Admin area's *Schedules and runs* every schedule, and the Reports
view's *Data feeds* the pipelines feeding the case — a run's counts withheld wherever the reader may not
view the source. **A folder watch** (ADR-110 decision 5, Amendment 4) runs the recipe on each new
file in its own dataset's folder whose name matches a pattern (`*.csv`): once the file has settled
for a minute, once per file (by name, size and modification time), one at a time, as the owner, with
the same checks; the run's trigger is `watch`. A refused or failed scheduled or watched run tells
its owner in words, on their alerts (decision 10).

## 7. The review queue — where unstructured material actually lands

Extraction produces candidates, not graph. The review queue is where a human turns one into the
other, and it is a first-class screen rather than an administrative afterthought.

```
┌────────────────────────────────────┬──────────────────────────────────────────────┐
│ SOURCE DOCUMENT                    │  CANDIDATES                                  │
│                                    │                                              │
│ …at approximately 03:20 on         │  ⬤ Person   "Owen WILSON"        0.94  [✓][✗]│
│ ⟦23/03/21⟧, ⟦I⟧ received a call    │  ⬤ Person   caller (unnamed)     0.61  [✓][✗]│
│ from the communications department │  ⬡ Endpoint (none extracted)                 │
│ stating that a male had phoned     │  ◆ Event    call to prison       0.88  [✓][✗]│
│ the prison to inform them that he  │  ◆ Event    alleged threat       0.72  [✓][✗]│
│ was being harassed by resident     │                                              │
│ ⟦Owen WILSON⟧ who was allegedly    │  Proposed links                              │
│ ringing the male constantly and    │  Owen WILSON ──ALLEGED_THREAT──▶ caller  0.70 │
│ threatening him to convey drugs    │                                              │
│ into the prison by throwing        │  ⚠ "caller" is unidentified. Accepting will  │
│ parcels over the wall.             │    create an unresolved Person node.         │
│                                    │                                              │
│ ⟦…⟧ = extracted span               │  [Accept selected]  [Reject all]  [Edit]     │
└────────────────────────────────────┴──────────────────────────────────────────────┘
```

The figures in the mock-up are a model's. Extraction runs the fast recogniser (Stanza) by default and
the deployment's extraction model only when asked (ADR-098 decisions 2 and 3); a recogniser finding
carries no confidence and reads *found by Stanza* in its place (Amendment 1 decision 3). Both kinds are
inferred until a person accepts them (rule 5), in the same list.

Rules, all of which follow from `01_DOMAIN_MODEL.md` §2.1:

- **No bulk accept above a confidence threshold.** Not as a default, not as a setting. The whole
  point of `inferred` is that a person decided. A queue of two thousand candidates is a resourcing
  problem, and the honest answer is a higher extraction confidence floor or a narrower extraction
  profile — not automatic promotion. **ADR-108 ruling Q1 adds one multi-id surface without touching
  this rule:** *Accept all pending* takes the explicit, enumerated ids a person reviewed on screen,
  as one decision — never a filter, a document-wide flag or a threshold — each finding still
  written `inferred`, each refusal answered per item, in words.
- **Accept, reject and edit are all recorded**, with the principal and the timestamp. Rejections
  are as informative as acceptances and feed the golden set.
- **Every candidate shows its span.** Clicking a candidate scrolls and highlights the supporting
  text, audio position or image region. A candidate with no locatable support is a defect in the
  extractor, not a judgement call for the analyst.
- **Rejected candidates are retained**, not deleted, so that a later re-extraction with a better
  model can be compared against what a human already declined.

## 8. Access control in the studio

Three roles, because the person who can define a mapping is usually not the person who should be
able to load material at any classification.

| Role | Can |
| --- | --- |
| Source author | Create and edit draft recipes, run verify against a sample |
| Source approver | Publish a recipe, schedule it, approve a mapping that changes an existing recipe's semantics |
| Loader | Run a published recipe against a file at or below their own clearance |

Verify runs against the sample under the author's own clearance, so an author cannot use a dry
run to see material they could not otherwise see (mechanism: §5). Every recipe publish, edit and
load is audited like any other action.

**A load is refused when the source is marked above the loader's clearance** (403
`source_above_clearance`, before anything is read or written). Verify may run below the source's
marking, masked; a load may not, because its `on_match: reference` lookups run at the loader's
clearance: a loader who cannot see an earlier load's elements cannot find them, and writes them
again (found 9 October 2026, when an OFFICIAL loader ran an OFFICIAL-SENSITIVE recipe twice and every
number was made twice).

**Rights, since ADR-112 (11 October 2026).** Studio routes now declare the *right* they need —
`edit_pipelines`, `verify_pipelines`, `publish_pipelines`, `schedule_pipelines`, `run_pipelines`,
`add_ingest_files`, `revert_loads`, `load_screening_lists` — through `require_right`, and
`require_studio_role` maps each Studio role to its right. The Data Engineer role holds all of them;
the Analyst role holds `add_ingest_files`; one right may be granted alone as the role
`right:<name>`. The three roles below are kept, each to the rights it already conferred
(`source_author` → edit, verify and add files; `source_approver` → publish and schedule; `loader` →
run), so no deployment loses access in the transition (`packages/schemas/rights.py`,
`LEGACY_ROLE_RIGHTS`). The Glass shows the Ingest Studio's rail entry only to an account holding
`edit_pipelines`. The paragraph below describes the mechanism as first built and still holds for
the legacy roles.

**Role vocabulary and enforcement.** The three roles are `StudioRole` values
(`packages/schemas/ingest.py`): `source_author`, `source_approver`, `loader`. They arrive the same
way `clearance`/`org_unit`/`receivable_handling_codes` already do — as a claim
(`services/api/auth.py`'s `CLAIM_ROLES = "roles"`) a deployment's IdP maps onto `Principal.roles`,
a plain list, so a principal may hold more than one role; nothing here implies exclusivity. Publish,
schedule and semantics-changing-edit routes are gated by a `require_studio_role(role)` FastAPI
dependency (`services/api/app.py`), following the same shape as the existing
`get_authorized_investigation`/`AuthorizedInvestigationDep` pair: it takes the resolved
`Principal`, raises `403` if the required role isn't in `principal.roles`, and is attached
per-route, e.g. `Depends(require_studio_role(StudioRole.SOURCE_APPROVER))` on publish. This is
role-based *action* authorisation, a different axis from `AccessFilter`'s per-record
clearance/handling gate (§5, which lives in the adapter and is never applied after retrieval) —
a source approver role does not itself grant
visibility into any material; it only permits the publish/schedule/approve action once the
recipe's own dry run has already passed under the author's clearance.

### 8.1 A retraction record — owner ruling R7, TENTATIVE, and not built

**R7 (27 September 2026, tentative — the owner is revisiting it after a usability walkthrough)
makes retraction two steps**: an analyst marks a node for suppression in the Glass
(`02_GLASS_FRONTEND.md` §9.5, built), and the suppression takes effect only when its evidence
arrives here — "a retraction record ingested and mapped to the node like any other source, so
every suppression is evidence-backed and auditable".

**This half is not built**, and it is worth saying why in this document rather than only in the
decision log, because the two obstacles are both *this section's* concerns:

1. **A recipe cannot currently change an existing record.** `services/ingest/engine.py` calls
   `upsert_nodes`, `upsert_edges` and `find_node` and nothing else — checked, not assumed. A
   publish that applies a suppression would be the first time ingest mutates what is already
   stored. §9 below does not forbid it, but its own "joining at ingest bakes a decision into
   storage" reasoning is close enough that this needs deciding rather than assuming.
2. **There is no retraction entity type.** R7 describes "an Event of a retraction type carrying
   the target node's identifier and the reason", and `packages/ontology/default.yaml` declares no
   such type, so this needs an ontology addition and an `ontology_version` bump — which every
   recipe, `apply_schema` call, conformance fixture and generated TypeScript type moves with.

**Until that decision is taken**, a suppression takes effect through
`POST /v1/investigations/{id}/nodes/{node_id}/retract` as it always has, and a mark is a proposal sitting beside it —
nothing in this section is wired to anything yet.

## 9. What the studio deliberately does not do

Rewritten 5 November 2026 for ADR-140 (rulings R4, R5, R13 and R15). **The guided staging steps'
engine is built** (ADR-140 Amendment 11), **and so are their drawers** (Amendment 12); the SQL
transform and the fuzzy match are not. Until a pipeline declares staging steps, its sources are
separate branches mapped row by row, as §1 describes.

**In the Studio** (Amendment 12). A step is a node of the pipeline: its id the step's, its config the
step's record. The recipe's `staging:` is built from the step nodes in run order when the pipeline is
saved and published, and the lines follow what the steps read (a line from each table a step reads,
and from the last step to Map, which no source then feeds). *+ Step* adds a step of the chosen kind,
reading the step or source chosen, and opens its drawer beside the pipeline: its record's own fields,
applied with *Apply step settings*, and beneath them a **live sample**, the steps up to that one over
the first ten rows of each source, at the reader's own clearance, writing nothing, with the save
gate's refusals in the gate's own words. A source table is named by its source node's id. The Map
editor of a staged pipeline maps the last step's table, its columns the profile of that table.

**A dataset's reference lists.** A Lookup reads the lists kept for its dataset whose ids the dataset's
live domain model names, each at the highest version kept, read from the list's version file below;
a list with no rows kept is refused in words. Until L1.6 builds import, rows are put there by
`python -m services.ingest.reference_list_import` from a synthetic test fixture only.

**The staging steps in the recipe** (`schemas/staging.py`). A recipe's `staging:` is a list of steps.
Each step has an `id` that later steps read it by, a `kind`, an optional `label`, and its own keys:

- `lookup`: `input`, `list`, `on`, `normalise` (optional) and `add`;
- `join`: `left`, `right`, `left_key`, `right_key`, `normalise` (optional), `how` (`inner` or
  `left`) and `add`;
- `filter`: `input` and `keep`, a list of conditions, each naming a `field` and exactly one of
  `is` (`null` or `not_null`), `equals` or `in`;
- `derive`: `input`, `column`, `operation`, `columns` and `settings` (each operation's own, §4);
- `union`: `inputs`, two or more;
- `dedupe`: `input` and `on`.

`add` lists the columns brought across, each `{column, as}`, with `as` optional. A step reads a
pipeline's source table by its name, or an earlier step by its `id`. **The last step is the table
Map reads.** Any other key is refused, so no step can carry an expression under a name of its own.
A recipe without `staging` is written exactly as before; `staging: []` is refused. YAML reads a bare
`on` as true, so `on:` is written quoted (`"on": estab_id`).

**What the save gate refuses** (`staging_rule_violations`):

- a step that reads a later step, or a table the pipeline does not have;
- a step that feeds nothing (every step but the last must feed a later one);
- a step whose `id` is a source's name;
- a key, or a Derive's `normalise`, read by anything but a text adapter (§4);
- a Lookup of a list the dataset cannot read. A dataset reads its own lists, and a
  **deployment-wide** screening list (one imported once for the deployment, whose own `dataset_id`
  is `deployment`) that it subscribes to **by the list's id** (Studio › Sources' *Screening lists*,
  ADR-140 Amendment 13; the lists a rule or Lookup is offered are exactly those this rule reads). Only the list's own record makes it
  deployment-wide. Another dataset's list is never readable, whatever its kind or name. A
  refusal uses the same words as for a list that does not exist, and a name two readable lists
  share is refused too.

A join must name both keys, and a Derive's settings and columns must be its operation's; the schema
refuses both. The gate runs before every staged run and every Test, which refuse the whole run if
it fails; a list handed to a run under a name that is not its own is refused there too. The
pipeline's save, a step's sample and publish ask it too (`studio_staging.staging_gate`), in the same
words, so nothing with steps is saved or published unjudged. Running a recipe with steps over a
single source's rows (`run_recipe` or `dry_run_recipe` without its staged rows) is refused. Only a
staged run may tell `run_recipe` not to stage raw rows.

**What a run does with rows.** Nothing is dropped silently:

- A Lookup keeps every row. A row with no match keeps empty cells and is counted.
- A Join gives one row per match. A left Join keeps an unmatched row; an inner Join counts it. A
  right-hand row that meets no left row (a blank key, or a key no left row holds) is counted. A key
  the adapter refuses is a rejection on either side, named by its side and its own source's row.
- A Filter counts what it leaves out. Its declared values are read trimmed, as the cells are.
- A Derive rejects a row its operation refuses, with the cause.
- A Union requires the same columns in its inputs.
- A Dedupe's first row stands for its repeats, carries their refs and counts them. A row with an
  empty key part has no key, as the engine's deduplicate reads it, so it stands alone and is
  never folded.

**A run reads each source by a load of its own**, `<the run's load>:<the source node's id>`, new for
every run, so no two runs share a raw file. Each step's table is written to staged Parquet, `<bucket>/loads/<load_id>/staged/<step>.parquet`,
with its refs as a `_refs` column; this is the only place a row's key is kept. Map reads the last
table back from what was written. Each source's rows, with a blank cell empty, are the raw rows of
**the load that read them**, `<bucket>/loads/<that load_id>/raw.parquet`. Each list a Lookup read
is kept at its version, `<bucket>/reference_lists/<the list's dataset>/<name>@v<version>.parquet`.
An element's ref, a source row's (source, `row <n>`, `load_id`) or a list row's, therefore names a
row of a file that exists. Both files are written once and never replaced: the same rows again
are no change, other rows are refused in words before anything is written, and a run refused by
its own checks writes neither. A staging rejection is listed in the load report as *staging step
<id> (<side> side, <source> row <n>): <cause>*, and a row Map refused as *staged table <table> row
<n>: <cause>*. Test and the load reject the same rows
(`services/ingest/staged_run.py`). A staged load reports as *rows read* the rows its sources gave.
It also counts the rows its steps staged and the bytes their Parquet took, for the run's metering
(`RunMetering.rows_staged`, `parquet_bytes`), and reports each step's counts (`staging_steps`, withheld
with the other counts) and each rejection's rows by table, row, load and side (`refs`), never by key.

- **No scripting in guided mode; a sandboxed SELECT in expert mode** (ADR-140: guided mode holds no expression or scripting language; expert mode may declare a sandboxed SELECT).
  Guided mode offers a closed catalogue of staging steps (Lookup, Join, Filter, Derive, Union,
  Dedupe), each declared in the recipe's YAML, and every operation in it is a Knowledge Adapter with
  golden tests (§4). Expert mode, for a person holding `write_sql_transforms`, may declare an SQL
  transform: a single SELECT over its upstream nodes, run by the Vault's DuckDB over the staged rows in
  a sandbox (read-only, no file or network functions, no other dataset's rows, a time and memory limit,
  the person's own principal), refused at publish if it is anything but one SELECT or if it drops the
  `_ref` columns, and listed in the run report with its rows in and out (ADR-140 decision 12).
- **Joins on declared keys in guided mode; SQL and fuzzy match in expert mode, with provenance,
  disclosure and safeguards.** A Join takes two upstream tables on an exact or normalised key, declared
  and never guessed. Every staged row carries `source_refs` — which input rows it came from, and
  their loads — into the element Map writes, so every link still shows where it came from (ADR-140
  decision 11).
  As built (Amendment 11), the refs are the element's `provenance.sources`, one `SourceRef` per input
  row: the source's name, `row <n>` and its `load_id`, which that load's `raw.parquet` resolves on
  the server. **No row key, raw or hashed, is carried** (rule 7: a key is low-entropy, so a hash of it
  is reversible); keys stay in the staged Parquet. A Join's element names both sides. A Lookup's
  names the list row it took values from, as `reference_list:<name>@v<version>` with no load id,
  which the list's rows kept at that version resolve. A **fuzzy match** decides a match at ingest
  only as a scored `SAME_AS` link marked
  `inferred`, never a merge; its threshold is part of the version; below-threshold rows are kept,
  unmatched and counted; a value Map binds from a matched column is `inferred`, with the match's score,
  until an analyst confirms the link (ADR-006 Amendment 1). Elements still meet existing nodes only
  through *match on* and *reference*; nothing is merged in storage (rule 6).
- **No aggregation at ingest, except an expert-mode SQL transform that carries its inputs' refs.**
  Load records at source fidelity, and aggregation is otherwise a query. An expert SQL transform may
  aggregate only when each output row carries the `_ref` of every input row it was computed from, so
  the element it becomes still names all of its sources (ruling R15); the publish gate refuses one that
  does not.
- **No enrichment from external services, except a geocoder the deployment allows.** No hosted
  lookup and no third-party enrichment API — with the one exception ADR-108 ruling Q5 made: an
  enrich node may geocode online, only through the deployment's configured allow-list
  (`OSPREY_ONLINE_GEOCODER`), the local gazetteer first, every online call disclosed in the run
  report (§1). Otherwise what goes in is what came in, plus locally computed normalisation.
