# 09 — The Ingest Studio

The capability that turns a file, a feed or a seized device into graph. It has a visual harness
because the mapping problem is genuinely visual, and because the people who know what a source
means are analysts and data officers, not the platform team.

Read `01_DOMAIN_MODEL.md` §1.1 first for POLE, and §7 for the Knowledge Adapters. This document
specifies the studio; `03_CONDUIT_MIDDLEWARE.md` §5 specifies the pipeline it drives.

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
Connect ──► Profile ──► Map ──► Verify ──► Publish
   │           │          │        │          │
   │           │          │        │          └─ versioned recipe, optionally scheduled
   │           │          │        └─ dry run on a sample; see the actual graph
   │           │          └─ the row template: what each record becomes
   │           └─ automatic; what is in this source and what shape is it
   └─ pick a connector, point at the data
```

The five stages are navigable in any order once a source is connected. Nobody gets a mapping
right first time, and a wizard that will not let you go back gets abandoned.

## 2. Stage 1 — Connect

Connectors are **profiles**, following the same pattern as map providers (ADR-016): a validated
YAML file in `connectors/`, so adding a new carrier's CDR layout is a file rather than a release.

### Structured connector catalogue

| Group | Sources | Notes |
| --- | --- | --- |
| Communications | CDR and IPDR from carriers; subscriber and toll reports | One profile per carrier layout. Header and column variance is the norm, not the exception |
| Mobile device | Cellebrite UFDR, XRY, generic forensic report exports | Prefer CASE/UCO where a tool emits it — it is the interchange standard and saves a profile per tool version |
| Financial | Card transactions, bank statements, ISO 20022 (`camt`, `pain`), SWIFT MT, crypto exchange exports | |
| Vehicle and movement | ANPR, telematics, travel and border records | High volume; almost always the largest event table |
| Records | Custody, incident, intelligence and case management exports | Usually CSV or XML out of a records management system |
| Generic | CSV, TSV, JSON, JSONL, XML, Parquet, Excel, SQL table or view | The fallback that always works |

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
      Row 1 of 10,000 sample    ◂ ▸        [Verify mapping]    [Save draft]
```

### Interaction

- **Drag a source field onto a template element** to bind it, or select both and press Enter —
  the keyboard path is not an afterthought, because this screen is used for hours at a time.
- **The profiler proposes a starting template.** For a recognised source shape it proposes the
  whole thing; for an unfamiliar one it proposes the bindings it is confident about and leaves
  the rest. Every proposal is visibly a proposal until confirmed.
- **An element's ref is its name in the recipe and can be changed.** Renaming an entity carries its
  links' ends with it; a ref another entity already holds is refused, since a link's end would
  then be ambiguous (a rename was silently dropped until 9 October 2026).
