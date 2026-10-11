# 08 — Acceptance Scenarios

Two analyst journeys, taken from the supplied documents, that between them exercise every
capability in the pack. They are the functional definition of done: if a scenario needs
scenario-specific code to pass, the platform has failed the test rather than passed it.

Both run on synthetic fixtures generated from a seeded generator in `tests/scenarios/fixtures/`.
No real data enters the repository.

## Which test proves these, and at which tier — DECIDED by owner ruling R5, 27 September 2026

There are two, and they are not interchangeable.

| Tier | Test | What it is |
| --- | --- | --- |
| **The closing-pass proof** | `tests/scenarios/test_phase8_exit_over_the_wire.py` | The rendered `local-lite` deployment, **through the analyst's own door**: OIDC authorization code with PKCE against the deployment's real Keycloak as the `--demo-analyst` subject, every call through the workspace's nginx proxy, the delta stream through the ticket exchange. No store port, no in-process app. Opt-in (`OSPREY_TEST_OVER_THE_WIRE=1`), its own CI job (`over-the-wire-exit-test`), `make exit-over-the-wire`. **This is the test the V1 END TO END milestone rests on.** |
| **The fast developer tier** | `tests/scenarios/test_phase8_exit_criterion_end_to_end.py` | The more complete walkthrough — every row below, including the ingest-dependent ones — driven in process (`TestClient`) against `make dev-up`'s published stores. Fast, and what a developer runs while changing a route. |

**Why R5 was needed.** The in-process test reaches ArcadeDB, Postgres and Valkey directly on
published ports. A rendered deployment publishes only the workspace and Keycloak — correct for a
deployment (`05_DEPLOYMENT.md` §7), and fatal for that test. Until R5 it was therefore the case
that the single test the milestone rested on **had never been run against the thing the milestone
is about** — a real finding, since fixed by ruling R5.

**The over-the-wire test does not cover every row, and its own module docstring has the row-by-row
table.** The reason is one fact: a rendered deployment gives an analyst **no route by which to
supply a source file** — `POST /v1/ingest/recipes` takes a `source_location` the Conduit's own
container must be able to read, nothing is mounted there, and the only upload route in the Conduit
is the site image. (That was so when the test was written. Since then the ingest folder is mounted
and files can be uploaded into it, `POST /v1/investigations/{id}/ingest/source-files`, ADR-067 and
ADR-099 Amendment 4; the recipe routes are under the case too.) So B1–B3 and every row that depends on data arriving that way (B6, B7, B8, B13,
B14, B15–B18) cannot be performed by an analyst against a rendered deployment at all. That is a
product gap, not a shortfall of the test. **Every row in that list has since been closed** —
B1–B3 on 27 September 2026 (the ingest root, owner ruling R6), B7/B8/B15–B18 by the
`scenarios` seed dataset, B13/B14 through the Ingest Studio, and B6 on 28 September 2026 once
the rendered model tier was pinned to the developer stack's. The table below carries each one's proof.

**Owner ruling R8, 27 September 2026 — those remaining rows are milestone-blocking, and this
section used to leave their weight unstated.** The question was put to the owner because
this section could be read two ways: it nominates the over-the-wire test as the one
the V1 END TO END milestone rests on (and it is green), while also saying that test does not
cover every row. R8 settles it:

> Clause 3 of V1 END TO END is **NOT REACHED — Reading B**. The milestone requires **every row of
> both acceptance scenarios to be performable through the analyst's own door on a rendered
> `local-lite` deployment.** Seeding the deployment with the remaining Scenario A and B fixture
> data is **milestone-blocking** work.

**So "which test proves these" has a bar, not just a tier.** A row proven only at the developer
tier (`test_phase8_exit_criterion_end_to_end.py`, in process against published stores) does **not**
count towards clause 3, however green it is.

**Built — six rows now clear that bar.** A third seed dataset,
`scenarios` (`scripts/seed_scenarios.py`, `--seed hmp,fixture-corp,scenarios`), puts Scenario B's
person layer, the shared messaging handle, the seized handset with its two SIMs and the device's
sightings into a rendered deployment.

