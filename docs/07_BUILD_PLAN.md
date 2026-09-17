# 07 — Build Plan

Nine phases. Each has a single demonstrable outcome and an exit criterion that is a test, not a
judgement. Do not start a phase until the previous one's exit criterion is green in CI.

The ordering is deliberate: the ports and the domain model come before any feature, because
every decision that is expensive to reverse lives in those two phases.

---

## Phase 0 — Skeleton and guard rails

**Outcome.** An empty monorepo that will not let you build the wrong thing.

- Monorepo layout per `00_ARCHITECTURE.md` §6.
- `packages/ports` — all four `Protocol` definitions, no implementations.
- `packages/schemas` — Pydantic models, with TypeScript type generation wired into the build.
- CI: lint, type-check both languages, `make licence-check` against the allowlist, and
  `trivy fs .` — a filesystem and dependency scan, since no image exists to scan until a service
  gains a Dockerfile. Add `trivy image` per service from the phase that containerises it.
- Conformance suites written for real, and structurally unable to pass vacuously. Each port gets
  a parametrised `test_suite.py` over an adapter registry that is empty in this phase, so it
  collects zero cases, plus an always-on `test_guard.py` asserting that the suite module imports
  cleanly and that the registry is empty. Zero collected cases is then a stated condition rather
  than an accident, and a suite that fails to import is a red build rather than a silent no-op.
- A single `_phase0_placeholders.py` in `packages/schemas` holding opaque stand-ins for exactly
  the types the four `Protocol` signatures reference. The domain model is Phase 1, but a
  `Protocol` cannot type-check against types that do not exist, and the drift gate needs a real
  model to change. Placeholders live in one module so their removal is a single deletion.

**Exit.** CI green — including the guard tests, which pass by construction here. A pull request
adding a GPL dependency fails, proved by a committed fixture lockfile and a test asserting the
offending package is rejected by name, not by a scratch branch or a manual check. A change to a
Pydantic model that is not reflected in the generated TypeScript fails the build. Seeding the
registry with a fake adapter turns a guard test red, which is what proves the empty-registry
assertion is not vacuous.

---

## Phase 1 — Domain model and graph adapter

**Outcome.** The ontology round-trips through a real graph store with access control working.

- Ontology loader, JSON Schema validation, channel and shape allocation with the nine-channel
  constraint enforced.
- Node, Edge, Provenance, Handling, ResolutionState, AuditStub.
- Handling scheme loader and the handling evaluator.
- `adapters/graph_arcadedb` — full `GraphPort`, declaring its `dialects` capability.
- Dialect-agnostic query builders with a `gremlin` render backend; the `GraphPort` conformance
  suite parameterised by dialect so a second backend can be proved against the same fixtures.
- Schema generator and migration runner, including the indexes in `04_VAULT_BACKEND.md` §1.4.
- `GraphPort` conformance suite, complete.

**Exit.** The conformance suite passes against ArcadeDB, including the existence-leak assertions:
an unauthorised principal cannot detect a filtered node via path length, degree count or
aggregate bucket. Two further conditions carried over from Phase 0: `_phase0_placeholders.py` no
longer exists once any adapter is registered, enforced by its own guard test; and each port's
`test_guard.py` empty-registry assertion is updated alongside the adapter that populates it, so
the guard turning red is recognised as the expected handover rather than a regression.

---

## Phase 2 — Ingest, normalisation, staging

**Outcome.** A CSV of call records becomes a queryable graph, correctly.

- Connector framework as validated profiles in `connectors/`; CSV, JSON and generic delimited.
- The ingest recipe format and its headless execution engine (`09_INGEST_STUDIO.md` §6), with
  row templates, match-on/on-match semantics, conditional elements and deduplication keys.
- Source profiler: type inference, null and cardinality statistics, and pattern recognition
  against the Knowledge Adapters.
- A throwaway prototype of the studio's Map screen over the headless recipe engine, put in front
  of an analyst for review (ADR-018). Cheap here, expensive in Phase 5a.
- All Knowledge Adapters from `01_DOMAIN_MODEL.md` §7, each with a golden test file.
- CDR content-hash deduplication.
- CRS reprojection at ingest (`01_DOMAIN_MODEL.md` §7.1, ADR-017): `coordinate_lon`/
  `coordinate_lat` Knowledge Adapters, declared `source_crs` per connector, fixtures in
  EPSG:27700 and two NAD83 State Plane zones.