- **The Map canvas paints from the themed palette (ADR-070)** and redraws when the theme changes, so
  every element, label and link stands out from the canvas in either theme (a link's chosen start
  was painted the dark theme's text colour, and vanished in the light theme, until 9 October 2026).
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
`msisdn()`, `imei()`, `datetime(tz=...)`, `person_name()`, `address()`, `iban()` and the rest.
There is no scripting language in the studio. The moment you allow arbitrary expressions you have
created an unreviewable, untestable transformation layer that nobody can audit, and the usual
result is the same normalisation logic implemented four slightly different ways. If a source
needs a transform that does not exist, that is a new adapter with a golden test file, written
once and available to everyone.

**Provenance and handling.** Set per source in stage 1, overridable per element, and a column can
carry either — a records-management export often has its own classification column. Everything
loaded structurally is `asserted`; everything derived by a model is `inferred`.

The engine's `_handling()`/`_provenance()` (`services/ingest/engine.py`) are pure — recipe
defaults and a row index in, a `Handling`/`Provenance` out, no open transaction required — which
is exactly what lets Map (and Verify, §5) show what an element's handling and provenance *would*
be before any write happens: `services/ingest/engine.preview_handling_and_provenance()` wraps
them for this purpose and is the one path both this stage's live preview and Verify's dry run
call, rather than each re-deriving it. The per-element override this paragraph promises is not
yet a field on `RecipeEntity`/`RecipeEdge` — building it is this stage's own scope: add
`handling`/`provenance` override fields to both, and have the write path (and the preview call
above) merge an element's override over `recipe.defaults` before validating, rather than using
the recipe-level default unconditionally as it does today.

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

### Files: the unstructured path, built for images, videos and text (ADR-094 step 3)

The studio's **Files** stage (shown once the studio has a case to load into) adds images, videos
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

A cause names the adapter, the field and why ("msisdn: cannot normalise field 'a_party' — a phone
number has no letters in it"), never the value: the value is in the row's sample. So one cause is
one group however many values fail it, and for a principal not cleared for the source the samples
are shape-masked like every other value the run would create, column names kept (both found 9
October 2026, when the report quoted each bad value and listed rejected rows in full under a note
that values were masked).

**Verify must pass before publish.** Not "verify is recommended".

## 6. Stage 5 — Publish

The recipe is written, versioned, and optionally scheduled.

```yaml
# recipes/cdr-carrier-a.yaml
id: cdr-carrier-a
version: 4
label: "Carrier A — call detail records"
connector: {profile: cdr-generic-csv, delimiter: ",", encoding: utf-8, header_rows: 1}
ontology_version: 12

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
  key makes a re-run idempotent.
  A load's report counts what it made: *edges created* is the links it created, so a second call
  between the same two parties (merged into the first link) is not counted again, and a re-run of
  the same file reports none. It agrees with Verify's *would create* and with the store (the
  report once counted every edge write, 236 for 141 links, until 9 October 2026).
- **Versioned, with loads attributed.** Every loaded element records which recipe version
  produced it (`load_id`/`recipe_id`/`recipe_version` on its audit stub — `01_DOMAIN_MODEL.md`
  §2.4). When a mapping error is found in month six, the affected elements are identifiable by
  query rather than by guesswork.
- **Ontology-aware.** An ontology change that invalidates a recipe flags it and blocks scheduled
  runs until someone opens it. Recipes never silently adapt.
- **Revertible.** A load is a unit. Revert is a function in `services/ingest` (`revert_load`),
  tested directly against a live `GraphPort`, not a CLI command — this build has no `osprey`
  unified CLI. It supersedes everything the load created, leaving the audit trail intact.
  Reverting a load is not yet reachable from the admin console; it is a function call today, and
  gets its own console screen once that surface exists.
- **Written in bulk (ADR-058, accepted in its Amendment 1).** A publish is to aggregate its resolved rows and write
  nodes then edges through the bulk-load capability in chunks, falling back to `upsert_*` only for what collides with
  stored data; `upsert_*` stays the path for low-volume and interactive writes. The seeds load in bulk (Amendment 10);
  the Studio's engine does not yet, and still writes one element per call, which at 234,000 links (the Enron
  measurement) is hours.

### The recipe registry, and how "flags the affected recipes" (above) actually happens

"Publishing writes the recipe to version control, not only to the database" already implies a
database record; this section gives it a shape. A Postgres-backed `studio_recipes` table (the
same Postgres instance the Conduit's audit stream already uses) tracks one row per recipe
version: `recipe_id`, `version`, `ontology_version`, `label`, `status`
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
  ontology_version != :current`. This is what makes the flagging proactive (at the moment the
  ontology changes) rather than scanning every recipe file in the repository on every reload.
- **`StaleRecipeError`** (`services/ingest/engine.py`) is the separate, reactive last-line guard
  at actual run time and is unchanged by this — the registry is what surfaces the problem before
  someone tries to run a flagged recipe, not a replacement for the run-time check.

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
  profile — not automatic promotion.
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

- **No scripting.** Covered in §4, and worth restating because it is the request that will come
  up most often. Transforms are adapters with golden tests.
- **No joins across sources at ingest.** A recipe maps one source. Relating two sources is entity
  resolution's job, at query time, where it can be adjusted and undone. Joining at ingest bakes a
  decision into storage and is the same mistake ADR-006 rejects.
- **No aggregation at ingest.** Load records at source fidelity. Aggregation is a query.
- **No enrichment from external services.** No hosted lookup, no third-party enrichment API. What
  goes in is what came in, plus locally computed normalisation.