| Row | Status | Proven by |
| --- | --- | --- |
| B7 | **over the wire** | `test_b7_a_shared_messaging_handle_is_common_to_the_second_cohort` |
| B8 | **over the wire** | `test_b8_the_handle_is_linked_to_the_shared_endpoint_asserted_at_one` |
| B15 | **over the wire** | `test_b15_both_sims_link_to_one_device_in_one_traversal` |
| B17 | **over the wire** | `test_b17_the_devices_location_events_are_reachable_and_windowed` |
| B16 | **over the wire + the Glass** | `test_b16_…` for the data; `apps/workspace/live/scenario-b-timeline.spec.ts` for the second track |
| B18 | **over the wire + the Glass** | `test_b18_the_sightings_form_an_ordered_track` (now also through `POST /v1/analytics/sightings`); `apps/workspace/live/scenario-b-timeline.spec.ts` for the trail advancing under playback — after a seed defect, see below |
| A1 | **over the wire** | `test_a1_a_site_grid_is_placed_and_its_cells_become_location_entities`, `test_a1_redrawing_the_grid_does_not_duplicate_its_cells`, `test_a1_a_cells_geometry_reference_resolves_to_its_centroid` (the ref names the cell's polygon), `test_a1_incidents_geocode_into_the_cells_that_contain_them` (owner rulings R9 and R10) |
| A6 | **over the wire** | `test_a6_the_reports_for_the_selection_open_with_a_source_locator_each` — not an extraction row |
| B6 | **over the wire + the Glass** | `test_b6_the_shared_endpoints_messages_open_with_the_entity_spans_in_place`; `apps/workspace/live/scenario-b-document.spec.ts` for the highlight in place |
| B13, B14 | **over the wire** | `test_b13_an_ingest_fires_an_alert_naming_the_identifier_document_and_rule`, `test_b14_an_alert_opens_into_an_investigation_linked_to_the_original` |
| A7 | **over the wire** | `test_a7_reports_can_be_filtered_to_one_item_category`, `test_a7_an_unknown_field_name_is_refused_rather_than_ignored` — the "Known gap" below is closed by `EventFilter.value_filters` |
| A15 | **over the wire** | `test_a15_a_consult_originator_item_blocks_the_export_by_name_then_proceeds_with_a_justification` |

**Every row, by tier, on the closing-pass proof.** "Rendered" is
`tests/scenarios/test_phase8_exit_over_the_wire.py` against a fresh-clone `local-lite` install,
signed in as the demo analyst (27 passed). "Glass" is `make glass-live` on the developer stack
(`apps/workspace/live/`). `test_scenario_a_over_the_wire` and `test_scenario_b_over_the_wire` are
the two walkthrough cases that carry the rows with no case of their own.

| Row | Rendered (over the wire) | Glass (live spec) | Performable under R8? |
| --- | --- | --- | --- |
| A1 | `test_a1_…` ×4 (grid, redraw, polygon ref, geocode) | — | Yes |
| A2–A5 | `test_scenario_a_over_the_wire` | — | Yes |
| A6 | `test_a6_…` | — | Yes |
| A7 | `test_a7_…` ×2 | — | Yes |
| A8–A11 | `test_scenario_a_over_the_wire` | — | Yes |
| A12 | `test_scenario_a_over_the_wire` | `scenario-a-a12-a15.spec.ts` A12 | Yes |
| A13, A14 | `test_scenario_a_over_the_wire` | `scenario-a-a12-a15.spec.ts` A13–A15 | Yes |
| A15 | `test_a15_…` | `scenario-a-a12-a15.spec.ts` A15 | Yes |
| B1–B3 | `test_b1_…`, `test_b2_…`, `test_b3_…` | `ingest-folder.spec.ts` | Yes |
| B4, B5 | `test_scenario_b_over_the_wire` (adapted) | `fixture-corp.spec.ts` (search) | Yes |
| B6 | `test_b6_…` (data half) | `scenario-b-document.spec.ts` ×2 | Yes |
| B7, B8 | `test_b7_…`, `test_b8_…` | — | Yes |
| B9, B10 | `test_scenario_b_over_the_wire` | `fixture-corp.spec.ts` (threshold, explain) | Yes |
| B11, B12 | `test_scenario_b_over_the_wire` | — | Yes |
| B13, B14 | `test_b13_…` ×2, `test_b14_…` | — | Yes |
| B15, B17 | `test_b15_…`, `test_b17_…` | — | Yes |
| B16 | `test_b16_…` | `scenario-b-timeline.spec.ts` B16 | Yes |
| B18 | `test_b18_…` (incl. the sightings route) | `scenario-b-timeline.spec.ts` B18 | Yes |
| B19, B20 | `test_scenario_b_over_the_wire` | — | Yes |
| B21 | `test_scenario_b_over_the_wire` | `fixture-corp.spec.ts` (pathfinder) | Yes |

Each of the six was **shown red first** against a deployment seeded `hmp,fixture-corp` only, then
green against **the same deployment** after seeding `scenarios` — one variable, not two
deployments.

**Built — B13 and B14.** The seizure record is a real file in
the deployment's ingest root, read by `connectors/seizure-record-csv.yaml`, walked Connect →
Profile → Map → Verify → Publish → Run as the demo analyst. `09_INGEST_STUDIO.md`'s rule that a
row worded "ingest …" is performed through the Studio rather than seeded around is honoured: no
candidate, node or edge for this row is seeded.

**Two corrections came out of building it, and both were defects in what this repository already
had.**

1. **The hotlist must be on the SIM's IMSI, not the handset's IMEI.** `services/api/evaluation.py`
   matches a hotlist against `node.properties["value_normalised"]` — an `Endpoint` property. The
   handset is a `Device` carrying `imei`, so a hotlist on it can never fire. B13's own wording
   ("the matched identifier") does not say which, and this is now recorded so the next reader does
   not lose an hour to it.
2. **The `scenarios` seeder seeded the SIM that B13 is supposed to ingest**, leaving the
   ingest nothing to create, producing no change entry, and firing no alert against a graph that
   looked entirely correct. The seeder now holds the *earlier* state — the handset with the SIM it
   held before the swap — and B13's ingest reveals the swap, which is what "the **later** seizure
   record" means. **B15 therefore depends on B13's ingest for its second SIM**, which is the
   scenario's own order rather than a test artefact.

**B13 is inherently a "new data arrives" row.** A hotlist watches incoming data and does not
retro-fire against what is already in the graph, so the row can only be walked on a deployment
where this record has not been ingested. The fixture asserts that precondition by name rather than
failing three assertions later on an empty list.

**A6 and B6 — walked over the wire.** What follows is the
account written when only the first half of the blocker was understood; the correction
is the subsection after it, kept together because the wrong diagnosis is as instructive as the
right one. Both are document-view rows, and a document's *spans* come from the extraction-candidates
store — `GET /v1/investigations/{id}/dossier/documents/{id}` reads `ExtractionCandidates`, not the
graph. They are populated by `POST /v1/investigations/{id}/ingest/extract`, which is the product's
own route and needs no seeding.

**That route had never worked on a rendered deployment.** `04_VAULT_BACKEND.md` §4 specifies
"Conduit → LiteLLM proxy → Ollama (local-lite: LLM + VLM, quantised)"; the renderer emitted
neither half — no LiteLLM service at all, and `ollama` as a bare image with no model pull, no
healthcheck and no volume. Measured over the wire: `500`, `httpx.ConnectError: All connection
attempts failed`. So `09_INGEST_STUDIO.md` §4's whole review queue was unreachable, not just
these two rows. **Fixed and proven**: a chat completion issued from inside the Conduit's own
container, through LiteLLM, to Ollama, now returns 200 with a real completion.

**Both rows are over the wire, and the diagnosis above was
wrong in two ways worth recording.**

**First, A6 is not an extraction row at all.** Its own step reads "Open the reports for the
filtered selection … each links to its source with a locator", and the reports are seeded
`Document` entities loaded by `tests/scenarios/fixtures/hmp_reports_recipe.yaml`; the locator is
the `SourceRef.locator` that ingest wrote. No model is involved. The paragraph above assumed both
document-view rows shared one blocker because they sit in one table cell —
`test_a6_the_reports_for_the_selection_open_with_a_source_locator_each` walks it with the model
tier untouched.

**Second, the named lead was the wrong place to look.** "The difference between those two call
sites" was the hypothesis; measured, the two sites send an **identical** request. What differed
was *which LiteLLM served it*: the conformance tier runs against `make dev-up`, which pins LiteLLM
and Ollama by digest, while `harness/render.py` pinned both by tags it had chosen — so a rendered
deployment ran LiteLLM `main-v1.55.8`, which does not translate `response_format: json_schema`
into Ollama's own constrained decoding and therefore let the model answer in prose. Correcting
that alone surfaced the second half: Ollama `0.3.12` predates schema-object `format` and refuses
the corrected request with `400 json: cannot unmarshal object into Go struct field
ChatRequest.format of type string`. Both pins now come from `deploy/compose/dev.yaml`, and
`tests/harness/test_render.py::test_the_rendered_model_proxy_is_the_developer_stacks` holds the
whole model tier to it.

**B6's data half is proven; its rendering half was the Glass's**, the split B16 and B18
carried — closed for B6 below. `test_b6_the_shared_endpoints_messages_open_with_the_entity_spans_in_place`
extracts from a synthetic transcript, accepts the candidate, and asserts the document view returns
the submitted text and a span covering the identifier within it — with the span still `inferred`,
since accepting a candidate does not promote it.

**A1's geocode half, and B16/B18's rendering halves.**

**A1: a cell's `geometry_ref` now resolves**; `services/api/app.py`'s grid route loads a
`GeometryRecord` per cell, which it had declined to do on a stated reason ("the Conduit has no
`AnalyticsPort` wired in yet") that had itself stopped being true. **"Incidents geocode into
cells" is still not claimed, and this is what it would take:** a cell is stored as a `POINT` at
its centroid, because `GeometryRecord` makes `POINT` and `POLYGON` mutually exclusive by design
and the `geometry_ref` Knowledge Adapter hashes a point — so a cell carries no extent, and
nothing in this repository resolves a point to the area containing it (`ST_Contains` appears
nowhere). Closing it needs three decisions, not one fix: whether a site cell is a polygon; what
happens to the `Location`'s existing ref when its kind changes; and which port method owns
containment. Raised here, in the spec, rather than guessed at in code.

> **Owner ruling R9, 28 September 2026.** Option 1: both remaining halves (A1's "incidents geocode
> into cells", B6's in-place highlighting) are **milestone-blocking build work**. A1's
> sub-decisions: **(a)** a site cell is a `POLYGON` in the geometry partition; **(b)** the cell
> keeps its `Location` identity, its `geometry_ref` moves to the polygon, and the centroid becomes
> a derived value — already-drawn grids are regenerated by redrawing; **(c)** containment is one
> `AnalyticsPort` method, implemented in the DuckDB adapter, held to by the conformance suite, and
> called by the grid route at draw time for incidents in scope. B6's in-place highlighting is
> proven by a live spec. The GitHub Actions gap on `main` since 22 September is bug-class work on
> the checker's brief.

**What R9 leaves for the building round to state before it writes code** (named here so it is not
filled silently): how a polygon's `geometry_ref` is derived, since the `geometry_ref` adapter
hashes a point today and (b) moves the ref to the polygon, so the ref's value changes on redraw;
the containment method's name and signature, and its access-control test (every read path gets one);
and what "geocode into a cell" writes for an incident. That could be the
event's cell reference, an edge, or both. The row's result is that "incidents geocode into
cells", and that output is what a test has to observe.

> **Owner ruling R10** (the owner's answers to three open questions, given in the maker session).
> Geocoding records **both** an event property and a graph edge.
> Seeded incidents are geocoded by their own points. Incidents that arrive after a grid is drawn
> are geocoded **on the next redraw**, not on ingest.

**A1 is over the wire.** What R9 left open, as built:

- **The polygon's ref.** A new Knowledge Adapter, `polygon_ref`, hashes the cell's four corners
  in the site's CRS (`polygon|crs|x0|y0|…`, TL/TR/BR/BL), with golden cases in
  `tests/knowledge_adapters/test_coordinates.py`. `recipes/site_grid.yaml` v2 binds it. The
  prefix keeps polygon refs and point refs from ever colliding.
- **Redrawing an older grid moves the ref.** `on_match: reference` never updates a matched
  node, so the grid route re-writes each cell `Location` whose ref differs, under the same node
  id: an ordinary upsert, a new revision of the same node. A superseded point row stays in the
  partition at its version, unreferenced. The partition is insert-only and versioned as a whole,
  so neither deleting that row nor bumping the version (which would hide every other geometry)
  is right.
- **Containment is `AnalyticsPort.geocode_events`** (`GeocodeRequest` → `list[GeocodedEvent]`).
  It is `ST_Covers` in the DuckDB adapter over `POLYGON` rows at the resolved version, and a
  point on a shared edge goes to the smallest ref. Access applies to events and polygons alike:
  an event the drawing analyst cannot see is neither geocoded nor returned, so it stays
  ungeocoded until a cleared analyst redraws. Six conformance cases, each shown red against a
  planted defect of the real shape.
- **What it writes.** On the event, `properties.site_cell` = the cell `Location`'s id, which the
  analytics routes' `value_filters` already filter on. In the graph, a `PRESENT_AT` edge from the
  incident's subject to the cell, carrying **the incident's handling**, written only when an
  incident's cell changes. `upsert_edges` sums occurrences on a same-pair write, so re-writing on
  every redraw would inflate them. A value this site's cells no longer cover is cleared from the
  event. An edge to a cell an incident has since left is not removed, since edges are never
  deleted; that is the one stale state a redraw into a *different* grid can leave.
- **The seed needed no change.** R10's "the fixture gains points" rested on a mistaken reading of
  mine: the HMP incidents already carry one point per yard (`_YARD_COORDINATES` in
  `tests/scenarios/fixtures/hmp.py`). The over-the-wire case places its site over those points.

**Found building it, and fixed:**
- `polygon_ref` was missing from `services/ingest/transforms.py`'s connector-default table. On a
  real deployment every grid row was refused as "ambiguous coordinate reference system" and the
  route 500ed; the in-process route test could not see it because it monkeypatches `run_recipe`.
  `tests/ingest/test_transform_connector_defaults.py` now guards the class: any adapter taking a
  connector default must receive it.
- A `POLYGON` `GeometryRecord` could not serialise to JSON at all (`bytes` defaulted to UTF-8).
  `geometry_wkb` is now base64 on the wire. Pydantic's mode is the URL-safe alphabet, which
  `atob` refuses, so the Glass maps it back before decoding. The Glass draws a polygon cell at its
  derived centroid (`apps/workspace/src/map/geometries.ts`); before this, a polygon record was
  simply absent, and every cell would have vanished from the map.

**B16 is proven in a real browser**, by `apps/workspace/live/scenario-b-timeline.spec.ts`. The row
reads "Overlay the **second investigation's** timeline on the first", so the spec runs against two
separately seeded investigations and asserts both that the overlay adds a track and that the track
is *drawing something* — an empty second case still produces a histogram, so the track count alone
goes to 2 for an overlay of nothing onto something. Shown red exactly that way before it was
trusted.

**B18 is proven in a real browser, after a defect that was in the seed, not the Glass.** First
recorded here as a Glass defect: with the device selected and the brush window set, the play control
rendered and the map drew no trail. Logging the page's own traffic showed the Glass sending exactly
the right request (`node_ids: ["seizure-scenarios-handset"]`, the scope, the seizure-day window) and
the Conduit answering `200 []`. The trail reads `AnalyticsPort.list_sightings` over the analytics
store's `events` rows; `scripts/seed_scenarios.py` wrote the sightings only as graph `PRESENT_AT`
edges — which is exactly what the over-the-wire B18 case read, so that case passed while the Glass
had nothing to draw. The seed now writes each sighting as both, tied by `edge_id` (`EventRecord` is
"one occurrence of" a summarised graph edge), idempotently. Held at three tiers: `tests/
test_seed_scenarios.py::test_b18_the_seeded_sightings_are_the_ones_the_glass_trail_reads` (the seeded
rows through `list_sightings` with the Glass's own filter; shown red with the load removed), the
over-the-wire B18 case (now also through the route), and the live spec (red against a scope with no
`scenarios` seed). The earlier note's claim that the route returned the four sightings "for that
entity, scope and window" was not a measurement of the request the Glass sends.

**B6 is proven in a real browser.** `apps/workspace/live/scenario-b-document.spec.ts`
holds two claims. First, a red state that costs nothing extra to seed: the *seeded* shared
endpoint's own provenance names a document id (`"fixture"`) that was never really ingested, so its
Dossier shows the empty state and no highlighted span — shown red by removing `Dossier.tsx`'s own
null-document filter, which would otherwise crash trying to render it. Second, the real claim:
extracting and accepting the same transcript `test_b6_…` uses, then reaching the accepted node's
own Dossier through the working set's one entry point (search, the radial menu's "View messages"
item, the same route `apps/workspace/keyboard/keyboard.spec.ts` already proves keyboard-reachable)
renders a real `<button>` over the message text, `title="Endpoint"`, covering the identifier. Shown
red by dropping the highlighted run's own `title` attribute.

**One run in eight surfaced a sharper case of the gap the paragraph below already names, worth
recording precisely rather than folded into "sometimes over-captures".** The accepted candidate's
span covered `"confirming the drop for tonight."` — not merely a wider span containing the
identifier (this file's own next paragraph's example), but a substring that does not contain it at
all. The live spec does not retry on this, deliberately: `test_b6_…` does not either, so retrying
here would make the two tiers disagree about what counts as a pass for the same underlying
`_locate` behaviour. Both fail hard on it, which is correct until the paragraph below's own
decision is taken.

**Proposed — a span should anchor on the property that identifies the entity, not the longest
one.** This row's own wording above says "the span text **equals** the entity's identifier", and
that is not currently guaranteed. `services/extract/candidates.py::_locate` tries every
string-valued property longest-first, on the stated reasoning that the longest value is the most
specific and so least likely to false-positive. Length is only a proxy for specificity, and
measurement showed where the proxy fails: the pinned model sometimes returns the whole message
line as `value_raw`, and the span then covered `Incoming from +447700900500: same yard as last
time.` rather than the endpoint. A span that wide cannot highlight an entity in place.

The obvious fix — anchor on the entity's identifying property — has no ontology concept to rest
on: for `Endpoint`, §7 of `01_DOMAIN_MODEL.md` makes `identifiers:` a list of *kinds*, not
property names, so nothing declares that `value_normalised` is what identifies the node. Choosing
one is a decision about the domain model, not a heuristic to pick in a test, so it is raised here
rather than made. Until it is taken, the row's test asserts containment, which is what the Glass
needs to highlight the entity at all, and this paragraph is the difference between that and the
row's own wording.

**One disclosed cost.** The CI-pinned `qwen2.5:0.5b-instruct` is sampled, and returned a candidate
carrying the shared endpoint on 6 of 15 consecutive extractions of that transcript. B6 therefore
retries the extraction up to twelve times — a bound taken from that measurement, and the same
run-to-run variance `tests/golden/harness.py` records for its own `N_RUNS`. Every assertion is
made in full once a candidate arrives; what is retried is the model's willingness to find
something, which is not what B6 is about.

Separately, A1's geocode half and the rows below need a seeding path into that second store, which is different work and
is not pretended to be done here. A1 needs a placed site grid; B13/B14 need an ingest to fire an
alert, and `09_INGEST_STUDIO.md`'s own rule is that a row worded "ingest …" is performed through
the Studio rather than seeded around it.

**Built — the "no door" half is closed.** The ingest root is
rendered, mounted read-only, listed by Connect, and walked end to end over the wire by
`tests/scenarios/test_phase8_exit_over_the_wire.py`.

**Built — B1–B3 are now over the wire.** They are walked through
the analyst's own door, Connect → Profile → Map → Verify → Publish → Run, and asserted by test id
(`test_b1_…`, `test_b2_…`, `test_b3_…`). Four separate things had to be true and none of them was:

1. **Connector availability is derived from `connectors/*.yaml`, not declared.** It had been
   hard-coded in four unconnected places, so `cdr-generic-csv` was declared in the catalogue and
   refused by the Studio — the reason recorded here until now.
2. **A connector profile's own settings reach the published recipe.** `studio_publish` built its
   `RecipeConnector` from the profile's *id* alone, so `date_order: dmy` never arrived and B3's
   `12/01/2026` would have been read with no declared order. Every test passed throughout,
   because they asserted on a hand-built connector the Studio never produces.
3. **The Conduit's image carries `git`.** It never had, so Publish — "publishing writes the
   recipe to version control" (`09_INGEST_STUDIO.md` §6) — returned a bare 500 in every rendered
   deployment this project has built. The one test of publishing runs on the host and supplies
   its own initialised repository, so it agreed with the code while the deployed article could
   not publish at all.
4. **The recipe repository has a persistent root.** It defaulted to `/app` inside the container:
   the image's own code directory, rebuilt on every deploy.

**What B3 asserts, and why those values.** Row 9 of the fixture is `2026-03-30 11:00:00` with no
offset against a recipe declaring `tz=Europe/London`; 30 March 2026 is inside British Summer
Time, so the correct conversion is `10:00Z` — a normaliser that read naive local time as UTC
would record `11:00Z` and pass any fixture that avoided a DST boundary. Row 6 is `12/01/2026`,
which read as `mdy` would land in December and move the stored interval's upper bound. Row 10 is
unparseable and appears in the run report's rejections, named, rather than guessed at.

**Ruled 27 September 2026 — owner ruling R6, restated the same day in fuller terms.** Ingest for
a rendered deployment works **through the existing Ingest Studio**, not around it: the ingest
folder is a configurable storage root in `osprey.yaml` (`components.storage.ingest`) alongside
data, staging and backups, set on the Components screen and shown in the summary rail; the
renderer bind-mounts it read-only into the Conduit for every profile; and the Studio's Connect
stage lists that folder's files so an analyst picks one and maps it on the existing Map canvas to
the POLE model. A browser upload route is explicitly post-milestone, as are Map's two already
recorded gaps. The ruling requires all five pieces to land together. Until they do, the rows above
stay proven at the in-process tier only, and this section's table stays as it reads.

---

## Scenario A — Fixed-site geospatial and temporal analysis

Derived from the HMP Hollywood intelligence development summary. Exercises site geospatial,
temporal, comparative case analysis, link analysis and assessment production.

**Fixture.** A synthetic secure site: 262 incident records over a two-month window, each with a
yard identifier, timestamp and item type; 229 associated reports of which 68 carry structured
detail; a population of ~400 person entities with wing and cell locations; a subset with
recorded group affiliations and family relationships; an aerial image of the site with control
points.

### The journey

| Step | Analyst action | Platform capability | Assertion |
| --- | --- | --- | --- |
| A1 | Upload the site image, place four control points, draw a 10×10 grid | Site geospatial | Grid cells become `Location` entities; incidents geocode into cells |
| A2 | View incident density across the grid | Geo-binning, heat layer | The four hotspot cells are the top four by count, and together account for ~52% of incidents |
| A3 | Select the hotspot cells | Cross-filter | Canvas, timeline and histograms all restrict to those cells; status bar shows the dimmed count |
| A4 | Switch the timeline to cyclical weekday × hour | Temporal, cyclical view | Two intra-day peaks are visible; Saturday and Sunday together are ~34% of the filtered total |
| A5 | Brush to the two intra-day peak windows | Temporal brush | The combined selection is ~66% of incidents in the hotspot cells |
| A6 | Open the reports for the filtered selection | Document view, provenance | 68 structured reports are returned; each links to its source with a locator |
| A7 | Filter reports to one residential sub-unit and one item category | Histogram cross-filter | The person entities named in the surviving reports are added to the working set as a named history step |
| A8 | Rank the resulting people by appearance count and group affiliation | Metrics panel | The principal subject ranks first; the affiliated subset is identifiable by an `Organisation` edge |
| A9 | Expand the principal subject's relationships | Radial menu, Search Around | Family, co-location, group and document-mention edges expand with a cardinality preview first |
| A10 | Notice the family link to a second subject on another wing | Link analysis | Both subjects share an `Organisation`; the second has prior events outside the current window |
| A11 | Drop the timeline filter to the full available history for these two | Temporal | Prior-period events appear; the pattern is visibly continuous rather than new |
| A12 | Run the Clique Metric on the working set | ComputePort | The relay group passing items between cells scores high on clique and low on degree centrality |
| A13 | Record four judgements against the yardstick, each with evidence | Assessment objects | A judgement cannot be saved without at least one supporting reference |
| A14 | Record seven intelligence gaps and three assumptions | Assessment objects | Gaps link to the entities they concern; assumptions link to the judgements they support |
| A15 | Export the chart and the assessment | Export, handling gate | Items marked consult-originator block the export by name; export proceeds only with a recorded justification and carries a withheld-item manifest; the export produces a real artefact of the requested shape (chart/subgraph/report), carrying the mark |

### What A13–A15 prove

Steps A1 to A12 are things a competent link analysis tool does. A13 to A15 are the reason this
platform exists: the analytical picture and the intelligence product are the same artefact, and
the product cannot be exported without the handling policy being applied to every element in it.
If a later change makes A15 pass without evaluating handling on each element, the platform has
regressed in the way that matters most.

**A15's own assertion was strengthened rather than left to read as proving more than it did.**
Before this addition, A15 tested the gate — blocks by name, requires justification, carries a
manifest — and stopped there, silent on whether anything a recipient could actually open ever
came out the other side. The milestone's own exit criterion, and through it the alpha
gate (`06_DECISIONS.md` ADR-042), were both satisfiable by an export feature that exported
nothing: the gate could pass every check and still hand nobody a file. **This is the second
instance of the same pattern this document's own standing rule 12 names — a gate proving less
than its name implies — found at the acceptance-scenario level, not only in a test file.** The
first was Scenario B's own "B12/B13/B14/B20 pass end to end," which was originally
found true only of the single-session walkthrough as written, not a claim that
hotlists and monitors fire across different analysts — the operational case B13's own CoLP framing
is actually modelled on. **That finding no longer holds — superseded once principal
resolution was built (`06_DECISIONS.md` ADR-043), proven by `test_a_hotlist_owned_by_one_analyst_fires_
from_a_different_analysts_own_ingest` — cited here as the
historical example the pattern was first found from, not as a still-open gap.** Both instances
share the same shape: an acceptance row whose literal wording is
narrower than what a reader assumes it proves, discovered only by checking the row against the
system's real behaviour rather than against its own passing test. A15's own assertion now says
what it means: the artefact must exist, in the requested shape, carrying the mark — not only that
the gate around producing one behaved correctly.

### Implementation note — A2's mechanism

`AnalyticsPort.geo_bins`'s precision ceiling (12, enforced by `GeoBinRequest`'s own validator)
cannot resolve individual grid cells at this fixture's scale: ten yards a few dozen metres apart
on one fixed site collapsed into two bins even at maximum precision — nowhere near "four hotspot
cells". A2's literal figure is instead produced by a *categorical* `cross_filter` dimension on
`target_id` (the yard `Location` each incident is `PRESENT_AT`), which resolves per-cell exactly
and reproduced the figure against live seeded data (51.1% measured vs. ~52% here). The Glass's
Map view ships both: the `geo_bins` heat layer (`02_GLASS_FRONTEND.md` §3.5 names it directly,
and it stays correct at a coarser scale this fixture doesn't exercise) and a ranked "hotspot
cells" panel on `target_id` as the mechanism A2/A3 actually rely on at this fixture's scale.

### Closed — A7's "item category" filter

This was a "Known gap". It read: `EventFilter` carries `investigation_scope`, `window`,
`node_ids` and `edge_types` only, with no field/value predicate an event property such as
`item_type` could be filtered on — `cross_filter`'s categorical dimensions *display* a field's
distinct values without letting a caller *restrict by* one.

**`EventFilter.value_filters` is that predicate.** `{field: [value, ...]}`; values within a field
OR-ed, fields AND-ed — the shape a filter bar with several facets has. Equality only: no ranges,
no negation, nothing fuzzy, because A7 needs none of them and each is a separate decision about
what an analyst asserts by clicking a facet. It is compiled into the adapter's own `WHERE` clause
beside the access filter, never applied after retrieval (`03_CONDUIT_MIDDLEWARE.md` §6 — access
control lives in the query, never after it), and a field may be a top-level event column or a key
inside the JSON `properties` blob.

**The data was never the problem.** The HMP fixture has written `item_type` on every event since
early in the build; only the predicate was missing, which is why this row needed a feature rather than a
fixture. Four conformance cases hold every adapter to it, including that a field name carrying
SQL is refused — a value filter is the first place a caller names a *column*.

### Additional assertion — retraction propagates

After A15, retract one node that supports a judgement. The judgement is flagged for review
within the same session, and the export produced in A15 is marked as resting on retracted
evidence. This closed loop is what makes the assessment objects worth storing rather than
writing in a word processor.

**This sentence is not what the analyst sees, and the discrepancy was found by running the
scenario over the wire on 27 September 2026 — recorded here, not fixed here.** The flag *is*
written (`flag_judgements_citing_superseded_node`, proven by `tests/services/api/
test_assessments.py`, which calls it directly and re-reads the store). But retraction supersedes
the node with a **new id**, the judgement's `supporting` still names the old one, and ADR-046's
hide-in-full rule (`judgement_visible_to`, composed into `list_visible_judgements`, the function
the Judgements tab's own route calls) removes every judgement with an unverifiable supporting
citation. Measured through the deployed Conduit: before the retraction the judgement lists with
`flagged_for_review: false`; after it, the list is empty. Two rules each correct alone compose
into a third behaviour this document does not describe, and no test could see it because the only
one that checked the flag bypassed the route.

**Ruled 27 September 2026 — owner ruling R7, and recorded as TENTATIVE at the owner's own
instruction, to be revisited after their usability walkthrough.** `06_DECISIONS.md` ADR-046's
addendum carries it in full. Two parts:

- **Retraction becomes two steps.** In the Glass an analyst *marks* a node for suppression —
  immediate, reversible, shown as a marker on the node and in the inspector. The suppression only
  *takes effect* when its evidence arrives through the Ingest Studio: a retraction record ingested
  and mapped to the node like any other source, so no suppression is ever an unevidenced click.
  This depends on ruling R6 (ingest for a rendered deployment works through the Studio) and cannot
  land before it.
- **A judgement citing a marked or suppressed node stays visible to its author, flagged for
  review, with the citation resolved to the successor for display.** ADR-046's hide-in-full rule
  applies to citations the principal is not *permitted* to verify, not to citations the system
  itself superseded.

**The visibility half is now built, so this document's own
sentence is true again**: a judgement whose supporting node is retracted stays visible to its
author, flagged for review, with the citation resolved to the successor for display — and the
citation itself is never rewritten, because the judgement asserted something about the evidence
as it stood. `tests/scenarios/test_phase8_exit_over_the_wire.py` asserts exactly that through a
real deployment, and `tests/services/api/test_assessments.py` in-process.

**The export half is built too, and it was not merely unimplemented — it was unimplementable.**
"The export produced in A15 is marked as resting on retracted evidence" had no implementation
anywhere, and could not have had one: `evaluate_export_selection` treated a superseded item the
same way it treated an access-denied one, so naming a retracted item blocked the export outright
and left no artefact to mark. Narrowed the same way, and `ExportMark.rests_on_retracted_evidence`
now carries it.

**Still not built: the two-step retraction R7 also describes** — marking a node is built
(`02_GLASS_FRONTEND.md` §9.5) but the suppression still takes effect through the existing
`/v1/investigations/{id}/nodes/{node_id}/retract` route rather than through an ingested retraction record.
`06_DECISIONS.md` ADR-046's addendum records the two decisions that blocks on.

### The fixture's statistical shape is built and proved independently of the map UI

The A1/A2 site-grid mechanism (upload an image, place control points, draw a 10×10 grid) is
a later capability — it needs the Glass's map screen. But the *finding itself* — four yards at ~52% of
incidents, two intra-day peaks, Saturday and Sunday at ~34% — is a property of the event data,
not of the grid UI, and is built and proved early
(`tests/scenarios/fixtures/hmp.py`, `tests/scenarios/test_hmp_fixture_shape.py`) against a real
`AnalyticsPort` adapter. Otherwise Scenario A would only discover, by eye
in a UI, whether the fixture ever actually carried the finding it is supposed to demonstrate.

---

## Scenario B — Communications, identity pivot and cross-case alerting

Derived from the City of London Police demonstration journey. Exercises identifier
normalisation, deduplication, entity resolution, pattern analysis, hotlist alerting and
cross-case linking.

**Fixture.** Two device extractions and two CDR files in different carrier formats, with
deliberate variation: the same number rendered four ways, CLI-suppression prefixes, duplicated
rows with differing sequence numbers, and mixed timestamp formats including one file in local
time. Two cohorts of person entities with no overt association. One messaging-handle dataset.
One later seizure record with two SIMs and a handset identifier.

### The journey

| Step | Analyst action | Platform capability | Assertion |
| --- | --- | --- | --- |
| B1 | Ingest both CDR files and both device extractions | Connectors, Knowledge Adapters | All four renderings of the shared number resolve to one `Endpoint`; `value_raw` is retained on each |
| B2 | Check the ingest report | Deduplication | Duplicate rows collapse to single events; every source row reference is retained on the survivor |
| B3 | Check timestamps | Datetime normaliser | The local-time file is converted with its original offset recorded; a file with no recoverable offset is rejected with a named error, not guessed |
| B4 | Seed a working set from the first cohort | Search, seed | Four person entities, no edges between them |
| B5 | Expand each to their endpoints, then one hop out | Search Around | One shared `Endpoint` is common to all four |
| B6 | Inspect the shared endpoint's messages | Document view | Message content renders with the entity spans highlighted in place |
| B7 | Repeat for the second cohort | Search Around | A shared messaging handle is common to that cohort |
| B8 | Examine the handle | Entity resolution | A `SAME_AS` edge, asserted at score 1.0 (ADR-024's own pattern for identifier systems with no lexical overlap — a handle and an `e164` number share none), links the handle to the shared endpoint |
| B9 | Move the resolution threshold from Strict to Balanced, on a genuinely close-but-not-exact `Person` pair the fixture provides (not the handle/endpoint pair — B8 is now a deterministic assertion, never threshold-sensitive; see the note after this table) | Resolution projection | The merge applies; the change summary reports entities merged and nodes affected |
| B10 | Open `explain` on the merged `Person` cluster | Resolution explainability | Per-comparison match weights are shown, not just the total score |
| B11 | Attribute the handle to a person | Manual link | A `SAME_AS` with score 1.0, provenance `asserted`, attributed to the analyst |
| B12 | Add the endpoint to a hotlist | Hotlist | The hotlist records owner and review date |
| B13 | Ingest the later seizure record | Hotlist alert | An alert fires naming the matched identifier, the triggering document and the rule |
| B14 | Open the alert into a pre-populated investigation | Alert workflow | The new working set contains the alert's entities and a link to the originating investigation |
| B15 | Pivot on the handset identifier | Endpoint model | Both SIMs link to one device; the SIM-swap pattern is one traversal, not a special case |
| B16 | Overlay the second investigation's timeline on the first | Cross-case overlay | Both event sets render on distinct tracks against a shared axis |
| B17 | Brush to the seizure date | Temporal brush | Location events for the device in that window restrict the map |
| B18 | Plot the device's sightings | Snail trail | An ordered track renders and animates under playback |
| B19 | Expand to common contacts across the two principal endpoints | Pattern query | The intersection set is returned, with the estimated count shown before running |
| B20 | Save the pattern as a monitor | Saved-pattern monitor | Subsequent matching ingest raises an alert with the same shape as B13 |
| B21 | Run the pathfinder between the two principal endpoints, one from each investigation | Pathfinder | `POST /v1/investigations/{id}/paths` returns k-shortest paths through the Glass end to end; the shortest path traces the same cross-case link B16 found by timeline alone, and the on-path node state matches §3.1's own convention |

**Each case reads only its datasets (ADR-099), and these rows depend on it.** B13 fires only if the
seizure record is loaded into the hotlist's dataset, and B20 only on ingest into its pattern's
dataset (a match in another dataset raises nothing). B14's new case reads the alert's dataset. B21's
path across the two investigations is found only from a case reading both datasets. B16's overlay
reads the analytics store, which stays keyed by case (ADR-099 decision 7), so it is unchanged.

### What B1–B3 prove

The unglamorous part. If identifier normalisation is wrong, the shared endpoint in B5 does not
exist, every subsequent step fails, and — worse — it fails by returning a clean, confident,
wrong answer. These three steps are the highest-value assertions in either scenario and should
be among the very first tests written.

### B8's own disposition — the chain split, correcting the scenario rather than working around it

**B8, B9 and B10 were one chain until this correction; they no longer are.** `Endpoint` carries no
`resolution` block in `packages/ontology/default.yaml` — checked directly, not assumed — and the
closed comparison-function registry (`packages/ontology/resolution_functions.py`:
`jaro_winkler`/`levenshtein`/`soundex`/`exact`) compares values of the same kind, the same reason
`06_DECISIONS.md` ADR-024 already gives for why an MSISDN and the IMSI it is dialled through
cannot be Splink-matched: "no lexical resemblance a comparison function could ever detect." A
handle and an `e164` number are the identical shape of problem. **This is the scenario catching up
with an already-accepted ADR, not the ADR being worked around**: ADR-024 decided this exact class
of identifier — two systems naming the same real-world thing with no shared lexical space — gets a
deterministic, asserted `SAME_AS` at score 1.0, written at ingest, never a Splink comparison. B8 is
corrected to say that (above).

**B9 and B10 move to `Person` resolution, unchanged in their own assertion text, because on
`Person` those assertions are literally true.** A deterministic score of 1.0 is already included
at every threshold, so "the merge applies" when moving Strict to Balanced would be vacuous against
B8's own corrected pair — there is nothing for the threshold to newly admit. `explain`'s own
"per-comparison match weights" likewise requires a real multi-comparison Splink score, which an
asserted 1.0 does not have. Both assertions are real and provable, on a real `Person` pair, which is
what B9/B10 now target.

**The fixture gap above — closed.** `Person` resolution needed a genuinely
close-but-not-exact pair; neither of this scenario's own two cohorts provides one
(`_seed_cohort`/`_seed_handle_cohort` write each cohort's own four `Person` nodes with a shared,
identical `family_name` and sequential `given_names`, no near-duplicate signal at all). **Closed by
reusing `tests/scenarios/fixtures/fixture_corp.py`'s own generator
(`generate_resolution_persons()`), not a second, hand-rolled pair** —
`test_phase8_exit_criterion_end_to_end.py`'s own `_seed_and_resolve_b9_b10_person_pair` extracts
that generator's own `close_given_name` pair's property values ("Volkov"/"Mikael" vs.
"Volkov"/"Mikhail", same DOB), writes them under fresh ids (avoiding a node-id collision with
Fixture Corp's own literal fixed ids in the same shared, persistent `ospreyflow` database), and
resolves them for real. **The measured, live score: 0.9812853391529271** — inside
(Balanced 0.95, Strict 0.99) by a real margin either side, asserted directly in that helper
(`THRESHOLD_BALANCED <= score < THRESHOLD_STRICT`) before the edge is even written, so a pair that
happened to land outside the band fails loudly rather than silently making B9/B10 vacuous again.
B9 now proves the threshold move for real (Strict: `merged == 0`; Balanced: `merged == 1`,
`affected == 2`); B10's `explain` shows a real `comparison_vector` and `manually_asserted: false`.

**Every other citation of B8 checked, none resting on it being Splink-scored.** `06_DECISIONS.md`
ADR-023 names B8 as its own precedent for using the `SAME_AS` edge *type* for a duplicate-identity
question — quoted alongside B11's own manual (asserted) link in the same sentence, never
distinguishing scored from asserted, so its reasoning holds unchanged; ADR-023 needs no correction.
Every remaining citation (`06_DECISIONS.md` ADR-025 and its own references) groups B8 with
B9/B13/B20 as needing the corpus-wide resolution trigger
(ADR-025) to run against a live deployment — **this grouping is now stale for B8 specifically**:
under the corrected, ADR-024-pattern write, B8's own edge is produced by the ingest recipe engine
at load time (ADR-024's own "natural home"), not by a later batch resolution job, so B8 no longer
depends on ADR-025's trigger at all. B9/B10, now pointed at genuine `Person` resolution, still do.
Not swept across every citation site here — recorded as a known, real consequence for whoever next
touches those references.

---

## Cross-cutting assertions

Run against both scenarios, on both the `local-lite` and `cluster` profiles.

| Assertion | Why |
| --- | --- |
| Every action appears in the audit stream with principal, query and result cardinality | Audit is architecture (`00_ARCHITECTURE.md` §5) |
| A restricted principal running the same scenario sees fewer entities, is told how many are withheld, and is never told which | Filter at the port, disclose the count, never the content |
| A case sees, counts and finds nothing outside its datasets, through search, suggestions, expansion, paths, the Explore counts and rankings | A dataset is a limit of access, like handling (ADR-099) |
| Every model-derived node is `inferred` until confirmed; no automatic promotion occurs | `01_DOMAIN_MODEL.md` §2.1 |
| No filter removes a node from the canvas; all filtering dims | `02_GLASS_FRONTEND.md` §2 |
| The status bar count of dimmed and withheld items is correct at every step | An analyst must never mistake a partial picture for a complete one |
| The performance budget holds throughout | `02_GLASS_FRONTEND.md` §5 |
| Results are identical on both profiles, allowing only floating-point tolerance on iterative metrics | Transportability |
| Disconnecting the network mid-scenario on `local-lite` changes nothing | Air-gap capability is a claim that must be tested |

**The two rows above are not part of V1 END TO END — recorded here pending the
owner's own confirmation.** The owner defined the V1 END TO END milestone
as a `local-lite`-only, clean-laptop install-and-demo; neither row is exercised by that milestone
as a consequence of that definition — this document does not claim the owner separately stated a
view on these two rows in these terms. Both remain real, standing claims for this document to prove
once their own owning work exists. Profile-parity testing's home is the `cluster`-profile
work; network-partition resilience has no owning work yet — both entries, with the full
reasoning, are recorded as out of scope for v1, not deleted from here.

## Scenario C — Operation Ledger, preventive AML (ADR-109) — PROPOSED, recording what is proven

**Status: proposed, not owner-ruled.** Scenarios A and B are the owner's definition of done. ADR-109
added preventive AML and KYC after both were written, and this document said nothing about it (found
by the spec survey of 11 October 2026). The rows below **record what ADR-109's tests already prove**
against the synthetic Operation Ledger fixture (`packages/demo_fixtures/ledger.py`, the synthetic
consolidated screening list, `ledger_onboarding_applications.csv`). They add no new criterion until
the owner rules them in; until then they are evidence, not a gate.

| # | Step | Capability | Proven by |
| --- | --- | --- | --- |
| C1 | Halcyon Marine Ltd's onboarding file is loaded through the Studio with the case's KYC rules deployed before commit | Rule gate, ingest | `test_an_applicant_owned_through_a_trust_by_a_listed_person_is_stopped_at_the_gate`; `test_the_gate_the_routes_build_carries_what_the_kyc_and_pattern_rules_read` (the routes' own factory) |
| C2 | The applicant loads with three alerts — PETROV 48% (sanctions), NAIR 32% (PEP), the expired certificate — and Brookfield with none | KYC screening of beneficial owners, document verification | the C1 case; `test_an_expired_document_verifies_no_one`, `test_a_valid_document_raises_nothing`, `test_an_owner_below_the_threshold_is_not_screened`; seen live 11 October 2026 |
| C3 | A rule that cannot judge holds the rows; a reviewer releases them and the rules judge them again | Fail-closed quarantine | `test_a_failing_pre_commit_rule_holds_its_rows_out_of_the_graph`, `test_a_released_row_loads_with_its_original_row_number`; `keyboard/alerts.spec.ts` (held rows) |
| C4 | The team's queue shows each alert in words; one is put on the canvas and closed as a true positive, confirming its node | Alerts place, triage, rule 5 | `test_a_rule_alert_is_in_the_whole_case_teams_queue`, `test_an_alert_explains_itself_with_its_transactions_links_and_node`, `test_triage_claims_once_and_a_true_positive_confirms_the_alert_node`; `keyboard/alerts.spec.ts` |
| C5 | Ownership is traced through the trust to the people behind it, a circle traced once | ComputePort.ownership, both tiers | `tests/conformance/compute_port/test_suite.py` (`test_ownership_through_a_chain_is_the_product_of_its_shares` … `test_ownership_agrees_across_tiers`); `keyboard/ownership.spec.ts` |
| C6 | Due diligence and neighbourhood risk are read as the reader sees the graph, never stored | KYC at read, ComputePort.propagate | `test_the_status_and_risk_are_computed_from_what_the_reader_sees`, `test_a_document_the_reader_cannot_see_verifies_no_one_for_them`, `test_risk_decays_by_half_per_hop_of_the_shortest_distance`; `keyboard/inspector.spec.ts` |
| C7 | A customer, alert or rule audit entry the reader cannot see is neither judged for them, shown nor counted | Rule 3 on every read path (rule 4) | `test_a_customer_the_deployer_cannot_read_is_not_judged`, `test_an_alert_the_reader_cannot_wholly_see_is_neither_queued_nor_opened`, `test_a_rule_audit_entry_naming_a_hidden_node_is_withheld_from_page_and_total`, `test_held_rows_are_read_only_at_or_below_the_readers_marking` |

**Not yet an over-the-wire test.** Unlike A and B, no single test walks C1–C7 against a deployed stack
as the demo analyst; the walk was done by hand on 11 October 2026 and recorded in the build record. Writing that test is what ruling this scenario in would require.

**Likely stale, not run:** B1–B3's Glass test `apps/workspace/live/ingest-folder.spec.ts` clicks
*Ingest Studio* and expects the Connect picker at once; since ADR-108 phase B the Studio opens on the
pipelines home (`09_INGEST_STUDIO.md` §1.0), so the test probably fails until it opens a pipeline's
first source. It needs a live stack to confirm and is recorded here rather than assumed.