- Parquet staging in MinIO.
- `adapters/analytics_duckdb` — full `AnalyticsPort`, and its conformance suite.
- The HMP fixture (`08_ACCEPTANCE_SCENARIOS.md` Scenario A's statistical shape, not its site-grid
  UI mechanism): four yards at ~52% of incidents, two intra-day peaks, weekend at ~34%, proved
  against a real `AnalyticsPort` adapter now so Phase 5 inherits a fixture already known correct.
- Load path writing both stores in one logical transaction per document.
- Edge weight computed per `01_DOMAIN_MODEL.md` §6.1 at load time (`adapters/graph_arcadedb`
  wrote a hardcoded `0.0` in Phase 1 — correct to defer, since the formula needs corpus-wide
  mutual information that doesn't exist until a corpus does).
- `services/ingest/Dockerfile` and its `trivy image` CI scan — see the standing rule below.

**Exit.** Load the synthetic CDR fixture through a hand-written recipe. Every phone-number
variant in the fixture resolves to one `Endpoint`. Duplicate rows collapse to one event with both
source references retained. A timeline histogram over the loaded events returns correct counts,
including across a DST boundary. Rows with an undeterminable timezone are rejected and counted,
never coerced. Reverting a load (`services/ingest`'s `revert_load` function — there is no
`osprey` CLI; this build does not have one, a correction to this phrasing's original assumption)
supersedes a whole load and leaves the audit trail intact.

---

## Phase 3 — Conduit and the working set

**Outcome.** A client can build and hold a working set.

- FastAPI app, OIDC via Keycloak, `Principal` resolution.
- Working-Set Service on Valkey: storage, caps, projection, delta computation.
- WebSocket delta protocol including the reconnect-and-resnapshot path.
- Expansion with cardinality preview and the expansion budget.
- Audit stream to PostgreSQL, with write failure failing the request.
- `NodeId`/`EdgeId` (ULID) and the audit stub's `created_at`/`revision` assigned here, by the
  Conduit, per `01_DOMAIN_MODEL.md` §2 — `adapters/graph_arcadedb` assigns them in Phase 1
  for lack of a Conduit yet to do it; move the assignment up when this phase lands, rather than
  the adapter continuing to do a Conduit's job.
- `Subgraph.filtered_count`, populated for real. `01_DOMAIN_MODEL.md` §8: left at `0` since
  Phase 1 — a declared gap, not a silent one — because computing it correctly needs a
  full-vs-filtered comparison at a point that holds both results, and no such point exists before
  this service does. `GraphPort.expand` itself cannot: its access predicate is compiled into the
  traversal from the start (never filter after retrieval), so it only ever sees the
  already-filtered result, and a second, broader query just to count what got excluded is exactly
  the kind of extra, less-audited channel the existence-leak requirement rules out. The
  Working-Set Service can, safely, because it already holds the full source-fidelity set
  server-side and applies the handling filter as a projection on read — the comparison is a size
  difference over data already fetched under its own authority, not a new query. Populate it as
  part of the expansion budget/cardinality preview work above, not as an afterthought:
  `02_GLASS_FRONTEND.md`'s status bar ("`6 hidden by handling`") reports this count directly, and
  an always-zero value reaching that screen would tell an analyst nothing was hidden in a system
  where things routinely are.
- A job-based path for `GraphPort.supersede_node` above a degree threshold, rather than always a
  synchronous Conduit call. `01_DOMAIN_MODEL.md` §8.2: measured (not assumed) at ~41 seconds for a
  5,000-degree node against a local ArcadeDB instance — it held, correctly, but a request that
  takes 41 seconds is not a reasonable synchronous operation, and a high-degree node (§6.1's
  "service number that everyone calls") is exactly the shape most likely to need correcting.
  Same job/status-id shape as `PatternQuery`'s "large results return a job id"
  (`03_CONDUIT_MIDDLEWARE.md` §3.3).

**Exit.** A scripted client seeds a working set, expands three times, disconnects mid-stream,
reconnects and arrives at a byte-identical set. Every action appears in the audit stream. An
expansion that would breach the cap returns the typed `limit_exceeded` error with its three
options. An expansion that excludes a handling-filtered node reports a non-zero `filtered_count`.

---

## Phase 4 — The Glass, first light

**Outcome.** An analyst can see and navigate a network.

- Vite app, `design/tokens.css`, the twenty primitives.
- Sigma renderer with the full node state vocabulary from `02_GLASS_FRONTEND.md` §4 —
  all nine channels, all three provenance strokes, all six interaction states.
- graphology working-set store, delta client.
- Canvas interaction: pan, zoom, select, lasso, radial context menu, expand.
- Semantic zoom (`02_GLASS_FRONTEND.md` §1.1): the four zoom bands via `nodeReducer` and
  `edgeReducer`, band transitions that fade rather than pop, and `hideEdgesOnMove` during camera
  movement only.
- Edge inspection as a DOM overlay anchored to the camera: type, occurrence count, interval,
  provenance, contributing source records.
- Inspector with properties, provenance and source excerpt.
- Global search.
- Named-step history with restore.

**Exit.** Load the 50k fixture. The performance budget in `02_GLASS_FRONTEND.md` §5 is met on
target hardware, measured in CI, including a sustained pan and zoom sweep from full overview to
link detail. Zoom never changes the working set: node and edge counts in the status bar are
identical at every band. Keyboard navigation reaches every canvas action. Both themes
pass automated contrast checks.

**Pre-deployment hardening item, carried forward rather than silently accepted.** The delta
stream's WebSocket route accepts a `?token=` query-parameter fallback
(`services/api/app.py`'s `_authenticate_websocket`) alongside the `Authorization` header, because
a browser's native `WebSocket` cannot set that header at all — discovered live, when the Glass's
canvas first tried to open this connection from an actual browser. The fallback carries the same
long-lived JWT a browser client already holds, which is adequate to demonstrate this phase but not
to deploy: a real deployment should replace it with a short-lived, single-use ticket (minted by an
authenticated HTTP call, exchanged here instead of the JWT itself) before going live, closing the
"token visible in a server access/proxy log" exposure the query-parameter form has. Not scheduled
into a numbered phase above; tracked here so it has a home before Phase 5 rather than only a code
docstring.

---

## Phase 5 — Temporal and geospatial

**Outcome.** Three of the five analytical capabilities, cross-filtering.

- Timeline: density strip, brush, playback, cyclical weekday × hour view, multi-track.
- MapLibre integration with `@sigma/layer-maplibre`.
- Basemap provider registry from `osprey.yaml`; layer control; attribution and licence notes
  rendered with the map and carried onto exports.
- Tier 1 shipped default: one-button local basemap build (extract download, planetiler, gazetteer
  load), with bundled dark and light MapLibre styles built against `design/tokens.css`.
- Tier 2 and tier 3 provider paths; the Conduit tile proxy with credential references, caching
  and area-of-operations prefetch.
- **Verify** parity check rendered on screen: CRS, zoom range, contrast floor over a fixture
  graph, attribution presence.
- Tier 4 generic OGC: WMTS, WMS, WFS and OGC API – Tiles/Features, with capabilities parsing at
  registration and projection handling beyond Web Mercator.
- Provider profile schema and validator; the shipped `providers/` set for the UK and the US, each
  with a verify fixture.
- UK and US gazetteer connectors: OS Open Names / Open UPRN / Code-Point Open / Boundary-Line,
  and USGS GNIS / Census TIGER/Line / National Address Database. Coordinate reprojection itself
  (`coordinate_lon`/`coordinate_lat`/`geometry_ref`/`grid_ref`, `01_DOMAIN_MODEL.md` §7.1) was
  brought forward to Phase 2 — these connectors consume it, they do not rebuild it.
- The geometry reference partition's own versioning and access-controlled read path
  (`schemas/analytics.py`'s `GeometryRecord`, Phase 2's stated gap) — Phase 2 established the
  correct storage tier and shape only.
- Give the HMP fixture (`tests/scenarios/fixtures/hmp.py`) a graph side: real `Location`/`Person`
  nodes and `PRESENT_AT` edges behind its `EventRecord`s, not the synthetic, unconnected
  `edge_id`/`source_id`/`target_id` strings Phase 2 scoped it down to. Needed once the site grid
  below actually resolves an incident to a `Location` entity.
- Licence enforcement: `redistributable` and `client_scope` on every provider; `osprey bundle`
  refuses non-redistributable data by name; CI rejects any non-`open` provider in the demo
  configuration.
- Geospatial reference-data connectors and the reference partition; `osprey seed --geo`.
- In-deployment geocoder resolving extracted place names against the gazetteer, written as
  `inferred` with a match score.
- Boundary overlays, and a drawn or selected boundary as a spatial filter.
- Server-side geo-binning, heat layer, clustering.
- Site geospatial: image upload, control points, drawn grid, grid cells as `Location` entities.
- Offline PMTiles path.
- Cross-filter wiring: timeline ↔ canvas ↔ map ↔ histograms, all directions.
- Filter panel with the histogram cross-filter pattern.

**Phase 5 known gaps (consolidated from Checkpoints 3a–3c's own implementation notes into one
list, so the next phase's scoping reads this instead of reconstructing it from three
checkpoints' worth of scattered notes).** Ordered roughly by how much unbuilt work each implies:

- **`MapProvider.endpoint` is asked to be two incompatible URL shapes at once, for a real RESTful
  WMTS service — found live by running `verify_map`, not assumed.** `services/api/tile_proxy.py`'s
  `build_upstream_url` needs it as a `{z}`/`{x}`/`{y}`-templated tile URL; `services/api/
  tier4_registration.py`'s `register_tier4_provider` (and `verify_map`'s own CRS check) needs it as
  a bare WMTS base URL it appends `?SERVICE=WMTS&REQUEST=GetCapabilities` to. Checkpoint 3b's and
  3c's own tests each passed in isolation because each used a differently-shaped `endpoint`
  fixture — the conflict only surfaced once both were run against the same live provider. **Not
  fixed.** A real WMTS KVP-encoding path (query parameters instead of path placeholders) would let
  both share one bare base URL; flagged in both modules' own docstrings.
- **There is no polygon-geometry storage anywhere** (`AnalyticsPort`/`GeometryRecord` is point-only).
  Two consequences, both unbuilt: rendering a real Boundary-Line-derived polygon as a map overlay,
  and filtering by *selecting* an existing jurisdiction boundary. Only the *drawn*, transient,
  browser-only boundary filter is built (`apps/workspace/src/map/BoundaryFilterTool.tsx`), since it
  needs no polygon storage. That drawn filter is itself scoped to the current working set (≤50k
  nodes, the same scope `MapView`'s own coordinate resolution already has), not every `Location` in
  the investigation — a server-side spatial predicate would be the scalable design for a very large
  investigation's `Location` population.
- **Tile prefetch is read-through-cache only.** `services/api/tile_cache.py` caches a tile the
  first time it's requested; `PrefetchCache.prefetch_areas` (warming a named area of operations
  ahead of time, a distinct feature from caching on read) is not built.
- **The in-deployment geocoder (`services/geocoder/match.py`) is not Splink-grade and cannot find
  its own candidates.** stdlib `difflib.SequenceMatcher.ratio()` on `Location.name` stands in for
  Fellegi-Sunter matching — proportionate to demonstrating the match-and-link mechanism, not a
  claim to be the real Splink integration (`services/resolve/`, still Phase 6). Candidate
  retrieval is explicitly the caller's job: `GraphPort.search_nodes` has no fuzzy name search, so
  there is no honest way for this module to supply its own candidates yet — Phase 6's extraction
  pipeline is the eventual real caller, and whatever search mechanism it builds is what closes
  this gap.
- **Tier-4 capabilities parsing covers WMTS only, not WMS/WFS/OGC API – Features** — a direct
  narrowing of the build-plan bullet's literal wording (line 194 above). Both shipped Checkpoint
  3a profiles (`providers/os-open-zoomstack.yaml`, `providers/usgs-national-map.yaml`) use
  `mvt`/`wmts`; WFS/OGC-Features capabilities describe feature types for entity creation (a
  gazetteer-connector-shaped job, not this phase's tile/zoom concern) and WMS's capabilities XML is
  a different shape needing its own parser. The same mechanism
  (`services/api/tier4_registration.py`) would extend to those formats later.
- **`kind: image`/`kind: dem` at the provider-registry level are not built.** Neither this
  bullet list nor `00_ARCHITECTURE.md` §1.2 names a schema field for an `image` provider's corner
  coordinates, and MapLibre's native `image` source needs them explicitly — it cannot read a
  GeoTIFF's own embedded georeferencing, and there is no GeoTIFF-parsing code anywhere in the repo.
  This is a different, unsolved input shape from the already-built Checkpoint 1 site-geospatial
  wizard (`site/siteLayer.ts`), which takes an analyst-uploaded plain image plus manually-placed
  control points. `kind: dem` has zero worked example anywhere in the docs. Both need a schema
  addition plus real image-processing work; no checkpoint in this phase owns that.
- **Smaller, lower-priority items:**
  - The tile-proxy endpoint template's credential placeholder is named `{credential}` —
    `services/api/tile_proxy.py`'s own naming choice; neither `MapProvider`'s schema nor this doc
    states how a tier-4 endpoint template should name its credential slot.
  - WMTS zoom range is read off a `TileMatrix`'s `Identifier` values directly — correct for the
    common `GoogleMapsCompatible` tile matrix set both shipped profiles use, not a general
    scale-denominator mapping for an arbitrary tile matrix set.
  - The map contrast-floor Verify check (`apps/workspace/map-verify/`) covers dark theme only —
    the light MapLibre style is a separate, already-named, not-yet-built follow-up. Its Playwright
    baseline screenshot (the first pixel-comparison test in the repo) was generated on macOS; a CI
    runner on a different OS needs its own baseline regenerated there once.

One item surfaced this phase was a genuine defect, not a gap, and **was fixed rather than
deferred**: the system-injected `SAME_AS` edge type declared no `properties` at all, so no
`SAME_AS` writer — including Splink's own eventual one — could ever have written the match score
`01_DOMAIN_MODEL.md` §4 itself requires. Found live while first verifying the geocoder against a
real ArcadeDB (a fake `GraphPort` unit test could not have caught it); fixed in
`packages/ontology/loader.py` (`_SYSTEM_EDGE_PROPERTIES`). Recorded here only so a future reader
doesn't mistake it for still-open.

**Exit.** Acceptance scenario A (`08_ACCEPTANCE_SCENARIOS.md`), **scoped to A1–A11**, passes end to
end on the tier 1 default provider with no network access, including the weekend and time-of-day
findings and the site-grid hotspot, without a code change specific to the scenario. Swapping the
default provider to tier 2 and re-running the scenario changes nothing analytically and `osprey
verify map` passes.

The full scenario, as originally written, is not satisfiable in phase order: A12 needs the Clique
Metric (`ComputePort`, Phase 7), and A13–A15 need Assessment objects, export and the handling gate
(Phase 8) — none of which exist yet when this phase lands. This is a correction to the scenario's
phase attribution, not a narrowing of what the platform must eventually do: A12 is re-proven
against this same HMP fixture when Phase 7 lands (its own exit criterion, below, says so), and
A13–A15 plus the full scenario end-to-end (including the retraction-propagates assertion after
A15) are exactly what Phase 8's "both acceptance scenarios pass unchanged" already implies. See
ADR-019 (`06_DECISIONS.md`) for why this was originally written as if Phase 5 alone completed the
scenario, and why splitting it across three phases is the correct fix rather than a workaround.

---

## Phase 5a — The Ingest Studio

**Outcome.** Someone who knows the data, and not the schema, can onboard a new source unaided.

- The five-stage studio over the Phase 2 recipe engine: Connect, Profile, Map, Verify, Publish.
- Row template canvas on the Sigma renderer; drag and keyboard binding; profiler-proposed
  mappings shown as proposals until confirmed; unmapped fields always visible.
- POLE-first element creation narrowing to a concrete type.
- Per-element match-on and on-match settings; Knowledge Adapter transform picker; no scripting.
- Verify: dry run rendering the graph it would produce, counts, and a grouped rejection report.
- Publish to version control with scheduling; recipe versioning with load attribution.
- Studio roles: source author, source approver, loader. Verify runs at the author's clearance.

**Exit.** A tester who has not seen the ontology maps the synthetic CDR fixture and a synthetic
financial fixture from scratch, using the studio only, and both verify clean. Editing the
ontology flags the affected recipes and blocks their scheduled runs. Every element loaded carries
the recipe version that produced it.

---

## Phase 6 — Extraction and resolution

**Outcome.** Unstructured material becomes graph, and duplicate people stop being duplicates.

- `adapters/model_litellm`, LiteLLM proxy, Ollama, faster-whisper, a vision model.
- Schema-constrained extraction for text, audio and image.
- The golden set and the precision/recall CI gate.
- `services/resolve` with Splink on DuckDB, configured from the ontology.
- `SAME_AS` writing; query-time projection at τ; the threshold slider with its change summary.
- Manual link and split; `explain` endpoint returning per-comparison match weights.
- Confirm/retract flow promoting `inferred` to `asserted`.
- Extraction profiles in the studio: POLE-class checklist generating the constrained-decoding
  schema, per-type confidence floors, adapter selection for extracted values.
- The review queue (`09_INGEST_STUDIO.md` §7): source and candidates side by side, span
  highlighting, per-candidate accept/reject/edit, retained rejections. No bulk accept.

**Exit.** Ingest a witness statement. Extracted entities appear as `inferred` with correct
source spans. Moving τ from Strict to Broad merges the expected clusters and reports the delta.
A manual split survives a subsequent resolution run that would have merged the pair, and the
conflict is recorded for review.

---

## Phase 7 — Analytics, patterns, alerting

**Outcome.** The remaining two analytical capabilities.

- `adapters/compute_rustworkx` and the browser worker tier.
- Degree, betweenness, eigenvector, clustering coefficient, Leiden, Clique Metric.
- `ComputePort` conformance across all three tiers on the 5,000-node fixture.
- Metrics panel with two-metric comparison; size encoding; community hull overlay.
- Visual query builder compiling to Gremlin builders, with result estimation.
- Hotlists, saved-pattern monitors, alert inbox with rule and evidence display.
- Pathfinder with access-filtered k-shortest paths.

**Exit.** Acceptance scenario B passes end to end. The Clique Metric ranks the insular-cluster
fixture node above the broad-hub fixture node, and all three compute tiers return identical
values within tolerance. A12 (Phase 5's exit criterion, scoped to A1–A11, deferred this one
step here per ADR-019) is re-proven against the same HMP fixture: the Clique Metric identifies
the same insular subgroup Phase 5 already surfaced by other means.

---

## Phase 8 — Assessment, export, and the second profile

**Outcome.** The platform produces an intelligence product, and runs on more than a laptop.

- Judgements, gaps and assumptions with evidence linking and the review-flag loop.
- The probability yardstick loader.
- Export: chart, subgraph, report. The handling gate with named blockers and recorded
  justification. Withheld-item manifest on every export.
- `adapters/graph_janusgraph` and `adapters/analytics_clickhouse`, both conformance-green.
- The browser harness and the admin console it becomes: the six setup screens, live preflight,
  the generated-artefact diff, and the backup, restore, upgrade and verify screens.
- Harness-driven orchestration (`05_DEPLOYMENT.md` §2.4): target confirmation, drift detection,
  change preview, enforced backup-before-switch, and downgrade capacity checks against the
  existing data volume.
- The headless CLI equivalent for every screen, so a deployment built by clicking is reproducible
  by a script.
- Generated Kubernetes manifests and the per-deployment runbook.

**Exit.** Both acceptance scenarios pass unchanged on `local-lite` and on `cluster`. A
`backup` → `restore` cycle across profiles reproduces the graph from staged Parquet. An export
containing an `S2`-marked item is blocked, names the item, and proceeds only with a recorded
justification.

---

## Standing rules for the whole build

1. **Conformance suites are written before adapters.** The suite defines the contract; an
   adapter written first will define the contract by accident.
2. **No feature ships without its access-control test.** Every read path gets a test asserting
   that an unauthorised principal cannot observe the data or infer its existence.
3. **Fixtures are synthetic and in-repo.** No real intelligence data in the repository, in CI,
   or in a demo. Generate fixtures with a seeded generator so they are reproducible. The same
   applies to map data: the demo and CI run on tier 1 providers only, enforced by rejecting any
   non-`open` provider in the demo configuration.
4. **The performance budget is a CI gate, not a report.** A regression fails the build.
5. **Every model-facing prompt is versioned and evaluated.** A prompt change runs the golden set
   and reports the delta on the pull request.
6. **The Glass never sees Gremlin, a raw node id from a source system, or an unfiltered count.**
7. **When an input document and this pack disagree, this pack wins and the disagreement is an
   ADR.** If you find one that is not recorded in `06_DECISIONS.md`, stop and record it before
   implementing either version.
8. **Each service gets its Dockerfile, and a `trivy image` CI scan, in the phase that creates
   it — never batched into Phase 8.** Phase 0's `trivy fs .` was always the interim measure,
   stated at the time ("since no image exists to scan until a service gains a Dockerfile. Add
   `trivy image` per service from the phase that containerises it") — this entry makes it a rule
   that does not depend on a later phase remembering to re-read Phase 0's parenthetical.
   `services/ingest` gets Phase 2's; each later phase's own service bullet list gets the same
   pair. An image scan turns up base-OS packages the service never touches with no upstream fix
   yet — `--ignore-unfixed` is the standard way to keep that from being permanent, unrelated
   noise on the gate, unlike the dependency-focused `trivy fs` scan, which does not use it.
