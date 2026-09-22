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

**Phase 2 known gaps (recorded 18 September 2026, during ADR-024's own work — not disclosed at
the time this phase closed, unlike Phase 5/5a/6's own gaps lists below, which is itself the
finding worth fixing here rather than only in a chat transcript):**

- **Only the CSV connector was built.** This phase's own outcome bullet promises "CSV, JSON and
  generic delimited"; `services/ingest/connectors/` holds `csv_connector.py` and a `geo/`
  directory (gazetteer/OSM connectors, a different concern) and nothing else. JSON and generic
  delimited never landed. `06_DECISIONS.md` ADR-024 depends on this: the ingest recipe engine's
  own row-template mechanism is the proposed home for a deterministic MSISDN↔IMSI `SAME_AS`
  write, and a device-extraction source is structurally exactly the kind of non-CSV format this
  bullet already promised and never delivered.

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
- **Three of this phase's own timeline bullets were deferred past it, and the deferral was
  disclosed only in `apps/workspace/src/timeline/Timeline.tsx`'s header comment, not here.** The
  bullet list above promises "Timeline: density strip, brush, playback, cyclical weekday × hour
  view, multi-track". Checkpoint 2 built the density strip, the brush and the cyclical view, and
  deferred `playback`, `multi-track` and the cross-case overlay (`02_GLASS_FRONTEND.md` §3.4) on
  the correct grounds that no A1–A11 step exercises them — but carried that into a component
  header rather than into this list, where it sat unread for four phases until Phase 7's own
  Scenario B audit found it. B16 and B18 each depend on two of the three, and are attributed to
  Phase 8 by ADR-022. Recorded here because this list exists precisely so the next phase's scoping
  reads it instead of reconstructing the position from three checkpoints' notes.
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

**Phase 5a known gaps (consolidated as each stage lands, the same discipline Phase 5's own list
above follows — so Publish's own scoping reads this instead of reconstructing it):**

- **Map's row template canvas binds by drag-and-drop only.** This bullet list's own line above
  promises "drag and keyboard binding"; the keyboard path (§4: "select both, press Enter") is not
  wired end to end — every other control on the screen (adding an element, changing a type,
  editing a binding, saving) is a plain focusable control reachable by Tab, so nothing is
  keyboard-*inaccessible*, only this one specific shortcut path is deferred. Disclosed in
  `apps/workspace/src/ingest/map/MapScreen.tsx`'s own module docstring at the point it was found,
  the same way `GlassCanvas.tsx` discloses its own curved-edge gap rather than shipping a silent
  partial version of the spec.
- **Map never proposes a starting template.** This bullet list's own line above promises
  "profiler-proposed mappings shown as proposals until confirmed" (§4: "For a recognised source
  shape it proposes the whole thing; for an unfamiliar one it proposes the bindings it is
  confident about"). What Map actually built is the *manual* half only — POLE-first element
  creation, per-element match-on/on-match, the transform picker, unmapped-field tracking — every
  binding is added and set by hand, with no auto-proposal step at all, confirmed or otherwise.
  Found auditing Publish's own closing pass (Publish's scope never touched Map), not disclosed
  when Map itself landed — recorded here now rather than left silent.
- **No synthetic financial fixture, and no second tester review.** The exit criterion above
  promises both a CDR *and* a financial fixture mapped from scratch by someone who hasn't seen
  the ontology, plus (§6, ADR-018) a second studio review once real data can be loaded through
  it. Only the CDR fixture (`tests/scenarios/fixtures/cdr.py`) exists; no financial fixture, and
  no second review, have happened. The first review (`docs/archive/SESSION_HANDOVER.md`, 15
  September 2026) covered the prototype against the CDR fixture only, before Verify or Publish
  existed.
- **Publish commits from the running Conduit process's own local checkout, not a shared
  remote.** `write_and_commit_recipe` (`services/api/studio_publish.py`) runs `git add`/`git
  commit` against `app.state.recipes_repo_root` — the checkout the process happens to be running
  from. That is the correct, and only sensible, behaviour for the single-instance dev deployment
  this phase targets; it is not yet correct for a horizontally-scaled deployment (`app.py`'s own
  statelessness proof) where two Conduit instances would each hold their own independent
  checkout, so a commit made against one is invisible to a Loader hitting the other. Making
  "the repository is the record" (§6) hold under that topology needs a push to a shared remote
  (or a single writable git-backed service Publish routes through) — real, undesigned work, not
  a stated deferral this phase already made a call about.
- **The ontology → dependent-recipe reverse index re-flags only on process restart.** §6's
  routine ("run whenever the ontology is reloaded") is real (`StudioRecipeStore.flag_stale`,
  called from `services/api/app.py`'s `lifespan`) and proven to actually block a flagged
  recipe's run (`tests/ingest/test_studio_publish_pipeline.py`), but this deployment has no
  live-reload admin action — "reload" only ever happens via a full process restart after a new
  `packages/ontology/default.yaml` ships. Fine for now (matches "the harness's admin console is
  Phase 8" already established for `revert_load`); a live "reload the ontology" trigger, if one
  is ever wanted without a restart, is unbuilt.
- **§8's "approve a mapping that changes an existing recipe's semantics" has no dedicated
  endpoint.** `POST .../versions` (source-author-gated) reopens a published/flagged recipe as a
  new draft version; publishing that version goes through the same `POST .../publish`
  (source-approver-gated) every other publish does. Reusing the one gate is a deliberate reading
  of §8's table, not an oversight — recorded here so a future reader doesn't go looking for a
  second "approve" route that was never meant to exist.

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

**Six stages, closed one at a time, the same discipline Phase 5a's own five stages followed:**
(1) `adapters/model_litellm` and schema-constrained text extraction, plus the LiteLLM/Ollama
dev-compose service; (2) audio (faster-whisper) and image (vision model) extraction; (3) the
golden set and the precision/recall CI gate; (4) `services/resolve` with Splink on DuckDB,
`SAME_AS` writing and the τ threshold projection — including the Working-Set Service wiring, the
`/v1/resolution/threshold` endpoint and delta computation, not deferred to a later stage, since the
exit criterion tests the wired behaviour rather than the projection function in isolation;
(5) manual link/split and the `explain` endpoint; (6) extraction profiles, the review queue, and
the confirm/retract flow promoting `inferred` to `asserted` — the studio-facing half of the phase,
and the one piece of the outcome list Stages 1–5 did not exercise: Stages 1–3 proved extraction
produces correctly-spanned `inferred` output at the `ExtractionResult` layer, but nothing wrote it
to the graph or gave a human a way to promote it.

**Phase 6 known gaps (consolidated as each stage lands, the same discipline Phase 5's and Phase
5a's own lists above follow):**

- **Stage 2 lands `transcribe()`/`describe_image()` for real** — `Systran/faster-whisper-tiny.en`
  behind `speaches` (audio) and `moondream:1.8b-v2-q4_K_M` behind Ollama (image), both pinned and
  conformance-tested the same way `extract()`/`embed()` are (`06_DECISIONS.md` ADR-020's Stage 2
  addendum has the full pin/mechanism detail). All four `ModelPort` methods are real as of this
  stage.
- **Diarisation is not implemented.** `TranscribeRequest.diarize=True` raises `NotImplementedError`
  rather than silently returning every segment's `speaker` as `None` as if diarisation had run and
  found nothing (`06_DECISIONS.md` ADR-020's Stage 2 addendum). Neither faster-whisper nor
  `speaches` do this natively; a real pipeline (e.g. `pyannote.audio`) is its own scoping decision,
  not assumed into Stage 2's default.
- **`describe_image()`'s own conformance case runs on a different CI cadence** than the other
  three `ModelPort` methods — merge-to-main only (`conformance-model-vision`), not every PR, since
  a vision-language model is materially heavier (1.8GB) than any of the other three pins. Split at
  the test-file level (`tests/conformance/model_port/test_suite_vision.py`), not only a CI job
  filter, so a contributor reading the suite sees exactly what runs on every PR without
  cross-referencing the workflow YAML. Full reasoning in `06_DECISIONS.md` ADR-020's Stage 2
  addendum.
- **`ModelPort.embed()` was found unowned by any stage, then resolved rather than left open**
  (`06_DECISIONS.md` ADR-020's addendum has the full reasoning). Checked directly before deciding:
  Stage 4's Splink resolution does not need it — the ontology's shipped `resolution` block
  declares only classical comparisons (`soundex`, `jaro_winkler`, `levenshtein`, `exact`), and
  Splink's own optional embedding-based comparison level expects a caller to supply vectors it
  does not compute itself, which nothing in the current ontology or Stage 4's scoping asks for.
  `embed()` is real from Stage 1 instead — `ModelLiteLLMAdapter.embed()` calls a second, much
  smaller pinned model (`all-minilm:22m-l6-v2-fp16`) through the same proxy, conformance-tested
  the same way `extract()` is. `03_CONDUIT_MIDDLEWARE.md` §5.1's "index — full text and embeddings
  into OpenSearch" step remains genuinely unowned by any phase — that gap is about the *consumer*
  (no OpenSearch adapter exists anywhere in this plan), not the `ModelPort` method. Recorded in
  full under "Gaps with no owning phase" below, not only here, precisely so it is findable by a
  reader auditing gaps rather than only one reading Phase 6 top to bottom — the same failure mode
  that let the witness-statement fixture drift unbuilt after being named in this same phase's own
  scoping.
- **The `ModelPort` conformance suite's own CI job (`conformance-model`) pulls a ~1–4GB Ollama
  base image on every run**, unlike the four stores `conformance`'s job already brings up. Accepted
  for Stage 1's text-only, small-model case; the heavier vision-model case landed in Stage 2 as
  planned here — its own slower CI cadence is the bullet above, not deferred further.
- **Stage 3 lands the golden set** (`tests/golden/`) — one hand-labelled case so far
  (`witness-statement-1`, folded in from Stage 1's own smoke-test fixture rather than a second
  document), gating on recall regression per `03_CONDUIT_MIDDLEWARE.md` §5.2/standing rule 5.
  **"Per entity type" is narrowed to "per schema-array-field"** — `tests/golden/harness.py`'s own
  docstring states this precisely: the spec's literal wording presumes Stage 6's ontology-driven,
  POLE-typed schema generation, which does not exist yet, so a "category" is whatever array-valued
  property a case's own caller-supplied `json_schema` declares (`persons_mentioned`, for the one
  case that exists), the same schema-agnostic shape Stage 1 already committed to. Revisit this
  narrowing once Stage 6 lands real per-type schemas.
- **Each golden case runs twelve times, not once, before its mean is trusted** — measured
  directly, not assumed: a single run's recall for the witness-statement case ranged from 0.0 to
  1.0, and even a five-run mean still varied batch-to-batch by roughly ±0.17. The CI gate's own
  regression tolerance (0.15, `tests/golden/test_golden_set.py`) is set from this same measurement,
  above the observed noise floor rather than at it.
- **The golden set measures the CI-pinned model's own regressions, not real extraction quality.**
  Stated explicitly in `tests/golden/harness.py`'s own docstring and `06_DECISIONS.md` ADR-020's
  Stage 3 addendum, not left implicit: the ~0.75 baseline recall is `qwen2.5:0.5b-instruct`'s own
  number, a model fourteen to twenty-eight times smaller than `03_CONDUIT_MIDDLEWARE.md` §5.2's
  named production default — reading it as "how well OspreyFlow extracts" would be a category
  error the doc now heads off directly.
- **A harness matcher bug, found while sanity-checking a suspicious result, not assumed to be
  model noise.** Two of the original zero/low-recall measurements were the golden-set's own exact
  matcher failing to recognise a correctly-identified entity (`dana_mercer`, `MERCER Dana`) — fixed
  by normalising separator characters and word order before comparing, still exact-after-
  normalisation rather than fuzzy. Full before/after in `06_DECISIONS.md` ADR-020's Stage 3
  addendum. A genuine partial-extraction miss (a bare surname with no forename) was left
  unnormalised deliberately — fixing that would mean substring matching, which is Stage 4's
  Splink job at query time, not this harness's.
- **Stage 4 lands `services/resolve`, real from the ontology to a wired τ endpoint** — a genuine
  licence conflict was found and resolved before any of it could be built: `splink`'s current
  stable/pre-release lines (4.x/5.x) pull in `igraph`, which is GPL, failing `make licence-check`
  outright. Pinned to `splink==3.9.9` instead (`06_DECISIONS.md` ADR-021 has the full finding and
  the cost of that pin — a different, older API surface). The ontology's `resolution: {blocking,
  comparisons}` closed function registry (`packages/ontology/resolution_functions.py`) is
  validated at ontology-load time, not Splink-setup time, per this phase's own original scoping.
  `SAME_AS`'s ontology-declared properties grew from `score` alone to also carry `model_version`/
  `comparison_vector` (`packages/ontology/loader.py`), closing the rest of the gap
  `01_DOMAIN_MODEL.md` §4 always asked for. The τ projection (`services/resolve/projection.py`)
  is pure and unit-tested standalone; `WorkingSetService.set_resolution_threshold` is the wired
  caller, exactly as this phase's own scoping insisted on rather than deferring the wiring to
  Stage 5.
- **No m/u training**, given its own ADR treatment (`06_DECISIONS.md` ADR-021's 18 September 2026
  addendum) rather than left only in a code docstring, since it is a real match-quality trade-off
  across the whole resolution system, the same category of call as ADR-006's query-time-projection
  decision. Splink's `comparison_library` defaults produce sensible `match_probability` values
  with no `estimate_u_using_random_sampling`/EM step at all; per-investigation EM training would
  need "a few hundred, preferably thousand" comparisons Splink's own guidance asks for — far more
  than a typical investigation's own Person population has. This was not accepted on the design
  argument alone: `tests/resolve/test_resolution_accuracy.py` checks six hand-labelled pairs
  (identical, case-varied plus abbreviated given name, misspelled-surname soundex block,
  given-name typo, two negative controls) against the real ontology config and the untrained
  defaults, the same fixture discipline `tests/scenarios/fixtures/cdr.py` established. Building
  that check found and fixed two real defects in `services/resolve/resolver.py` — DuckDB's
  `jaro_winkler_similarity` is case-sensitive (`'MERCER'` vs `'Mercer'` scored `0.44`, not `1.0`,
  silently near-certain-non-matching a same-person pair differing only in case) and the DataFrame
  builder omitted blocking-only columns — both now fixed and covered. All six pairs now land
  correctly; the ADR addendum records the honest cost this doesn't buy (uncalibrated, only
  directional, probabilities) and a "revisit if" clause tied to population size. Deployment-wide
  model training against a real historical corpus, with its own persistence and retraining story,
  is real, undesigned work — not assumed into this stage.
- **Stage 5 lands manual link/split, `explain`, and resolution-conflict recording.**
  `WorkingSetService.manual_link`/`manual_split` write a real `SAME_AS` (score 1.0)/`NOT_SAME_AS`
  edge through `GraphPort` in a transaction (`01_DOMAIN_MODEL.md` §4's own wording for both),
  then reproject the working set at the session's current τ and return the same `DeltaReproject`
  shape `set_resolution_threshold` already established. `explain_cluster`
  (`GET .../resolution/explain/{cluster_id}`) returns every direct `SAME_AS`/`NOT_SAME_AS` edge
  between a cluster's current members — including sub-threshold ones that only matter because a
  transitive chain pulled the pair together — with score, model version, comparison vector and a
  `manually_asserted` flag, satisfying `03_CONDUIT_MIDDLEWARE.md` §3.5's "return the per-comparison
  match weights, not just the total."
  `services/resolve/conflicts.py`'s `detect_conflicts`/`same_as_writer.record_conflicts`
  supersede the existing `NOT_SAME_AS` edge with `conflict_pending`/`conflict_score`/
  `conflict_model_version`/`conflict_comparison_vector` properties when a fresh candidate would
  have merged a manually split pair, closing the second half of
  `03_CONDUIT_MIDDLEWARE.md` §5.3's "a later run... records the conflict for review" (Stage 4
  only closed the first half: refusing to act on it).
  **Two things here are this build's own design, not spec text, flagged rather than presented as
  spec-mandated:** the `ResolutionConflict` record's shape (§5.3 names the behaviour, never the
  fields a recorded conflict must carry — see `conflicts.py`'s own docstring), and the "would have
  merged" bar being `THRESHOLD_BROAD` (0.80), the lowest of the three official detents, rather
  than a session-specific τ, since conflict detection runs corpus-wide, outside any one
  investigation's session. Both were checked, not assumed: this bar started as `DEFAULT_THRESHOLD`
  (Balanced, 0.95) in an earlier draft of this stage, which had a real, silent gap — a candidate
  scoring between Broad and Balanced could merge for an investigation actually running at Broad
  without ever being flagged. Broad is the correct single value instead: merging is monotonic in
  score, so Broad is the one bar that catches every candidate that could merge under *any* of the
  three supported settings. Flagged to the user as an arbitrary-vs-principled call in the same
  category as ADR-020's model pin, and corrected before landing — `06_DECISIONS.md` ADR-021's
  second Stage 5 addendum has the full decision record.
- **No proactive conflict-discovery surface.** Nothing lists "all pending conflicts" for an
  investigation or the corpus. An analyst who already suspects a pair needs review can query
  `explain`/the graph directly for `conflict_pending = true` on a `NOT_SAME_AS` edge; nothing
  surfaces that to them unprompted. A review-queue-style endpoint over pending conflicts is real,
  undesigned work, deliberately not built this stage.
- **No corpus-wide resolution job trigger exists yet — a gap that has been true since Stage 4,
  only now made explicit.** `resolve_entity_type`/`write_same_as_edges`/`detect_conflicts`/
  `record_conflicts` are real, tested, callable functions, but nothing in this build schedules or
  triggers a run of them against the live corpus — no ingest hook, no cron, no manual "resolve
  now" endpoint. Every test of this pipeline (`tests/resolve/*`) calls it directly. Building that
  trigger is real, separate work (what runs it, how often, against what population) that neither
  Stage 4 nor Stage 5 was scoped to include.
- **`ResolutionState.manually_linked`/`manually_split` (`packages/schemas/domain.py`) remain
  unpopulated.** These per-node convenience fields predate this phase; populating them correctly
  would mean writing them onto the permanent Vault node via `GraphPort.supersede_node` (a heavier,
  edge-repointing write), whereas the actual permanent record of a manual decision is the
  `SAME_AS`/`NOT_SAME_AS` edge itself, which `manual_link`/`manual_split` already write. Left
  unpopulated deliberately rather than half-populated only in the ephemeral working-set copy,
  which would silently vanish on the next fresh `expand()`/`seed()` and misrepresent permanence
  the field's name implies.
- **Stage 6 lands `services/extract` (profile → schema generation, candidate extraction/span
  location, the graph writer, confirm/retract) and `services/api/review.py` (the Postgres-backed
  review queue, mirroring `studio_recipes`'s own registry pattern).** `09_INGEST_STUDIO.md` §7's
  "extraction produces candidates, not graph" is literal here: `run_extraction` never touches
  `GraphPort`; only `accept_candidate` does, writing `provenance.state = inferred`, never
  `asserted` — accept and confirm are different actions (`services/extract/writer.py`'s own module
  docstring), the only reading consistent with `CLAUDE.md` rule 5's "no automatic promotion" and
  with this phase's own exit criterion naming `inferred` as what extraction produces. Confirm/
  retract go through `GraphPort.supersede_node` — not invented for this stage: that method's own
  docstring already named "Phase 6's retraction" as one of its two intended callers, written back
  when the port itself was built. An explicit test
  (`tests/services/api/test_review_routes.py::test_confirming_a_node_does_not_touch_an_unrelated_conflict_flagged_edge`)
  proves confirming a clustered entity cannot reach a `NOT_SAME_AS` edge's `conflict_pending`
  property — confirm/retract only ever call `get_node`/`supersede_node` against the target node id.
- **Edge/relationship candidates are not built — and this is a match against the phase's own
  literal exit criterion, not a convenient narrowing that happens to line up with it.** This
  phase's `**Exit.**` paragraph reads in full: "Ingest a witness statement. Extracted entities
  appear as `inferred` with correct source spans. Moving τ from Strict to Broad merges the
  expected clusters and reports the delta. A manual split survives a subsequent resolution run
  that would have merged the pair, and the conflict is recorded for review." It names *entities*
  exactly once and never names an edge or a relationship anywhere in that text — the checkable
  acceptance bar Stage 6 had to clear was always entity-only. The broader outcome bullet
  ("Unstructured material becomes graph") and `09_INGEST_STUDIO.md` §7's own mockup (which shows
  "Proposed links", e.g. an `ALLEGED_THREAT` edge between two extracted people, alongside entity
  candidates) are more expansive than the exit criterion actually tests, and edge candidates
  remain real, undesigned future work against that broader ambition — but Stage 6 is not falling
  short of what it was graded against. Separately, and not as the primary reason: building edge
  candidates now would also need a `GraphPort.get_edge` method that does not exist — adding one is
  a real port change needing its own conformance-suite coverage (`CLAUDE.md` rule 1) — but that
  constraint is incidental to the scoping decision, not the justification for it.
- **No persisted, versioned extraction-profile registry.** Unlike `studio_recipes` (§6), a profile
  is inline, caller-supplied configuration on each extraction run, not a database row with its own
  draft/publish lifecycle — nothing in the Phase 6 outcome bullet asks for that, only the
  schema-generation capability itself (`services/extract/profile.py`'s own module docstring).
- **The review queue has no new studio-specific role layered on top of ordinary access control —
  it is not ungated.** To be precise about which of two different claims this is: `run_extraction`/
  `accept_candidate`/`reject_candidate` are real, tested access-control boundaries — every route
  carries `AuthorizedInvestigationDep` (403/404s a principal outside the investigation's own
  `owning_unit`, `tests/services/api/test_review_routes.py`'s own denial tests), and
  `ExtractionCandidateStore.get_authorized` independently re-checks the *candidate*'s own
  `owning_unit` against the caller a second time. What is genuinely absent is a *third*,
  finer-grained layer: `09_INGEST_STUDIO.md` §8's role table (`source_author`/`source_approver`/
  `loader`) is entirely about the structured Connect/Map/Publish/Load workflow and names nothing
  for reviewing unstructured extraction candidates, so any principal already authorized on the
  investigation can run extraction and accept/reject — there is no `require_studio_role`-style
  restriction narrowing that further, the way publishing a recipe is restricted to
  `source_approver`. This is a disclosed reading of a silent table, standing rule 2's own
  access-control test discipline fully applied to the boundary that does exist, not a gap in it.
- **Extraction confidence is the model's own self-report, uncalibrated with the CI-pinned tiny
  model** — the same disclosed-limitation class as ADR-021's no-EM-training addendum, and worse
  than merely uncalibrated: checked live against the real model, not assumed, `qwen2.5:0.5b-
  instruct` reports confidence on an unpredictable mix of 0..1, 0..10 and 0..100 scales from one
  call to the next for extractions of comparable actual quality (`1`, `0.8`, `8`, `14`, `92`,
  `150` observed directly across ten runs of the same document). Two real defects were found and
  fixed because of this, not merely disclosed around: `profile.py`'s schema first constrained
  `confidence` to `{"minimum": 0.0, "maximum": 1.0}`, which made constrained decoding *retry and
  fail the entire extraction* (`ExtractionFailedError`) whenever the model reported a value outside
  that range, rather than merely miscalibrating — the bound was dropped from the schema entirely.
  `candidates.py` now normalises defensively (treats `>1.0` as a percentage, then clamps to
  `[0.0, 1.0]`), which recovers the common 0–100 case but not the 0–10 one — a genuine, disclosed
  residual gap, not silently papered over. Nothing in `services/extract` further corrects or
  calibrates the underlying self-report; the per-type confidence floor filters against whatever
  survives normalisation, honestly, not against a verified figure.
- **No Glass/frontend screens** for the extraction-profile checklist or the review-queue UI —
  backend/API only, consistent with every other Phase 6 stage.
- **`ollama` (Stage 1+) shares this host's Docker VM memory budget tightly enough with ArcadeDB to
  OOM-kill it (exit 137), reproduced repeatedly running Stage 6's own live tests.**
  `deploy/compose/dev.yaml`'s `arcadedb` service already carries two dated notes on this exact
  failure mode from earlier phases (two concurrent conformance suites; one heavy sequential HMP
  build); this is a third, environment-level cause (cross-container contention with `ollama`'s own
  resting footprint, introduced by Phase 6 itself) recorded there rather than only here, so it
  does not have to be rediscovered from scratch. **A fourth occurrence, recorded here rather than
  rediscovered again:** the container was OOM-killed a second time while writing Phase 6a's own
  closing-pass scenario test (running it alongside `test_phase3_working_set.py`'s and this file's
  own `test_phase6_exit_criterion_end_to_end` in the same session) — same exit 137, same cause.
  After restart, `test_phase6_exit_criterion_end_to_end` specifically (its own `arcadedb_adapter`
  fixture, which provisions a fresh `conformance_*` database per run) failed intermittently on a
  different randomly-affected type each retry (`Error on creating index on type 'mx_Vehicle'`,
  then `'mx_Organisation'`, then `'mx_Event'` — three different types across three consecutive
  attempts, including after a full `docker restart`), suggesting the OOM-kill leaves the server
  in a degraded state schema/index creation is sensitive to, beyond the immediate crash itself —
  not something a restart alone reliably clears. Not investigated further here, since it is this
  host's own resource budget rather than anything Phase 6a's own scenario touches: the new
  closing-pass test (`tests/scenarios/test_phase6a_glass_surfaces.py`, below) does not use
  `arcadedb_adapter` at all — it reads/writes the long-lived `ospreyflow` database directly, the
  same database the Conduit itself runs against — and passed consistently across every one of
  these events.

**Phase 6 exit criterion, verified end to end after Stage 6 closed it.** All three clauses
together, against the live stack (real LiteLLM/Ollama, real Postgres, real ArcadeDB, real
DuckDB/Splink) rather than trusting each stage's own tests to add up correctly — the same closing
pass Phase 5a's own Publish stage did for its acceptance scenario. See `tests/scenarios/
test_phase6_extraction_and_resolution.py`.

---

## Phase 6a — The analyst-facing surface over extraction and resolution

**Outcome.** Everything Phase 6 shipped as an API only becomes something an analyst can use,
the same relationship Phase 5a had to Phase 2's headless recipe engine (ADR-018).

**Read first:** `02_GLASS_FRONTEND.md` §2 (workspace layout — the Inspector's own spec'd tabs are
"Properties, Provenance, Relationships, Judgements, Source document"; nothing named "Resolution,"
so B9/B10/B11's controls need a real placement decision, not an assumed tab), §1.1/§4 (node-state
vocabulary — nine channels, three provenance strokes, six interaction states, and a *separate*,
already-built sense of "cluster": §1.1's zoom-dependent *community* clustering is a data
operation, not this phase's concern, and must not be confused with resolution's own `ClusterId`,
which has no rendering convention at all yet — deciding one is this phase's own work), and §5
(performance budget — a CI gate, not a target; "node hover to inspector populated < 100ms" is the
one figure these four screens could threaten if any attaches to the existing Inspector rather
than a new surface).

**Two dependencies, answered here rather than discovered mid-stage.**
- **Does this phase depend on ADR-025's corpus-wide trigger landing first? No.** Stage 1 below
  (manual link/split) needs no pre-existing `SAME_AS` edge — it creates one from any two
  analyst-selected nodes directly. Its own output is the seed data Stages 2 and 3 need. Phase 6a
  is fully self-sufficient; it does not wait on Phase 7's own, much larger, trigger
  infrastructure (ADR-025), and no analyst review needs to either.
- **What would a reviewer actually see, given ADR-024's device-extraction mechanism is unbuilt?**
  The manual-link-seeded flow below demonstrates the *generic* resolution UI — threshold,
  `explain`, manual link — working correctly against any `SAME_AS` edge, regardless of how it was
  written. It does **not** demonstrate ADR-024's own specific claim (a device extraction reporting
  an MSISDN and an IMSI together writes the link automatically) — that connector does not exist
  (this document's Phase 2 known-gaps list and its `Gaps with no owning phase` entry both record
  it). B15's *imsi→Device* leg is demonstrable end to end (`PAIRED_WITH`, already
  conformance-tested); its *msisdn→imsi* leg is demonstrable only by manual assertion in this
  phase's own review, not by the automatic mechanism ADR-024 describes, until that connector
  lands. A reviewer is told this directly, not left to infer it.

**Stages, closed one at a time, the same discipline Phase 6/5a followed:**

1. **B11 — manual link/split.** Smallest, most contained: a canvas/context-menu action
   (`RadialMenu`, already built) on two selected nodes, calling the existing
   `POST .../resolution/link`/`split`. No new design-system primitive needed. Closes first
   because its own output seeds Stages 2 and 3.
2. **B9 — resolution threshold control. Built: three fixed detents (`ResolutionThresholdControl`,
   `apps/workspace/src/resolution/ThresholdControl.tsx`), reusing `Slider` with a new, disclosed
   `onCommit` prop (commits on release, not on drag — `PUT .../resolution/threshold` re-projects
   the whole working set) and an App-level `Toast` summary.** Scoping this stage surfaced two
   access-control gaps neither `_manual_assertion`'s own Stage 1 fix nor `explain_cluster` had
   closed — both fixed here, not deferred, and both folded into the `FakeGraphPort` gaps entry as
   instances three and four of one pattern (`Gaps with no owning phase`, above): `set_resolution_
   threshold`/`_manual_assertion` clustered the investigation-*shared*, unfiltered node population
   rather than the principal-visible subset (a write-path bug — a principal blind to a node could
   silently reset its persisted `cluster_id` — proved against the real adapter in `tests/services/
   api/working_set/test_resolution_threshold_access_control.py`), and `explain_cluster` returned a
   hidden node's own id verbatim in `member_node_ids` (`tests/services/api/working_set/
   test_explain_cluster_access_control.py`). `DeltaReproject`/`ClusterDelta` grew
   `affected_cluster_ids` (bounded by `affected`) so the Glass applies cluster moves in place
   (`workingset/store.ts`'s `applyReproject`) instead of re-syncing the whole working set.
   Rendering, proposed since `02_GLASS_FRONTEND.md` has no existing convention for resolution
   collapse: same-cluster nodes co-locate at the cluster's own anchor and get a second, independent
   `@sigma/node-border` ring (`canvas/nodeAttributes.ts`'s `computeClusterGraphAttributes`) —
   distinct from the interaction-state ring, so both can show at once. Measured, not assumed:
   `compute_clusters`+`diff_clusters` over the full 50,000-node cap, worst case (every node
   collapsing into one cluster in a single call), took 0.056s (`tests/resolve/
   test_projection_perf.py`) — this path is not where a reprojection's cost lives; `GraphPort.
   expand`'s own network/traversal cost at that scale is unmeasured here and remains the open
   question if a real demo shows the control feeling slow. **Not built:** a WebSocket-level
   integration test proving `affected_cluster_ids` round-trips through the real Conduit — the
   harness's own `seedOneNode` cannot seed a real `GraphPort` node (see the `Gaps with no owning
   phase` entry above), so this is proved at the Python service layer against the real adapter
   instead. Demonstrated against the `SAME_AS` Stage 1 created.
3. **`explain` rendering (B10). Built: a cluster-aware "Explain cluster" radial-menu item
   (single-node trigger — `explain` takes one `cluster_id`, not a pair) opening
   `ClusterExplainOverlay`, a transient `Popover` (modelled on the existing edge-inspection
   overlay) containing the `Table` primitive.** Scoping this stage surfaced a rendering-layer
   question the Stage 2 API fix doesn't answer by itself: what the *table* does with a node id,
   independent of whether the API was correct. Answer, built and tested: `visiblePairs`
   (`apps/workspace/src/resolution/explainView.ts`) requires a pair's both endpoints to be *both*
   in the response's own `member_node_ids` *and* already present in this session's local graph
   before rendering it at all — belt and braces against a legitimately-visible member not yet
   synced to this client, or a future regression, dropping the row entirely rather than showing it
   redacted (`explainView.test.ts`, plus a keyboard-level render assertion, not just a network-call
   one). A manually-asserted pair's "Basis" column branches on `manually_asserted` before ever
   reading `score`/`model_version`, so it reads "Asserted by analyst" by construction, never as
   blank data (`explanationBasis`). Rule 13: `keyboard.spec.ts` gained a case proving the new
   action reachable and activatable, and the harness fixture gained the `resolution.cluster_id`
   data needed to exercise it — it had none before. `make glass-a11y` re-run after adding a
   representative sample of the new "Basis"/"meets τ" cell patterns to `a11y/showcase.tsx` (the
   only way its fixed-page scan reaches new content); both themes pass. Standing rule 2: the
   access-control test for this read path is `test_explain_cluster_access_control.py`, written in
   Stage 2 when this method's own node-disclosure bug was found and fixed — cited here rather than
   duplicated, since the Stage 2 threshold test does not cover it and the new frontend test above
   is a different concern (the render boundary) from the API's own access control. Rendering
   convention recorded in `02_GLASS_FRONTEND.md` (added alongside Stage 2's own, likewise
   never written into that document before now). Demonstrated against the same seed as Stage 2.
4. **B6 — the Dossier. Built: a wholly new Glass surface** (`apps/workspace/src/dossier/`;
   `00_ARCHITECTURE.md` names the Dossier as its own component alongside Canvas/Timeline/Map/
   Query, not an Inspector tab) — the same shape of work Phase 5a's own Map screen was over Phase
   2. The backend data this needed did not fully exist before this stage: `run_extraction`'s own
   `text` argument was discarded after building candidates, so `services/api/review.py` gained a
   small `owning_unit`-scoped document-text store (`store_document_text`/`get_document_text`,
   the same query-level `WHERE owning_unit = $2` shape `get_authorized` already uses, so an
   unauthorised principal 404s identically whether a document never existed or simply isn't
   theirs). **A second gap, standing rule 12's own kind, found while writing this stage's tests
   rather than left for a later one:** every test written so far called `store_document_text`
   directly; none called it through `run_extraction`, the only real caller — deleting
   `run_extraction`'s own call to it left every existing test green. Closed with
   `test_run_extraction_persists_the_document_text_the_dossier_later_renders`
   (`tests/services/api/test_review.py`, against the real store that file already uses),
   reverted and confirmed failing before the fix, per standing rule 2. `services/api/dossier.py`
   assembles a document's text with the subset of its
   **accepted** extraction candidates the requesting principal can currently see — pending/
   rejected candidates stay the still-separate, still-unbuilt review-queue screen's own concern
   (`09_INGEST_STUDIO.md` §7), not this stage's. **A third independent copy of the "narrow node
   ids to what a principal can see" pattern, closed rather than added:** `set_resolution_
   threshold` and `explain_cluster` (instances three and four, `Gaps with no owning phase` above)
   each still inlined that logic independently; the Dossier's own assembly would have been a
   fourth. Extracted instead into `services/api/access.py`'s `narrow_to_visible`, and both
   existing call sites retrofitted to it — verified unchanged by the existing threshold/explain
   test suites, which still pass. A span naming a node the principal cannot see is omitted from
   the response entirely, never rendered redacted — the same rule Stage 3's `visiblePairs`
   established one surface over (`tests/services/api/test_dossier_access_control.py`, reverted
   and confirmed failing before the fix, per this build's own standing discipline). Frontend:
   `HighlightedMessage.tsx` renders each span as a native, focusable `<button>` — colour and
   rendering convention recorded in `02_GLASS_FRONTEND.md` §1.1, alongside Stage 2/3's own,
   likewise never written into that document before now; `Dossier.tsx` reads the selected node's
   own already-synced `provenance.sources` rather than a new backend call to discover which
   documents mention it. Trigger: a new "View messages" radial-menu item, `Endpoint`-type nodes
   only (B6's own wording).

   **The keyboard-action-registry decision (`Gaps with no owning phase` above) is decided here:
   built, not deferred.** `apps/workspace/keyboard/actionRegistry.ts` — a plain list of
   `GlassCanvas`'s own action ids, `registerCovered(id)` called at the point each `keyboard.
   spec.ts` case actually proves one, and a final test asserting every registered id was covered.
   Rule 13 alone had already let four actions go untested entirely on its own before this stage
   added anything, checked directly rather than assumed: ring-cycling (a second `Tab`), the
   `"manual-split"` item, the per-edge-type item exercised through the menu itself rather than
   only `Enter`'s own shortcut, and dismissing either transient overlay at all. All four retrofitted
   here, alongside the new Dossier case, rather than left red against a newly-built gate (standing
   rule 9). **A real bug, found while retrofitting the fourth case, fixed as part of it — not left
   disclosed-only:** confirmed against a running browser, not assumed from reading the container's
   own `onKeyDown`, that `Escape` never reached `EdgeInspectionOverlay`/`ClusterExplainOverlay`'s
   own close button at all — opening either from a radial-menu item leaves focus nowhere (the
   menu's own `<button>` unmounts on select, dropping focus to `<body>`, past the container
   entirely), so a handler that only fires while the container itself has focus never ran. Fixed
   in `Popover` (the shared base both overlays render through, so this is fixed once rather than
   per overlay): the same self-contained mount-focus-and-`document`-level-`Escape`-listener shape
   `RadialMenu` already had. `make glass-keyboard` (twelve cases, all newly passing) and
   `make glass-a11y` (both themes, after adding a representative highlighted-message sample to
   `a11y/showcase.tsx`) both re-run clean.

**Exit.** Acceptance scenario B's B6, B9, B10 and B11 (ADR-022) pass end to end against Phase 6's
existing API. Moving the threshold control from Strict to Broad in the Glass produces the same
merge and change summary `WorkingSetService.set_resolution_threshold`'s own test already proves at
the service layer. A manual link made from the interface is indistinguishable, once written, from
one made through the API directly. **If the analyst review (ADR-018's own precedent: put the
screens in front of someone who hasn't built them) has not taken place by the time the automated
criterion above is met, that is recorded in this phase's own known-gaps list and does not block
Phase 7** — the same disclosure Phase 5a's own unmet second review already carries
(`07_BUILD_PLAN.md` Phase 5a known gaps, "no synthetic financial fixture, and no second tester
review"), not a new pattern. Naming a review does not make it happen; what this phase commits to
is that the review's status — done, or disclosed as outstanding — is true and checkable at close,
not that its completion gates anything downstream.

**Phase 6a known gaps (this list did not exist before this phase's own closing pass — it is
created here, not merely populated, the same way Phase 5's and Phase 5a's own lists above were
each created once by the stage that first needed to disclose something):**

- **The analyst review named in the Exit paragraph above has not happened.** The demo was
  deliberately deferred until after the build — the Exit paragraph's own clause explicitly permits
  this, provided the status is disclosed honestly rather than left unrecorded, which is what this
  bullet is. The four screens are built, and automatically verified at three separate levels:
  each stage's own unit/keyboard/a11y tests, and now `tests/scenarios/
  test_phase6a_glass_surfaces.py`'s closing pass proving B6/B9/B10/B11 compose correctly in one
  session against the live stack. No analyst who did not build them has used them. **What this
  proves, stated at the strength it actually supports and no further: the screens work — the API
  they call is correct, access-controlled, and composes end to end. It does not prove the screens
  are usable** — that a real analyst's workflow fits what got built, that the four-screen split
  (Inspector vs. a new Dossier surface vs. transient overlays) reads as intended, that "View
  messages" is where someone would actually look for it. Automated correctness and human usability
  are different claims; this phase can honestly make only the first until the review happens. Same
  disclosure shape Phase 5a's own unmet second review already carries — not a new pattern, a
  repeated one, which is itself worth noticing rather than treating each occurrence as a one-off.
- **No literal browser-driven test exists for any of B6/B9/B10/B11 — the closing pass proves the
  API surface, not a rendered Glass.** Checked directly before writing the closing pass, not
  assumed: every existing Playwright suite in this repository (`keyboard/`, `a11y/`, `perf/`,
  `map-verify/`) boots an isolated Vite harness with `page.route` intercepting every network call —
  none of them drive a live Conduit. Building that combination (a live auth-token flow reaching the
  browser, a live Conduit alongside Playwright's own `webServer`, CORS) is real, unscoped test
  infrastructure work with no existing pattern to extend, not a natural next step from
  `keyboard.spec.ts`. This is a narrower, more specific version of the analyst-review gap above:
  even a scripted, non-human agent has never operated these four screens through a browser against
  real data — only against the API directly, or against a mocked network.
- **The Dossier's own existence-leak answer is confirmed identical to Stage 3's `explain` answer,
  not different — checked directly, not assumed.** `services/api/dossier.py` omits a span naming a
  node the requesting principal cannot see, exactly the same "omit, never redact" rule
  `explainView.ts`'s `visiblePairs` already established for a pairwise comparison row
  (`02_GLASS_FRONTEND.md` §1.1's own "Highlighting" paragraph states this plainly, and
  `tests/services/api/test_dossier_access_control.py` proves it against the real adapter,
  reverted-and-confirmed-failing per standing rule 2). Recorded here explicitly, as a settled
  question rather than an open one, so a future reader doesn't have to re-derive whether the
  Dossier's own answer might diverge from the surface Stage 3 already closed.
- **The keyboard-registry retrofit found exactly one real defect, not four.** Of the four
  previously-uncovered `GlassCanvas` actions the registry surfaced (ring-cycling, the
  `"manual-split"` item, the per-edge-type item via the menu, dismissing a transient overlay),
  three were simply untested and already correct once a case was written for them. Only the
  fourth — `Escape` never reaching `EdgeInspectionOverlay`/`ClusterExplainOverlay`'s own close
  button, because opening either from a radial-menu item drops focus to `<body>` past the
  container entirely — was a genuine, user-facing defect, fixed in `Popover` (this phase's own
  "Built" bullet above has the full account). Stated precisely rather than left to imply the
  registry's yield was larger than it was.
- **`resolution/threshold`'s own "move the threshold and see the merge" clause is demonstrated by
  this phase's closing pass in a narrower, honestly-stated form.** `tests/scenarios/
  test_phase6a_glass_surfaces.py`'s own module docstring has the full mechanical account: a
  manual link's `score=1.0` exceeds every valid τ, so its merge and change summary appear in B11's
  own response, not in the subsequent `PUT .../resolution/threshold` call — which, correctly,
  reports zero further change. A fresh Strict-to-Broad transition on a genuinely
  intermediate-scoring, Splink-produced pair is `test_phase6_exit_criterion_end_to_end`'s own
  clause 2, already proven separately; this phase's own closing pass does not repeat it, and a
  reader should not assume B9's presence in the B11→B9→B10→B6 chain demonstrates a threshold-driven
  transition specifically — it demonstrates the mechanism running for real against a state B11
  already produced, and that state surviving the move unchanged.

**Phase 6a exit criterion, verified end to end after Stage 4 closed it.** B11, B9, B10 and B6
together, in that order, in one investigation, as one principal, against the live stack (real
ArcadeDB, real Postgres) — the same closing-pass discipline Phase 6's own Stage 6 and Phase 5a's
own Publish stage each followed for their acceptance scenarios, rather than trusting four stages'
worth of individually-passing tests to compose correctly. See `tests/scenarios/
test_phase6a_glass_surfaces.py`.

---

## Phase 7 — Analytics, patterns, alerting

**Outcome.** The remaining two analytical capabilities.

- `adapters/compute_rustworkx` and the browser worker tier.
- Degree, betweenness, eigenvector, clustering coefficient, Louvain (Leiden is unavailable on
  either compute tier — `06_DECISIONS.md` ADR-029), Clique Metric.
- `ComputePort` conformance across two tiers (Tier 1 graphology, Tier 2 `rustworkx`) on the
  5,000-node fixture — Tier 3 registers in Phase 8a's `cluster` profile instead (`06_DECISIONS.md`
  ADR-028).
- Metrics panel with two-metric comparison; size encoding; community hull overlay.
- Visual query builder compiling to Gremlin builders, with result estimation.
- Hotlists, saved-pattern monitors, alert inbox with rule and evidence display.
- Pathfinder with access-filtered k-shortest paths.
- The corpus-wide resolution and alerting trigger (ADR-025, `06_DECISIONS.md`): a new
  `GraphPort` method to list a type's population (conformance-suite-first, standing rule 1);
  this system's first job-queue worker, generalised rather than resolution-specific so it also
  closes `services/api/supersede.py`'s own long-disclosed "no worker attached yet" gap; the
  post-ingest hook `run_recipe` needs to submit a scoped resolution job; a manual "resolve now"
  route mirroring `submit_supersede_node`'s sync-vs-job split; and a status-bar conflict-count
  notice, since an automatic run generates `conflict_pending` edges nobody asked to see.

**Priced, not just added — the assessment ADR-022's own precedent calls for.** Before the trigger
bullet above, this phase already carried three `ComputePort` tiers with two of its own unresolved
environment questions (`NEXT_STEPS_PHASE7.md`: how a Python-`pytest` conformance suite exercises
a browser Web Worker for Tier 1; whether Tier 3's Spark/HugeGraph is even feasible on this host's
already-tight Docker VM budget), the metrics panel, the visual query builder, the pathfinder, and
Scenario B's own analytic half. The trigger adds a new `GraphPort` method with its own
conformance suite, this system's first job-queue worker, and a service-principal identity that
doesn't exist yet — real infrastructure, not one more bullet's worth of work. Unlike Phase 6a
(carved out because Glass work over a backend-only phase is a different *kind* of work), the
trigger and the compute/analytics work here are both backend/Conduit work of the *same* kind, so
this does not split into a new phase — but it does mean Phase 7 needs the stage breakdown it has
lacked until now, with the trigger sequenced first because it shares no implementation surface
with compute/analytics and two of this phase's own bullets (hotlists, alert inbox) depend on it:

1. **The trigger** (ADR-025's own pieces) — independent of every other stage below; closes
   `supersede_node`'s long-open worker gap in the same stroke; unblocks B8/B9/B13/B20's live
   demonstration soonest.
2. **`ComputePort` schemas and its conformance suite** — `NEXT_STEPS_PHASE7.md`'s own Tier-1/
   Tier-3 questions answered here, before any adapter, per standing rule 1 (`06_DECISIONS.md`
   ADR-028: Tier 1 runs as a plain Node script, Tier 3 defers to Phase 8a's `cluster` profile);
   independent of Stage 1 and may run in parallel with it. **Stage 3's own obligation, named here
   rather than left to be assumed automatic:** `ComputePort` takes no `Principal`
   (`01_DOMAIN_MODEL.md` §10) — the structural containment test this stage writes proves an
   adapter cannot leak a node it was never given, but the composed claim (a real caller always
   assembles its `Subgraph` through an access-filtered `GraphPort.expand`/`match` first) is
   `test_projection_access_control.py`'s own shape of test, owed by Stage 3 the moment the metrics
   panel exists as a real caller.
3. **`adapters/compute_rustworkx` and the metrics panel.**
4. **The visual query builder** — `01_DOMAIN_MODEL.md` §8.1's own pattern-binding-rule question
   (flagged since Phase 3, still unresolved) settled here, before an analyst is put in front of a
   canvas drawing arbitrary patterns. **Unfinished business, moved here from Stage 6's own scope
   21 September 2026 and closed the same day (Part 3):** ADR-032's own "saveable, shareable and
   versioned" promise for `PatternQuery` was left two-thirds unbuilt after this stage first shipped
   compose/preview/run — save, load, list, version and owner are this stage's own gap, not a
   monitor feature. Now built: `services/api/pattern_store.py`'s `PatternStore` (Postgres-backed,
   owner-only, versioned by insert-not-update, the same shape `investigations.py`/`sites.py`
   already use), `POST /v1/patterns/save`, `GET /v1/patterns`, `GET /v1/patterns/{pattern_id}`, the
   `QueryBuilderPanel.tsx` Save/Load controls, and two new `QUERY_BUILDER_ACTIONS` keyboard entries
   (`save-pattern`, `load-saved-pattern`) with their own Playwright proof, red then green (see the
   known-gaps entry below and ADR-032's own updated record for what shipped). Sharing is out of
   scope pending ADR-040 (Proposed, not accepted) — a saved pattern is loadable only by the analyst
   who saved it.
5. **The pathfinder.**
6. **Hotlists, saved-pattern monitors, alert inbox** — genuinely demonstrable only once Stage 1
   exists. **ADR-036 through ADR-039 (`06_DECISIONS.md`) are Accepted, 21 September 2026** —
   monitor principal identity (ADR-036), monitor trigger model and execution bounds (ADR-037,
   amended to a unified change stream), hotlist membership and existence (ADR-038, decided as a
   deployment-level `strict`/`notify` policy switch), and alert inbox lifecycle (ADR-039, accepted
   with two additions) are no longer open decisions. **Stage 6's one remaining precondition —
   pattern persistence — is also closed, same day (Stage 4's own Part 3 above):** ADR-036's own
   owning-principal reference now lives on `SavedPattern.owner_id`.

   **Stage 6 splits into 6a (foundation), 6b and 6c — 6a and 6b built 21 September 2026, 6c not
   started.** Read this as the same "carve out a different kind of work" discipline Phase 6a
   (over Phase 6) already established, applied one level down: the alert model, the disclosure
   switch and the change stream are backend primitives every future producer shares; hotlist/
   monitor UI and the actual scheduled evaluation loop are each their own, later, unit of work
   against those primitives, not bundled into discovering them.

   **6a — foundation, built.** The change stream (`services/api/change_stream.py`, ADR-037's own
   amendment): one Valkey Stream (`changes:corpus`), a thin publish/read mechanism with no
   consumer-group/worker of its own — Stage 6b/6c's own future evaluator is the first real
   consumer. Wired to all three accepted producers: ingest (`app.py`'s `run_studio_recipe`
   route), the corpus-wide resolution trigger (`services/resolve/trigger.py::
   run_resolution_for_entity_type`, optional `valkey` param so every existing direct caller keeps
   working unchanged), and manual assertion (`WorkingSetService._manual_assertion`, optional
   `valkey` constructor param, same shape). Proven with the case ADR-037's own amendment named
   directly: `tests/services/api/test_change_stream.py::test_change_stream_carries_a_same_as_
   edge_written_by_resolution_with_no_new_ingest` — two pre-existing nodes, no ingest call
   anywhere in the test, the resolution trigger alone writes the `SAME_AS` edge and the stream
   carries it.

   The alert model (`services/api/alerts.py`, ADR-039): `Alert` stores references
   (`referent_node_ids`), never copies; `AlertStore.get_authorized` filters `owner_id` in the
   query itself from the start (ADR-041's own mechanical check, `scripts/
   authorized_query_check.py`, passed clean on first write — 38 files, no offenders);
   `evidence_available` re-checks every referent against `GraphPort.get_node` at read time,
   independent of the ownership check. Proven: `test_alert_evidence_is_unreadable_after_
   referent_access_is_revoked` (a `supersede_node` call with a replacement handling the owner
   can no longer see — the only way a node's own handling changes in this system) and
   `test_revoked_alert_remains_listed_as_unavailable_not_removed` (the row stays readable and
   listed, marked unavailable, per ADR-039's own Addition 2).

   The disclosure policy switch (`disclosure_policy_from_value`, ADR-038): a whitelist match to
   exactly `"notify"`, defaulting to `"strict"` for everything else — fail-closed by
   construction, not by a separate check, read once into `ApiConfig.hotlist_alert_policy`.
   Proven: `test_hotlist_policy_defaults_to_strict_when_deployment_config_is_unset` (unset,
   empty, unrecognised and wrong-case all resolve to `strict`) and `test_notify_mode_alert_
   contains_no_referent_its_recipient_cannot_read` — written against `alert.model_dump(mode=
   "json")`, the client-serialised shape, not the internal object, per the task's own
   instruction, since a check against an attribute happening to be empty today would not catch a
   future evidence panel reconstructing content a different way.

   Audit (`record_match`, ADR-038): every suppressed (`strict`) and every notified (`notify`)
   match writes an `audit_log` row via the existing `AuditWriter`, carrying the principal, the
   matched identifier and the policy mode — both modes, not only `notify`. Proven:
   `test_suppressed_and_notify_matches_both_write_an_audit_record_with_principal_and_mode`, run
   under both configured modes in one test, asserting a distinct row for each.

   **Bounds (ADR-037: concurrency limit, per-evaluation cost cap, overrun behaviour) — disclosed,
   not implemented, and that is the deliberate choice, not an oversight.** All three exist to
   bound a *scheduled evaluation loop* — the thing that would run a saved pattern or a hotlist
   check repeatedly against the change stream. Stage 6a builds no such loop (6a's own scope is
   the mechanism the loop will later call, not the loop); ADR-025's own overlap-guard shape
   (`resolve:running:{entity_type}`, a held-for-duration Valkey lock) is the obvious pattern to
   reuse once one exists, but writing that lock now, with nothing yet acquiring it on a repeating
   schedule, would be bounding a mechanism that cannot yet run unbounded — speculative
   infrastructure against a caller that doesn't exist, the same class of premature build this
   document's own standing rules argue against elsewhere. **Owning phase/stage: 6b or 6c**,
   whichever first builds a real scheduled/event-driven evaluator — the bound belongs in the
   scheduler ADR-037 already says it must, at the point a scheduler is first written, not before.

   **What 6a does not build, named precisely rather than left to be inferred from "foundation
   only":** no `HotlistStore`/monitor-definition store (the disclosure mechanism `record_match`
   takes an abstract "triggering node ids" and a caller-supplied identifier label — real, but
   generic; nothing persists a hotlist entry or a monitor's own saved-pattern binding yet), no
   scheduled or event-driven consumer of the change stream (the stream is proven readable, not
   watched), no hotlist/monitor/alert-inbox UI, no `app.py` routes for any of the above (nothing
   yet calls this code except a future 6b/6c and this stage's own tests). B12/B13/B14/B20 remain
   unexercised by any acceptance scenario until 6b/6c gives them a real hotlist/monitor to fire
   from — Stage 6a's own primitives are what B12/B13/B14/B20 will eventually run against, not
   something this stage itself claims to satisfy.

   **6b — the evaluator and its bounds, built 21 September 2026. 6b, not 6c, is where the
   evaluator lives:** ADR-037's own bounds (concurrency limit, per-evaluation cost cap, overrun
   behaviour) exist to bound a scheduled/event-driven consumer of the change stream, and 6b is
   the first stage that builds one — 6c's own remaining scope (below) is UI and the routes a real
   analyst would use to create a hotlist or turn a pattern into a monitor, neither of which needs
   or benefits from existing before the mechanism they will eventually call does. Building the
   evaluator against 6c's own not-yet-written routes would have meant either a second, throwaway
   test harness or blocking on 6c — reversed instead: the evaluator is proven directly, by tests
   calling it with real Postgres/ArcadeDB/Valkey, exactly the way 6a's own primitives already were.

   Two stores, both Postgres, both `owner_id`-filtered in the query itself from the start
   (`scripts/authorized_query_check.py`, re-run after this stage: 41 files under `services/api`,
   no offenders): `services/api/hotlists.py`'s `HotlistStore` (`02_GLASS_FRONTEND.md` §3.3 — an
   `identifier`, an `owner_id`, a `review_date`; deliberately bare, since ADR-038's own "an analyst
   can hotlist a bare phone number before it resolves to anything they can see" means a hotlist
   entry is not a node reference) and `services/api/monitors.py`'s `MonitorStore` (a `pattern_id`
   reference, never a copy of the pattern's own definition — re-read fresh from `PatternStore` on
   every evaluation, the same "resolved fresh, never cached" discipline ADR-036 already requires of
   a monitor's *access*, extended here to its own *query*). Both add a `list_all_active` method
   that is deliberately **not** principal-scoped — the one unscoped read each store has, mirroring
   `GraphPort.list_nodes`'s own ADR-025 precedent for "the trigger needs the whole population, not
   a caller-scoped view of it" — and both are never called from any route, only from the evaluator
   below.

   The evaluator (`services/api/evaluation.py`) is two functions, not one, because a hotlist match
   and a monitor match have genuinely different leak shapes (ADR-036/038 already say so):
   `evaluate_hotlists_for_entry` needs a read unscoped to any one owner's access just to *find* a
   match (`service_principal`, the same corpus-wide identity `services/resolve/trigger.py` already
   uses for resolution), then a *separate* disclosure decision via `alerts.py`'s `record_match`
   using the hotlist owner's own principal and ADR-038's `strict`/`notify` switch;
   `evaluate_monitors_for_entry` re-runs the saved pattern through `GraphPort.match` as the owner's
   own principal directly, so there is no out-of-access case for a monitor alert to ever suppress
   or redact — `record_match`'s `strict`/`notify` branch is structurally unreachable for a monitor,
   not merely defaulted to one side of it. Both are guarded per-hotlist/per-monitor by a Valkey
   lock (ADR-025's own overlap-guard shape, reused rather than reinvented) that skips a concurrent
   trigger rather than queuing it — ADR-037's overrun bound. The per-evaluation cost cap
   (`MAX_TOUCHED_NODES_PER_EVALUATION = 200`) bounds how many of a single change-stream entry's own
   touched node ids one hotlist evaluation will check, not the number of hotlists themselves.
   Monitor dedup is disclosed as coarse, not assumed precise: `GraphPort.match` returns one
   `Subgraph` per pattern, not discrete match instances, so "is this a new match" is answered at
   the whole-subgraph level — a hash of the current match's sorted node/edge ids, compared against
   the last hash this monitor alerted on. A growing, shrinking-but-nonempty, or differently-composed
   match set all count as "new"; an unchanged one does not.

   **The no-principal-directory gap, disclosed at the point it first bites, not worked around.**
   No principal directory exists anywhere in this codebase — `Principal` is "resolved by the
   Conduit from the session token" (`schemas.domain.Principal`'s own docstring) — and a scheduled
   evaluator has no session token in flight to resolve one from. Both evaluator functions take a
   caller-supplied `principal_for_owner: Callable[[str], Principal | None]` rather than resolving
   one internally; returning `None` is the disclosed stand-in for ADR-036's own "the monitor
   stops" when a fresh principal cannot be resolved, proven directly by
   `test_a_hotlist_with_no_resolvable_owner_principal_is_skipped_not_run_as_a_stale_one`. **Owning
   phase for the real resolution: 6c**, the same stage that first gives a hotlist/monitor a route
   an actual analyst calls through — a scheduled worker process still has no session token even
   once 6c exists, so 6c's own job is a principal-resolution strategy for a backgrounded caller
   (a service-level re-resolution against a stored `owner_id`, most plausibly), not a full
   principal directory; recorded here so it is not silently assumed solved by 6b's own test double.
   **This is manifestation one of three of a single gap** — see "Gaps with no owning phase"'s own
   consolidated entry, below, for the other two and the combined operational consequence.

   Proven — the task's own named test and five more exercising what it implies:
   `test_a_hotlist_match_outside_the_owners_access_leaks_nothing_in_strict_or_notify` (renamed
   from `..._produces_nothing_in_strict_and_notify` — a later review caught that the original name
   read as "nothing is produced in either mode," which is false: notify mode does produce an
   alert, ADR-038's whole point of having two modes. What the test actually proves: a hotlist
   match the evaluator's own unscoped read can see but the hotlist's owner cannot produces nothing
   at all under `strict`, and a content-free alert under `notify` — `referent_node_ids == []` and
   neither the node id nor the identifier appear anywhere in the serialised alert, checked against
   `.model_dump(mode="json")` per ADR-038's own precedent, not an internal attribute);
   `test_a_hotlist_match_visible_to_its_owner_writes_a_full_alert`;
   `test_a_hotlist_evaluation_already_in_progress_is_skipped_not_queued` (the overlap guard,
   proven by holding its own lock externally, not merely asserted);
   `test_a_monitor_alert_is_always_visible_since_the_match_is_already_owner_filtered`;
   `test_a_monitor_alerts_once_per_match_set_and_again_only_when_it_changes` (the coarse dedup,
   proven against a match set that grows, not only one that stays the same); and
   `test_a_monitor_whose_pattern_no_longer_exists_stops_rather_than_errors`.

   **`test_a_monitor_never_evaluates_with_a_principal_broader_than_its_owner`, added on later
   review — pins an invariant the code already had but nothing proved.** The structural-
   unreachability claim in `evaluate_monitors_for_entry`'s own docstring is a property of today's
   code, not an enforced one: a future "efficiency" swapping in `service_principal` (the identity
   `evaluate_hotlists_for_entry` deliberately does use) for a monitor's own match would silently
   activate the out-of-access path this module claims does not exist. Checked directly while
   writing this test, not assumed: an assertion on the *alert outcome* alone cannot catch that
   regression — `alerts.py::record_match`'s own independent per-referent recheck
   (`graph.get_node(node_id, recipient)`, always against the true owner) suppresses the leak at
   the alert either way, so a leak-outcome-only test passes whether or not `graph.match` itself
   was ever called with the wrong principal. The test instead wraps the real adapter
   (`_PrincipalRecordingGraph`) to record the actual `principal` argument `graph.match` receives,
   the only thing that pins the invariant the task named rather than a downstream proxy for it.

   **What 6b does not build:** no `app.py` routes for creating a hotlist or turning a pattern into
   a monitor (nothing yet calls `HotlistStore.create`/`MonitorStore.create` except this stage's own
   tests), no production wiring of the evaluator into an actual running scheduled or event-driven
   process (the evaluator is a callable function, proven directly by tests against real
   Postgres/ArcadeDB/Valkey — a real always-on consumer of `changes:corpus` is 6c's own job,
   paired with the routes above, since a scheduler with nothing able to create a hotlist or
   monitor yet would have nothing to evaluate in production), no hotlist/monitor/alert-inbox UI.
   **B12/B13/B20 are therefore still not satisfied end-to-end** — `08_ACCEPTANCE_SCENARIOS.md`'s
   own rows describe an analyst action ("Add the endpoint to a hotlist," "Save the pattern as a
   monitor") that has no route to perform it through yet. What 6b changes is *where* the remaining
   gap sits: narrowed from "no mechanism exists" to "the mechanism exists and is proven directly,
   only the route and the UI in front of it are missing" — 6c's own scope, precisely.

   **6c — the backend half, built 21 September 2026; the Glass UI half not started, named
   precisely rather than silently implied by "6c done."** Routes: `POST`/`GET /v1/hotlists`,
   `POST`/`GET /v1/monitors` (owner-only, mirroring `/v1/patterns/*` exactly), `GET /v1/alerts`,
   `GET /v1/alerts/{id}`, `POST /v1/alerts/{id}/jump` (`services/api/watch_routes.py` for the
   request/response shapes, wired into `app.py`).

   **The synchronous-evaluation decision (`06_DECISIONS.md` ADR-036's own new amendment has the
   full reasoning) wired into two of ADR-037's three producers — ingest and manual assertion — the
   third (corpus-wide resolution) found structurally unwireable while building the carry-over
   below, not deferred by choice.** `app.py`'s `run_studio_recipe` and `link_resolution_route`
   (a manual link only — `manual_split` cannot grow a match set, ADR-037's own reasoning) both call
   the shared `_evaluate_watches_best_effort` helper right after publishing to the change stream,
   with `principal_for_owner` resolving only when `owner_id` equals the requesting analyst's own
   id. A failure in this best-effort side evaluation is caught and audited
   (`action="watch_evaluation_failed"`), never allowed to fail the primary operation (the load, or
   the link) that already succeeded.

   **Corpus-wide resolution — checked, not assumed, and found to have no code path with a live
   principal anywhere, for any caller.** `services/api/resolution_trigger.py`'s own `resolve_now`
   docstring: "Always submits a job, never runs synchronously." `services/resolve/trigger.py::
   run_resolve_entity_type_job`'s own fixed `JobWorker` dispatch shape (`payload, *, graph, tx`,
   with `ontology`/`scheme`/`valkey` bound at registration) carries no principal, for the automatic
   post-ingest trigger or the manual "resolve now" route alike — both cross the identical job/worker
   boundary before `run_resolution_for_entity_type` ever executes. Wiring evaluation in here would
   need either an invented identity (defeats the whole point of `principal_for_owner` returning
   `None` rather than guessing) or a principal captured at job-submission time and carried through
   the queue — exactly the cached-principal shape ADR-036 already rejects as "a durable grant
   outliving whatever permission produced it." Not fixed here; recorded, with the test that pins the
   boundary rather than assumes it: `test_a_monitor_does_not_fire_on_a_match_created_by_resolution_
   with_no_new_ingest` (`tests/services/api/test_evaluation.py`) — a real resolution run, via
   `run_resolution_for_entity_type` itself, genuinely writes a `SAME_AS` edge a real monitor's own
   pattern genuinely matches (both asserted, not assumed), and still produces no alert, because
   nothing with a resolvable principal ever calls the evaluator for a `source="resolution"` entry.
   Owning phase: **Phase 8**, the same principal-directory dependency ADR-036's amendment already
   names — this is not a second, separate gap, only its first concrete instance found by trying
   to close it rather than only naming it. **Manifestation three of three** — see "Gaps with no
   owning phase"'s own consolidated entry, below, for the combined operational consequence.

   **The request-path cost this adds, disclosed rather than silently absorbed into latency —
   both routes now carrying it, not only ingest.** Each hotlist/monitor evaluation is bounded (the
   overlap lock, `MAX_TOUCHED_NODES_PER_EVALUATION`, both Stage 6b's own) — the *aggregate* is
   not: `run_studio_recipe` and `link_resolution_route` alike now block on evaluating every
   hotlist and monitor the requesting principal owns, not a fixed number of them, unlike
   `services/resolve/trigger.py`'s own precedent of one dispatched job regardless of population
   size. Acceptable at the scale a single analyst's own watch list reaches today; not a bound that
   holds at arbitrary scale, and not fixed here — a job-queue dispatch (`services/api/jobs.py`,
   the same infrastructure `submit_supersede_node`/pattern-match already use) is the shape a fix
   would take, owned by whichever phase first needs it.

   **`Hotlist.status`/`Monitor.status`, `06_DECISIONS.md` ADR-036's own "surfaced as stopped"
   requirement, closed.** Written by the evaluator on every reach (`"stopped"` when a principal
   cannot be resolved or, for a monitor, its pattern no longer resolves; `"active"` on every
   attempt that genuinely runs), not sticky — the next successful attempt clears it. Proven:
   `test_a_skipped_hotlist_evaluation_is_observable_as_stopped_and_a_later_success_clears_it` and
   its monitor twin (`tests/services/api/test_evaluation.py`) — the named tests the task itself
   asked for, proving the skip is observable, not merely that it happens (already proven in 6b).

   **`Alert.investigation_id`, threaded from the triggering event, not from the hotlist/monitor's
   own creation context** — `schemas.domain.Alert`'s own docstring has the full reasoning for why
   (ingest is investigation-scoped at the route level; a hotlist/monitor is not investigation-scoped
   at all and outlives any one investigation it was set from). `ChangeStreamEntry` gained the same
   field, threaded through `ChangeStreamWriter.publish`. `POST /v1/alerts/{id}/jump` branches a new
   `Investigation` from it via `InvestigationStore.create(principal, branched_from=...)` — the
   identical mechanism `branch_investigation` already uses — then seeds the branch's working set
   with the alert's referents, re-fetched fresh as the *viewer's* own principal at jump time, never
   trusted from whatever `evidence_available` found true when the alert was listed
   (`fetch_jumpable_referents`, `watch_routes.py`). A referent unreadable by jump time is not
   silently dropped: `AlertJumpResult.unreadable_count` reports it, alongside `seeded_count`, so a
   caller can surface a partial-success notice rather than a call that looks fully successful when
   it wasn't — the task's own question, answered in the response shape, not only in prose.
   **Real foreign key, checked directly while writing this stage's own tests, not assumed:**
   `investigations.branched_from` is a genuine `REFERENCES investigations(id)` constraint — a
   synthetic or stale `investigation_id` is rejected at write time, not silently accepted.

   **`AlertView` redacts server-side** (`watch_routes.py`) — the task's own instruction that
   notify-mode's render-layer leak risk ("a component that helpfully falls back to an id") needs an
   equivalent to the API-layer test that already exists. A `FULL` alert whose evidence has since
   become unavailable (ADR-039's own revocation case) is never returned with its real
   `referent_node_ids` intact alongside a separate flag a future renderer could ignore;
   `referent_node_ids` in the wire response is authoritatively `[]` whenever `evidence_available`
   is `False`, computed once, server-side, so a renderer has nothing left to get wrong. Proven:
   `test_alert_list_redacts_a_full_alert_whose_evidence_has_since_become_unavailable`
   (`tests/scenarios/test_phase7_stage6c_watch_routes.py`), against a real revocation
   (`supersede_node`), at both `GET /v1/alerts` and `GET /v1/alerts/{id}`.

   **A real connection-pool ceiling, found while writing this stage's own real-service tests and
   now closed for all ten Postgres-backed stores, not only the three this stage added.**
   `asyncpg.create_pool`'s own default (`min_size=10`, `max_size=10`) times the ten Postgres-backed
   stores `app.py`'s lifespan opens was already within reach of Postgres's own
   `max_connections=100` before this stage; adding `HotlistStore`/`MonitorStore`/`AlertStore`
   (three more pools at the same default) pushed a real `TestClient(app)` lifespan over it,
   reproduced directly as `asyncpg.exceptions.TooManyConnectionsError`, not merely suspected.
   Bounding only the three new stores would have left the other seven's identical unbounded
   default as live a risk as before — checked and found true (a single reverted bound was enough
   to push the measured delta back over this section's own regression test's threshold), so all
   ten are now explicitly sized, each store's own `.connect()` carrying `hotlists.py::
   HotlistStore.connect`'s comment as the shared reference for why.

   **The arithmetic, stated explicitly rather than left implicit in ten separate numbers.**

   | Store | `min_size` | `max_size` |
   | --- | --- | --- |
   | `AuditWriter` | 2 | 10 |
   | `InvestigationStore` | 2 | 8 |
   | `InvestigationHistoryStore` | 1 | 5 |
   | `PatternStore` | 1 | 5 |
   | `SiteStore` | 1 | 5 |
   | `StudioRecipeStore` | 1 | 5 |
   | `ExtractionCandidateStore` | 1 | 5 |
   | `HotlistStore` | 1 | 4 |
   | `MonitorStore` | 1 | 4 |
   | `AlertStore` | 1 | 4 |
   | **Total** | **12** | **55** |

   At lifespan **startup**, one Conduit instance opens 12 connections (measured directly —
   `test_app_lifespan_does_not_reopen_the_unbounded_pool_ceiling`,
   `tests/scenarios/test_phase7_stage6c_watch_routes.py`); at its own **worst case under load**
   (every pool saturated at once), 55. Against Postgres's own `max_connections=100` — the
   `postgres:16` image's own unmodified default; confirmed directly (`SHOW max_connections`), not
   assumed, since neither `deploy/compose/dev.yaml` nor `ci.yml`'s own `conformance` job overrides
   it: one instance is safe in both cases (12 and 55 both well under 100). **Two instances — the same stateless-multi-instance shape Phase 3's own exit criterion
   and Phase 8a's own outcome bullet already name as this build's real target
   (`test_statelessness.py`; Phase 8a: "The Postgres connection-pool hardening Phase 7 Stage 1
   found — two live Conduit instances together exhausted `max_connections` — real here for the
   first time") — are safe at startup (24) but not at worst case (110, over the 100 limit).**
   This is not a new problem this stage introduces: it is the identical, already-named Phase 8a
   gap, now given an exact bound instead of an untested "eventually OOMs under load" description —
   this stage's own fix makes **one** instance safe under any load and makes **multiple** instances
   safe at rest, narrowing the gap from "unknown, found only under load" to "known, and only under
   simultaneous multi-instance saturation," still Phase 8a's own scope to close (raising Postgres's
   own `max_connections`, or a shared connection-pooler such as PgBouncer, are the two shapes
   already implied by that phase's own hardening language). **One of three disclosures now bearing
   on the same horizontal-scalability claim** — see "Gaps with no owning phase"'s own consolidated
   entry for the other two and the combined finding.

   **The test that would fail if an eleventh store were added without a bound, named and
   confirmed both directions, not only proposed.**
   `test_app_lifespan_does_not_reopen_the_unbounded_pool_ceiling`
   (`tests/scenarios/test_phase7_stage6c_watch_routes.py`) measures the actual delta in live
   Postgres connections one full `TestClient(app)` lifespan opens (`12`, matching the table above)
   against a threshold (`20`) tight enough that any single store regressing to
   `asyncpg.create_pool`'s own unbounded default fails it — confirmed by reverting one store's own
   bound during this stage and watching the test fail, then restoring it and watching the test
   pass again, not assumed from the arithmetic alone.

   **What 6c's backend half does not build, named precisely:** no Glass UI (no hotlist/monitor
   creation panel, no alert inbox render, no jump affordance), no keyboard actions registered for
   any of the above, no vitest/Playwright coverage for any of the above — the Gates this stage's
   own task named (`authorized-query-check`; every new workspace action registered and covered, red
   then green; frontend behaviour gets frontend tests) apply to that half and are unmet by design,
   not overlooked, pending a decision on whether this session continues into it or a follow-up does.
   `authorized-query-check` itself: run against this stage's own new stores, clean — 42 files under
   `services/api`, no offenders.

   **6c Part 2 — the Glass UI half, built the same session.** `apps/workspace/src/watches/`:
   `HotlistPanel.tsx` (create + list, `Hotlist.status` rendered via a shared `StatusBadge`),
   `MonitorPanel.tsx` (a saved-pattern `Select`, reusing `patterns/api.ts::listPatterns` rather than
   duplicating it, + list with the same status badge), `AlertInbox.tsx` (list, per-row `full`/
   `notify_stub` rendering, the jump action and its result summary), `api.ts` (fetch wrappers for
   all six routes). Wired into `App.tsx` as a fifth top-level `view`, `"watches"` — owner-only, not
   investigation-scoped, the same reasoning `/v1/patterns/*` already has, so it sits beside
   `"ingest"`/`"dossier"` rather than inside the investigation-scoped graph-view side panel; a
   successful jump sets `investigationId`/`sessionStorage` and switches `view` back to `"graph"`,
   the same transition the existing "create a new investigation" effect already performs. Errors
   surface as the same inline `error` banner `QueryBuilderPanel.tsx` already established for a
   non-canvas panel, not `ActionErrorOverlay` (an x/y-positioned `Popover` built for the canvas) —
   disclosed in each panel's own doc comment so the departure from a literal reading of "surface via
   `ActionErrorOverlay`" isn't mistaken for an oversight.

   **`AlertView`/`AlertJumpResult` are hand-mirrored TypeScript interfaces in `watches/api.ts`, not
   generated.** Checked directly against `packages/schemas/generate_ts.py`: its own model list is
   `schemas.{analytics,compute,domain,ingest,model,profile,provider_profile}` — `services/api/
   watch_routes.py` (where both live) and `services/api/investigations.py` (`Investigation`, needed
   for the jump result) are outside that scope by construction, neither being a `packages/schemas`
   module. `Hotlist`/`Monitor` *are* generated and imported, not redeclared. A drift gate exists for
   every `packages/schemas` model (`generate_ts.py` itself, run as part of `schemas-check`); these
   three hand-mirrored shapes have no equivalent — an edit to `AlertView`/`AlertJumpResult`/
   `Investigation` server-side has nothing to fail a build the way a `Hotlist` field rename already
   would. No owning phase decided here; recorded as a gap for whichever phase next revisits
   `generate_ts.py`'s own scope (widening it to `services/api` route-response models generally,
   not just this one route module, would be the shape of the fix).

   **The three named render-layer tests this session's own task required, each confirmed to fail
   against a real reverted implementation, not only against a self-contained regression stand-in
   (`src/watches/AlertInbox.test.tsx`, `src/watches/StatusBadge.test.tsx`):**
   - `test_a_notify_mode_alert_renders_with_no_referent_the_viewer_cannot_read` — a `notify_stub`
     `AlertView` fixture renders with no id-shaped token anywhere in the DOM; its own second case
     feeds a non-empty `referent_node_ids` on a `notify_stub` alert (a shape the real server-side
     `AlertView` never produces) to prove `AlertRow` itself enforces the redaction, not merely an
     accident of an already-empty fixture — confirmed live by deleting both of `AlertRow`'s own
     `mode === "full"` guards and watching this fail, then restoring them.
   - `test_a_stopped_hotlist_is_visibly_stopped_not_only_flagged_in_data` — a `status: "stopped"`
     fixture renders a distinct "Stopped" label, not merely a prop; confirmed live by hardcoding
     `StatusBadge`'s own `stopped` to `false` and watching this fail.
   - `test_jump_result_never_frames_unreadable_count_as_newly_visible_content` — pins the actual
     safety argument, confirmed by reading `services/api/alerts.py` this session:
     `AlertStore.get_authorized`/`list_authorized` filter `WHERE owner_id = $1` (ADR-041) — an alert
     is only ever reachable by its own recipient — and `fetch_jumpable_referents` re-checks every
     referent fresh as the *current* viewer's own principal, never a cached one, so
     `unreadable_count` can only ever recount referents the viewer already had a standing claim to
     receive, never reveal a new one. The test asserts the rendered copy is framed accordingly ("no
     longer accessible", never "found"/"new"/"hidden") and is scoped to the `unreadable_count`
     sentence specifically, not the whole summary (which legitimately says "new investigation"
     elsewhere, about the investigation itself, not the referents) — confirmed live by changing the
     real component's own copy to "N new referents found." and watching this fail.

   Component-render testing (`@testing-library/react`, `jsdom`) had no precedent in this
   workspace's `vitest` suite before this — every prior `*.test.ts` was pure logic under
   `environment: "node"`. Added `jsdom`/`@testing-library/react` as new devDependencies and a
   per-file `// @vitest-environment jsdom` docblock convention (`vitest.config.ts`'s own global
   `environment: "node"` is unchanged, so no existing test is affected) plus the `@vitejs/
   plugin-react` plugin `vitest.config.ts` itself now also loads, for JSX transform in `.test.tsx`
   files.

   **Keyboard reachability — the fourth keyboard-driven surface** (`keyboard/watch-panels-
   harness.tsx`/`.html`, `keyboard/watch-panels.spec.ts`, a new `WATCH_PANEL_ACTIONS` registry in
   `keyboard/actionRegistry.ts`): `submit-create-hotlist`, `submit-create-monitor`, `alert-row-jump`
   (a real `POST /v1/alerts/{id}/jump`, mocked at the transport, not the component), and
   `jump-result-open-investigation` (the real callback out of `AlertInbox`, proven via
   `window.__WATCH_HARNESS__`, the same shape `window.__KEYBOARD__` already establishes for
   `GlassCanvas`). Every native `Input`/`Select`'s own Tab-reachability is exempted, the same
   precedent `QUERY_BUILDER_ACTIONS`'s own docstring already sets. **Confirmed non-vacuous, not
   only asserted**: commenting out one `registerCovered` call and re-running made
   `assertAllCovered` fail by name; restoring it passed again. All 35 Playwright specs across all
   four registries pass together, and `registryCoverage.test.ts` (the static half — every declared
   registry has some `*.spec.ts` actually asserting it) picked up `WATCH_PANEL_ACTIONS` with no
   wiring beyond the registry declaration itself.

   **Vitest: 174 → 181 tests, 24 → 26 files** (`AlertInbox.test.tsx` + `StatusBadge.test.tsx`; the
   movement includes one additional case inside the pre-existing `registryCoverage.test.ts`, which
   iterates every declared registry and so grew by exactly one entry when `WATCH_PANEL_ACTIONS` was
   added, not a padded count). `npx tsc --noEmit` clean across the whole workspace.

**Exit.** Acceptance scenario B, scoped to B1 (its two-CDR-files half only; the device-extraction
half stays unowned, ADR-027), B2–B5, B7, B12, B13 (via a CDR-carried hotlisted identifier, not the
literal seizure-record fixture, ADR-027), B14, B15 (its `imsi→Device` leg only, ADR-022's own
first addendum), B19 and B20, passes end to end. The Clique Metric ranks the insular-cluster
fixture node above the broad-hub fixture node, and its two registered compute tiers (Tier 1
graphology, Tier 2 `rustworkx` — Tier 3 deferred to Phase 8a's `cluster` profile, `06_DECISIONS.md`
ADR-028) return
identical values within tolerance. A12 (Phase 5's exit criterion, scoped to A1–A11, deferred this
one step here per ADR-019) is re-proven against the same HMP fixture: the Clique Metric identifies
the same insular subgroup Phase 5 already surfaced by other means. B15 (a SIM `Endpoint` reaching
its `Device` in one traversal) is re-verified here specifically because this phase's own pathfinder
and visual query builder compute over that same traversal shape — see ADR-023, which must land
before this phase's Session 5 (schemas and the `ComputePort` conformance suite) so neither is built
against a graph topology about to change.

**Read precisely, not assumed from the sentence above, a second time: "B12/B13/B14/B20 pass end to
end" is not the same claim for every principal who could set a hotlist or a monitor.** The pattern
this document's own standing rule 12 names — a gate proving less than its name implies — applies to
this exit criterion itself, not only to a test file, and is recorded here rather than only in
`06_DECISIONS.md` ADR-036's own amendment. What actually passes: the walkthrough
`08_ACCEPTANCE_SCENARIOS.md` narrates, where the analyst who sets the hotlist/monitor in B12/B20 is
the same analyst whose later action in B13/B20 triggers it — `owner_id == requester` holds by
construction, because it is one continuous session. What does not pass, and is not exercised by
this exit criterion at all: a hotlist or monitor firing from a *different* analyst's later ingest —
the operational case B13's own CoLP framing is actually modelled on ("a warrant seizure logged by a
unit other than the one that set the original hotlist entry"), which is precisely the case this
document's own acceptance scenario does not test, because ADR-036's amendment (`06_DECISIONS.md`)
means the built system does not yet handle it. "Scenario B passes end to end" is therefore true of
the walkthrough as written and not a claim that hotlists/monitors work operationally across
analysts — that remains Phase 8's own scope, alongside the principal-directory dependency the
amendment names. B15's own "Platform capability" column
(`08_ACCEPTANCE_SCENARIOS.md`) names "Endpoint model," not "Pathfinder" — the traversal it
re-verifies is a direct `GraphPort.expand`-shaped one over the corrected ontology, not a `POST
/v1/paths` call. The sentence above names the pathfinder only as *why the phase orders ADR-023
before Session 5* (both consumers would need rework if the topology moved under them after being
built), not as a claim the pathfinder is itself exercised by any acceptance scenario. Checked
directly against every B-step's own row rather than inferred from this ordering note: none of
B1–B20 names "Pathfinder" in its own mechanism column, and Phase 7's own exit criterion (above)
does not list it. Standing rule 9 makes this permitted — a phase closes against its exit criterion,
and the pathfinder (Phase 7 Stage 5, `06_DECISIONS.md` ADR-033) is bullet-list work with no
acceptance-scenario obligation, the same shape hotlists/saved-pattern monitors have until Stage 6
gives B20 something to run against — recorded here, before the gate, rather than left for a future
phase's scoping to rediscover from this same ambiguous-looking sentence.

The full scenario, as originally written, is not satisfiable by this phase alone. B6 and B9–B11
need the Glass surface Phase 6a builds over Phase 6's existing API. B16 and B18 need a cross-case
timeline overlay and a playback-driven snail trail; Phase 5's own Checkpoint 2 deferred
`playback`, `multi-track` and `cross-case overlay` past that phase without carrying the deferral
into this document. None of these four steps is built by any phase's bullet list above them. This
is a correction to the scenario's phase attribution, not a narrowing of what the platform must
eventually do: B6/B9–B11 are Phase 6a's own exit criterion, B16/B18 are Phase 8's own outcome
(below). See ADR-022 (`06_DECISIONS.md`) for the full reasoning and its 18 September addendum for
the Phase 6a/Phase 8 split.

B8, B13 and B20's own dependence on a corpus-wide trigger — and B15's own msisdn leg, which stays
fixture-only until a device-extraction connector exists (ADR-024) — mean this phase's own bullets
above cannot be demonstrated against a live deployment, rather than fixture data assembled by a
test harness, until ADR-025's own design is actually built. See ADR-025 for the full trigger
design (event, population, principal, overlap, recovery) and ADR-024 for the msisdn↔imsi
mechanism and its own owning phase.

**Phase 7 known gaps (created here, during Stage 1's own closing pass, the same discipline Phase
5's, Phase 5a's and Phase 6's own lists were each created by the stage that first needed to
disclose something — this list did not exist before Stage 1 found it needed one):**

- **The status-bar conflict-count notice (this phase's own Stage 1 bullet,
  `06_DECISIONS.md` ADR-025) is not built.** ADR-025 proposes surfacing pending conflicts "the same
  way the status bar already surfaces 'N hidden by handling'" — but that existing notice
  (`apps/workspace/src/statusbar/StatusBar.tsx`) rides the per-*investigation* WebSocket delta
  stream (`DeltaNotice`, `03_CONDUIT_MIDDLEWARE.md` §3.2), and a corpus-wide resolution run is not
  scoped to any one investigation's session. ADR-025 never settled how a signal with no
  investigation to attach to reaches an open investigation's own delta stream — broadcasting to
  every open session, polling a corpus-wide count on some other request, or another shape entirely
  are each a real design choice with its own cost, not an implementation detail to fill in while
  wiring the rest of Stage 1. Left disclosed rather than built on an invented, un-reviewed
  broadcast mechanism.
- **`services/resolve/trigger.py`'s `LOCK_TTL_SECONDS` (two hours) guards a correctness property
  with an unmeasured, conservatively-guessed value.** `06_DECISIONS.md` ADR-025's addendum has the
  full reasoning: the overlap guard is a real, held-for-duration Valkey lock, not merely a
  pre-submission check, but a run that genuinely outlives the TTL still lets a second run start
  while the first is writing, reopening the conflict-recording race the lock otherwise closes. No
  measurement of `resolve_entity_type`'s own running time at corpus scale exists anywhere in this
  repository — `tests/resolve/test_projection_perf.py`'s 50,000-node/0.056-second figure measures a
  different operation (`compute_clusters`' τ-threshold reprojection, bounded by the working set's
  50k cap), not this one. **What would retire the guess:** a real timing of `resolve_entity_type`
  against a `Person` population at the largest scale a deployment expects to run it, the same
  "measured, not assumed" discipline `01_DOMAIN_MODEL.md` §8.2 already applied to
  `supersede_node`'s own ~41-second figure.
- **`GraphPort.get_edge` remains unbuilt, now for a second, independent reason.** Phase 6's own
  gaps list declined to add it for edge-candidate extraction. Stage 1 hit the identical absence
  from a different direction — a cheap revision-check inside `record_conflicts` would have closed
  the overlap gap above directly — and made the same call not to add it for this reason either.
  Recorded here so a third caller finding the same gap reads this instead of re-deriving it.
- **`ComputePort.temporal_motifs`'s own algorithm (convoy/relay/burst detection) is unclaimed.**
  Stage 2 gave `MotifRequest`/`MotifMatch` real schemas — `_pending_port_placeholders.py`'s
  retirement needed every one of `ComputePort`'s five names replaced, not only the ones this
  phase's own outcome bullet names — but that bullet lists only "Degree, betweenness, eigenvector,
  clustering coefficient, Louvain, Clique Metric." The type is real
  (`01_DOMAIN_MODEL.md` §10); the algorithm itself has no owning phase, the same "gaps with no
  owning phase" shape the OpenSearch index and the corpus-wide trigger both had before something
  claimed them.
- **Tier 3 (`GraphFrames`/HugeGraph Vermeer, >2M nodes) does not register in Phase 7, on this
  host.** `06_DECISIONS.md` ADR-028 has the full reasoning and its own "revisit if": this
  development host's ~7.65GB Docker VM has produced five distinct memory/resource incidents across
  this build, and a local Spark session's own JVM overhead is not a proposal worth a sixth. Tier 3
  registers in Phase 8a's `cluster` profile instead — Phase 7's own exit criterion's "all three
  compute tiers return identical values within tolerance" is therefore demonstrated for two tiers
  inside this phase, not three, disclosed here rather than silently narrowed.
- **`02_GLASS_FRONTEND.md` §3.3's "Patterns are saveable, shareable and versioned" — scoped and
  two-thirds closed 21 September 2026, recorded here rather than left as the open question the
  paragraph below originally posed.** Stage 4 (the visual query builder, `06_DECISIONS.md`
  ADR-032) built compose, preview and run only, on 20 September; `PatternQuery` had no persistence
  path, no owner or share target, and no version history. **The scoping decision:** this is Stage
  4's own unfinished business, not Stage 6's — a monitor (Stage 6's own concern) is one consumer of
  a saved pattern, not a demonstration that generic save/share/version exists, and B20 ("save the
  pattern as a monitor") only ever needed save/version, never sharing. Moved to Stage 4's own
  bullet above accordingly. **Save, load, list and version are built**, same day, Part 3 of the
  session that accepted ADR-036–039: `services/api/pattern_store.py`'s `PatternStore`
  (Postgres-backed, owner-only via `SavedPattern.owner_id`, versioned by inserting a new row per
  save rather than updating in place, so no prior version is ever lost), `POST /v1/patterns/save`,
  `GET /v1/patterns` and `GET /v1/patterns/{pattern_id}` (`services/api/app.py`), direct-Postgres
  access-control tests (`tests/services/api/test_pattern_store.py`, mirroring
  `test_sites_store.py`'s own existence-leak discipline), and `QueryBuilderPanel.tsx`'s Save/Load
  controls with two new `QUERY_BUILDER_ACTIONS` (`save-pattern`, `load-saved-pattern`), each proven
  by its own Playwright case in `keyboard/query-builder.spec.ts` — shown red (both ids named as
  missing by `assertAllCovered`) before the cases existed, green after. The `owner_id` field this
  work adds is what closes ADR-036's own contingency. **Sharing is not built and stays out of
  scope pending ADR-040** (`06_DECISIONS.md`, Proposed, not accepted) — a saved pattern is readable
  only by its own owner until that record is decided, because sharing a pattern's own query
  definition (named entity types and literal attribute values) is a distinct leak from anything a
  fired match already discloses, per ADR-040's own reasoning. **Neither Acceptance Scenario A nor
  B exercises this persistence directly** — checked against `08_ACCEPTANCE_SCENARIOS.md` rather
  than assumed: B19 is a one-shot expand-and-return with no save; B20's own assertion is about the
  *alert* a monitor raises, not about save/load/list/version as objects in their own right, and
  Stage 6 (not yet built) is what would ever make B20 exercise this code path at all. Owned here
  rather than left to be rediscovered at Phase 7's own exit gate.

---

## Phase 8 — Assessment, export, and the admin console

**Outcome.** The platform produces an intelligence product, and a deployment is buildable and
operable from the browser or a script — all of it provable on `local-lite`.

- Judgements, gaps and assumptions with evidence linking and the review-flag loop.
- The probability yardstick loader.
- Export: chart, subgraph, report. The handling gate with named blockers and recorded
  justification. Withheld-item manifest on every export.
- The browser harness and the admin console it becomes: the six setup screens, live preflight,
  the generated-artefact diff, and the backup, restore, upgrade and verify screens.
- Harness-driven orchestration (`05_DEPLOYMENT.md` §2.4): target confirmation, drift detection,
  change preview, enforced backup-before-switch, and downgrade capacity checks against the
  existing data volume.
- The headless CLI equivalent for every screen, so a deployment built by clicking is reproducible
  by a script.
- Generated Kubernetes manifests and the per-deployment runbook.
- The two Scenario B Glass features no earlier phase built (ADR-022): cross-case timeline overlay
  and playback-driven snail trail (B16, B18) — small, incremental additions to Timeline and Map,
  the components Phase 5 already shipped, not a new surface the way Phase 6a is over Phase 6.
- **The demo distribution-class registry and Fixture Corp (R24) — `06_DECISIONS.md` ADR-035.** The
  `shipped`/`internal` manifest schema, its fail-closed registry, the packaging-time exclusion gate
  (both asserting no internal demo's id/path/dataset filename reaches a built artefact, including
  inside image layers), the Glass's "dataset not provisioned" unavailable state, and `make
  demo-manifest`. Fixture Corp itself (AMLSim- or gen-fraud-graph-generated, Enron-shaped, `shipped`)
  is this registry's first real citizen and the only demo this phase's own packaging work can put in
  front of a customer — entity resolution at τ 0.99/0.95/0.80, Louvain community structure, the
  pathfinder's full `max_hops` range, and an access-control-lengthened-path case, per ADR-035 §C5.
  `make licence-check`'s own scope (ADR-035 §C7: Python/npm package metadata only, never a data
  file's own licence) is extended in the same pass, so a future fixture carrying its own data
  licence (ADR-035 §C6's IBM AML-Data case) does not pass unexamined the way it does today.
- **A pathfinder acceptance-scenario step (B21, or an ADR addendum accepting its absence) —
  `07_BUILD_PLAN.md`'s own "Gaps with no owning phase" entry, this session's Part A.**

**Exit.** Both acceptance scenarios pass unchanged on `local-lite`. A `backup` → `restore` cycle
reproduces the graph from staged Parquet. An export containing an `S2`-marked item is blocked,
names the item, and proceeds only with a recorded justification.

`adapters/graph_janusgraph`, `adapters/analytics_clickhouse`, ComputePort Tier 3 and the
`cluster` half of this phase's own former exit criterion move to Phase 8a
(`06_DECISIONS.md` ADR-022's third addendum, 20 September 2026) — that phase's own verification
needs real multi-node infrastructure this phase's own bullet list does not, so each phase's exit
criterion is now a test it can actually run on the infrastructure it has, not a criterion split
across two without saying so.

**This phase's own close is also when `06_DECISIONS.md` ADR-031 schedules the repository split —
`docs/` into `spec/` and `process/`, `README.md`/`DEMO_GUIDE.md` to the repository root — not
before, regardless of whether Phase 8a has closed by then.** Not built as part of this phase's own
outcome bullets above; recorded here as the trigger point per that ADR's own reasoning (the
specification needs to have stopped moving shape first, and the move must not wait on Phase 8a's
own infrastructure uncertainty). The move ships with `scripts/doc_citations_check.py`, a new
CI-gating check (joining `Makefile`'s `ci` target alongside `schemas-check`/`licence-check`) run
once before the move as a baseline and again after as the permanent gate — see ADR-031 for why
both runs matter.

**This same close step is Trigger A under `06_DECISIONS.md` ADR-034** (21 September 2026, supersedes
ADR-031 — read ADR-031 for the physical `spec`/`process` layout, ADR-034 for the licence boundary,
the publication trigger, and everything downstream of it). Trigger A fires here and moves files; it
does **not** fire Trigger B (publication), which is owner-instructed only, after alpha and beta
testing, and is a new seeded repository rather than this one made public. Six deliverables are owed
at this close step, per ADR-034, beyond the restructure itself:

- **B3/B4 — record, do not build:** the destination account (`github.com/ospreyflow`, a personal
  account today) and the reserved-but-unclaimed `github.com/ospreyflow/ospreyflow` name stay exactly
  as ADR-034 records them; whether the account converts to an organisation is Trigger B's own open
  item, not this close step's.
- **B5 — authorship record.** A dated authorship record, created in the private build tree at this
  close step (ADR-034's own B6 deliverable, cross-referenced from B5) — without it, Trigger B's
  neutral-identity squash later removes the evidence of who wrote the build along with the name.
- **B7 — tester-artefact gates are a blocking prerequisite of Phase 8's own harness/packaging work,
  not a follow-up to it.** The harness this phase's own outcome bullets already build must ship, from
  its first version, with both ADR-034 assertions (no private-tree file in the artefact; no B5
  identifier in the artefact, including in build-time version metadata) — no artefact reaches any
  third party, alpha or beta tester included, until both exist.
- **`scripts/doc_citations_check.py` gains the ADR-citation scope ADR-034's own B2 finding names** —
  flagging any product-tree docstring's own `06_DECISIONS.md` ADR-number citation, since that file
  stays private past publication even though it stays inside `spec/` at this close step.
- **B2/B6 — `LICENSE` and `NOTICE`, present in the product subtree, new at this close step.**
  ADR-034 §B2/§B6 decide *what* licence and *who* the holder is (Apache 2.0; "The OspreyFlow
  Authors") but record no step that actually creates either file — checked directly: no `LICENSE`,
  `LICENSE.txt`, `NOTICE` or equivalent exists anywhere in this repository today, and neither
  `make licence-check` leg (`scripts/licence_check.py`'s own docstring, and ADR-034 §B2's own text)
  checks for one; both validate third-party dependency licences only. A decision recorded in
  `06_DECISIONS.md` is not the same thing as a build step that discharges it, and this gap is the
  difference between the two. **Owned by Trigger A, not Trigger B**: the published artefact is
  seeded from this subtree (ADR-034 §B4), so `LICENSE`/`NOTICE` must already be present and correct
  in it before that seeding, not written for the first time at publication. Only the copyright
  *year* is Trigger B's own (ADR-034 §B6: "Year set at Trigger B, being the year of first
  publication") — the holder name, the licence text itself, and the files' own presence are not
  year-dependent and are not deferred.
- **A new `licence-check` gate, built at this close step: the project's own `LICENSE`/`NOTICE`,
  not only its dependencies'.** `make licence-check` today runs two legs (`pip-licenses` against
  Python, `license-checker` against `node_modules`), both scoped to third-party dependency licence
  *metadata* — confirmed directly against `scripts/licence_check.py`'s own docstring and ADR-034
  §B2's own "Neither leg... existing script" finding. Nothing anywhere checks that this project's
  *own* `LICENSE` file exists, is the unmodified Apache 2.0 text (not silently edited or truncated),
  and that `NOTICE` names the holder ADR-034 §B6 records ("The OspreyFlow Authors") — a gap in the
  same class the Phase 0 allowlist gap this script's own docstring already discloses, just on a
  different axis (own-project compliance, not dependency compliance). Add to this close step's own
  scope, sibling to the two existing legs rather than folded into either: a third check (or a small
  script `licence_check.py` gains a mode for) asserting `LICENSE` is present and byte-identical to
  the canonical Apache 2.0 text, and `NOTICE` is present and contains the B6 holder string.

**Recorded, not decided: per-file Apache 2.0 headers across the product tree — an open item for the
owner, the same "not made here" treatment ADR-034 §B6 already gives DCO-vs-CLA.** Nothing in
`06_DECISIONS.md` or this document commits to (or against) a header on every source file, only to
the licence covering the tree as a whole (`LICENSE`/`NOTICE`, above). **Cost, if chosen:** roughly
455 source files across the Apache-scoped tree today (321 Python files under `packages/`,
`services/`, `scripts/`, `tests/`; 134 TypeScript/TSX/JS/MJS files under `apps/`) — a number that
will have moved by the time this is decided, not a commitment to touch exactly that count.
**No tooling in this repository applies headers today** — checked directly: no header-management
tool (`licenseheaders`, `addlicense`, or similar) appears in `pyproject.toml`, `package.json`, or
`Makefile`; introducing one, not adapting an existing one, would be the first step if the owner
decides to build this.

---

## Phase 8a — The cluster profile

**Outcome.** The platform runs on more than a laptop, and both acceptance scenarios pass there
too.

- `adapters/graph_janusgraph` and `adapters/analytics_clickhouse`, both conformance-green against
  the `cluster` profile.
- ComputePort Tier 3 (GraphFrames on Spark, or HugeGraph Vermeer) — deferred here from Phase 7
  (`06_DECISIONS.md` ADR-028) because the dev host cannot host it at all, not merely awkwardly;
  its own conformance case joins `tests/conformance/compute_port` the moment it registers, with
  no change owed to that suite (ADR-028's own design already accommodates a third tier).
- The Postgres connection-pool hardening Phase 7 Stage 1 found (two live Conduit instances
  together exhausted `max_connections`) — real here for the first time, since concurrent
  instances are the `cluster` profile's own defining property and cannot be *demonstrated* on
  `local-lite` at all. **Bounded arithmetically, not yet demonstrated, by Phase 7 Stage 6c**
  (that phase's own outcome bullets): all ten Postgres-backed stores' pools are now explicitly
  sized (`min_size`/`max_size` each), with the resulting per-instance and two-instance totals
  against Postgres's own `max_connections=100` computed and recorded there. One instance is safe
  under any load; two are safe at rest but not at simultaneous worst-case saturation (110 against
  100) — the arithmetic this bullet's own gap lacked before, though a live two-instance
  reproduction is still this phase's own to run.

**Exit.** Both acceptance scenarios pass unchanged on the `cluster` profile. ComputePort's three
registered tiers (Tier 1 `graphology`, Tier 2 `rustworkx`, Tier 3) return identical values within
`06_DECISIONS.md` ADR-028's own measured tolerance on the 5,000-node fixture. A sustained run of
two or more Conduit instances against the same Postgres does not exhaust its connection pool.

**Why this phase exists, stated plainly rather than left to be inferred from a bullet list.**
`06_DECISIONS.md` ADR-022's own second and third addenda have the full finding: Tier 3 and the
pool-hardening item share a verification profile neither Phase 8 nor any earlier phase carries —
provable only against real multi-node infrastructure, not a docker-compose stand-in for one. That
is the reason for the split, not bullet count; B16/B18 landed on Phase 8 in the same period and
correctly stayed there, being small additions reusing components Phase 5 already shipped.

---

## Gaps with no owning phase

Unlike the known-gaps lists inside Phase 5, Phase 5a and Phase 6 above — each a thing that stage's
or phase's own work found and deferred — an entry here is something no phase's bullet list claims
at all. A phase about to close checks this list the same way Phase 6's own stages checked the
previous phase's known gaps before scoping their work, so an orphaned intention doesn't sit
findable only from whichever phase happened to notice it.

- **Highest-consequence item in this list for Phase 8 — the principal-resolution gap, consolidated
  from three separate disclosures of what is one missing capability, not three.** Stated once,
  plainly: there is no way to obtain a live `Principal` for a stored `owner_id` without a request
  in flight carrying that owner's own bearer token — `services/api/auth.py`'s
  `PrincipalResolver.resolve()` is the only place a `Principal` is ever constructed, and it builds
  one from JWT claims only; no id-keyed directory exists anywhere in this codebase to look one up
  cold. Three manifestations, each found independently, each previously recorded as if it were its
  own gap:
  1. **General background evaluation** — Phase 7 Stage 6b's own "no-principal-directory gap" entry
     (this document, Phase 7's own bullets, `principal_for_owner: Callable[[str], Principal |
     None]`), proven by `test_a_hotlist_with_no_resolvable_owner_principal_is_skipped_not_run_as_a_
     stale_one`.
  2. **Cross-analyst hotlist/monitor firing** — `06_DECISIONS.md` ADR-036's own Phase 7 Stage 6c
     amendment: access is resolved fresh only when the saving analyst is the current requester, so
     a hotlist or monitor owned by anyone else is skipped, not evaluated, for every trigger that
     isn't that owner's own action.
  3. **Resolution-triggered monitors** — this document's own Phase 7 Stage 6c entry (Part 1 of
     this session's own carry-over work): corpus-wide resolution has no live principal for *any*
     caller, proven by
     `test_a_monitor_does_not_fire_on_a_match_created_by_resolution_with_no_new_ingest`.

  **Stage 6's own operational value is blocked on this, stated plainly rather than left to be
  inferred from three separately-qualified exit criteria.** As delivered across 6a, 6b and 6c, a
  monitor or hotlist fires only when the owning analyst's own studio-recipe run or manual
  assertion is what triggers the check — every other route to a match (a different analyst's
  ingest, a different analyst's manual link, corpus-wide resolution regardless of who triggers it)
  produces no alert, observably skipped rather than silently wrong, but skipped all the same. The
  CoLP walkthrough `08_ACCEPTANCE_SCENARIOS.md` Scenario B narrates end to end (B12/B13/B14/B20)
  passes only because it is one analyst throughout; the operational case the feature exists for — a
  warrant seizure logged by a different unit than the one that set the original hotlist entry —
  does not. Everything built across three stages of Phase 7's own Stage 6 is waiting on this one
  capability, not on any of its three symptoms individually. Owning phase: **Phase 8**, alongside
  the harness/identity-provider work already deferred there — the fix is a principal directory (or
  an equivalent service-account/lookup mechanism), not a third patch to `principal_for_owner`.

- **The Conduit's horizontal scalability is asserted and unverified, three ways, and that is one
  finding, not three separate ones.** `03_CONDUIT_MIDDLEWARE.md` §1 states the claim plainly: "Any
  Conduit instance can serve any request for any session; kill one mid-investigation and the
  analyst notices nothing." Three independent things now bear on whether that sentence is true:
  1. **The claim's own only proof cannot run.** `test_statelessness.py`'s
     `test_a_second_process_continues_an_investigation_the_first_was_killed_mid` (below, in this
     same list) is the *only* place in the repository that exercises the claim at all, and it
     currently fails to even connect (`httpcore.ConnectError`) in this environment — undiagnosed as
     to whether that is a test-harness process-spawn problem or a real regression.
  2. **The one number that has been computed says two instances do not fit.** Phase 7 Stage 6c's
     own connection-pool arithmetic (this document, that stage's outcome bullets): 55 connections
     per instance at worst-case saturation, against Postgres's own `max_connections=100` — two
     instances' simultaneous worst case is 110, over the ceiling. One instance is safe under any
     load; concurrent instances are not, under load, regardless of whether session state is
     correctly stateless.
  3. **Phase 8a's own outcome bullet already names this as work still to do**, not yet done: "a
     live two-instance reproduction is still this phase's own to run."

     Individually, each of these three is disclosed already, in its own place, as its own finding.
     Together they mean something stronger than any one of them alone: the specific architectural
     property this platform's horizontal-scaling story depends on has never been demonstrated
     true, has one arithmetic finding suggesting a real ceiling under concurrent load, and has its
     one intended proof currently unable to run — three independent reasons to distrust the same
     claim, not three unrelated gaps that happen to sit near each other. Owning phase: **Phase
     8a**, the same phase already carrying the two-instance reproduction and the only phase with
     the real multi-node infrastructure (`06_DECISIONS.md` ADR-022's second/third addenda) to prove
     or disprove any of the three at once; Phase 8's own diagnosis of why `test_statelessness.py`
     cannot currently connect (below) is this phase's prerequisite, not a substitute for it.

     **Cheapest first step, stated rather than left for Phase 8a to rediscover:** raising
     Postgres's own `max_connections` past 110 (a one-line configuration change, no code touched)
     removes the two-instance worst-case ceiling the arithmetic above found, immediately, without
     waiting on either the harder fix (a shared pooler such as PgBouncer, or tighter per-store caps
     across ten files for diminishing returns) or the slower one (diagnosing and fixing
     `test_statelessness.py`'s own inability to run, which verifies session continuity, a different
     half of the same claim, and buys no connection headroom by itself). Raising the limit does not
     make the claim *true* — only the statelessness test running green does that — but it is the
     cheapest lever on the one part of the claim already known, arithmetically, to be false at
     scale today.

- **The ingest pipeline's OpenSearch full-text-and-embeddings index has no owning phase.**
  `03_CONDUIT_MIDDLEWARE.md` §5.1 names it as the ingest pipeline's own `index` step ("full text
  and embeddings into OpenSearch"), `03_CONDUIT_MIDDLEWARE.md` §3.3 specifies `POST /v1/search` as
  "federated search across graph, documents, index", and `02_GLASS_FRONTEND.md` §2's workspace
  mockup already shows the search box as "Search entities, identifiers, documents" — three
  separate points in the spec assume this exists, and no phase's own bullet list above builds it.
  `services/api/search.py`'s own docstring already discloses half of this live in the code
  (`SearchRequest`/`search()`): "the index leg is OpenSearch, which is not wired into any
  deployment profile until later... document content itself does not exist as a searchable thing
  until extraction, Phase 6" — Phase 6 is what makes document content extractable, not a commitment
  to build the OpenSearch adapter itself, and no phase after it picks that commitment up either.
  **Not the same gap as Phase 8's own OpenSearch use** — `04_VAULT_BACKEND.md` §1.4 ties OpenSearch
  to `adapters/graph_janusgraph` (Phase 8) as JanusGraph's own cluster-profile mixed index for
  graph-property search, a different consumer of the same underlying store. Phase 8 closing does
  not close this gap. Needs a scoping decision — its own phase, or folded into an existing one
  (Phase 2's ingest pipeline is the natural producer of the index writes; Phase 4's Glass search
  box is the natural consumer of reading it) — before a future phase assumes `/v1/search`'s
  document/index legs already work because the graph leg does.

- **Nothing triggers resolution or alerting against a live corpus.** `services/resolve`'s
  `resolve_entity_type`/`write_same_as_edges`/`detect_conflicts`/`record_conflicts` are real and
  tested — Phase 6's own gaps list already discloses "no ingest hook, no cron, no manual endpoint
  ... every test calls them directly" — and no hotlist/alert code exists anywhere in `services/`
  or `packages/` to consume a match once one is found. `08_ACCEPTANCE_SCENARIOS.md` Scenario B's
  B8 (a scored `SAME_AS` edge exists to examine) and B13/B20 (ingest raises an alert) all presume
  this trigger runs; Phase 7's hotlist/saved-pattern-monitor bullet builds the alert's display, not
  the corpus-wide job that would ever fire one outside a test calling the functions directly.
  **No longer just a scoping question** — see `06_DECISIONS.md` ADR-025 for the full design (what
  runs it, on what event, against which population, under what principal, what happens when a run
  overlaps the previous one, how a partial run is recovered) and the Phase 7 outcome bullets above
  for where it lands.

- **`GraphPort` has no method to list a type's population.** Found while designing ADR-025's own
  trigger, not by inspection alone: `resolve_entity_type` is a pure function over a
  caller-supplied node list, and nothing in `packages/ports/graph.py` can produce "every `Person`
  node" or "every node of type X touched since Y" — `find_node`/`search_nodes` need an exact
  identifier value, `expand`/`paths` need a known seed, `match` needs a bounded pattern. A
  structural port gap, not an orchestration one: `06_DECISIONS.md` ADR-025 proposes a new,
  paginated, access-controlled `GraphPort` method, conformance-suite-first per standing rule 1 —
  needed before any corpus-wide resolution job can run against more than a caller-already-knows
  population.

- **No device-extraction connector or format exists, and no phase has ever claimed one.** Phase
  2's own outcome bullet promised "CSV, JSON and generic delimited" (its own known-gaps list above
  now records that only CSV shipped) — but device-extraction formats (Cellebrite UFDR, XRY) were
  never promised by that bullet or any other; `packages/schemas/ingest.py`'s connector catalogue
  carries them as labels only. `06_DECISIONS.md` ADR-024 depends on this: the deterministic
  MSISDN↔IMSI `SAME_AS` write it proposes needs a structured record that reports both values
  together, which only a device-extraction (or equivalent) connector would ever produce. Needs a
  scoping decision — its own stage inside whichever phase eventually builds it, per ADR-024 — not
  an assumption that Phase 2 closing or Phase 6a's Glass work already covers it. **Phase 7's own
  exit criterion (ADR-027) confirms this gap is not closed by that phase either** — B1 and B13 are
  both scoped around it, not through it: B1 to its two-CDR-files half only, B13 to a CDR-carried
  hotlisted identifier rather than the literal seizure-record fixture.

- **Fake-based tests in this repository do not exercise security-relevant paths, and that is now
  a pattern across four independent findings, not a property of any one fake.** Each instance was
  found by someone deliberately going looking for coverage that turned out not to exist; none was
  found by a test failing. That is itself the property worth recording: it means the next instance
  is currently caught only by an audit, not by the suite.

  **Instance one — `FakeGraphPort` (`tests/services/api/working_set/fakes.py`) ignores `principal`
  on `expand`.** Checked precisely, correcting an initial "eleven files" estimate that turned out
  to be a substring match: `grep -rl FakeGraphPort tests/` also matches seven independently-defined,
  unrelated `_FakeGraphPort` classes (`tests/extract/test_writer.py`, `tests/resolve/
  test_conflict_pipeline.py` and `test_same_as_writer.py`, `tests/services/api/test_review_routes.py`,
  `test_review.py`, `test_studio_verify_routes.py`) that implement `get_node`/`upsert_edges`/etc.
  for entirely different code paths, several of which *do* simulate their own principal check
  correctly (e.g. `test_review_routes.py`'s own `_FakeGraphPort.get_node` checks `owning_unit`).
  The actual shared, public `FakeGraphPort` — the one whose `expand(req, principal)` records the
  request and returns a fixed `Subgraph` regardless of who asks — has exactly three real
  consumers: `test_manual_resolution.py`, `test_resolution_threshold.py` and `test_service.py`,
  all in `tests/services/api/working_set/`. Every test built on it that exercises resolution
  clustering was therefore only ever proving `compute_clusters`' own logic against input the fake
  declares safe by construction, never proving the filtering that safety actually depends on.

  **Instance two — the twenty-two `review.py` tests that passed identically either side of the
  real `AND owning_unit = $2` fix.** Found during Phase 6's own access-control pass: a fake-backed
  suite is not evidence a query is scoped correctly if the fake never runs the query at all. The
  fake returning a plausible-looking result regardless of the fix being present or absent is
  indistinguishable, from inside the suite, from the fix working.

  **Instance three — `set_resolution_threshold`'s (and `_manual_assertion`'s) own unfiltered
  `node_ids`, found this session while scoping Phase 6a Stage 2, and checked precisely enough to
  correct the first theory of the bug.** `node_ids = list(nodes_by_id.keys())` came from
  `source_fidelity_nodes` — the investigation-*shared*, unfiltered node set — and both
  `compute_clusters` calls (`before`/`after`) ran over that unfiltered list in *both* methods
  (Stage 1's own fix to `_manual_assertion` only added the two-named-node existence check; it did
  not narrow this population). The first hypothesis was an aggregate-count leak through
  `merged`/`split`/`affected` — checked directly and it does **not** hold: `GraphPort.expand`
  already excludes any edge with either endpoint hidden from `principal`
  (`test_projection_access_control.py`), so a node the caller cannot see always arrives with no
  edges and sits in `compute_clusters`' union-find as an untouched singleton at every τ, never
  registering as affected. The **real** defect is a write, not a read: `compute_clusters` returns
  a mapping over whatever ids it is given, and persisting that mapping unfiltered let a principal
  blind to a node silently reset that node's own stored `resolution.cluster_id` — collapsing
  state a better-cleared principal had legitimately established, purely by calling their own
  threshold or manual-link endpoint. `tests/services/api/working_set/
  test_resolution_threshold_access_control.py` proves this against the real adapter, and proves it
  the way this document requires: reverting the narrowing reintroduces the exact failure.

  **Instance four — `explain_cluster` (`GET .../resolution/explain/{cluster_id}`), found in the
  same pass, and worse in kind.** This route resolves a `cluster_id` to its member node ids from
  the same unfiltered `source_fidelity_nodes` population, with nothing checking that every member
  is visible to the calling principal before returning `member_node_ids` directly — a live route,
  not a latent one, that handed back a hidden node's own id verbatim rather than merely an
  aggregate count. Fixed the same way: candidate membership narrowed to `expand`'s own
  principal-filtered result, an empty result after narrowing raising `ClusterNotFoundError`
  (indistinguishable from the cluster never existing, standing rule 3).

  No version of `FakeGraphPort` could have caught instance three or four, because none of its variants
  simulate classification-based filtering at all — a fake that returns everything to everyone
  cannot fail a test that checks whether everything was returned to everyone.

  **The implication, stated at the strength these four instances actually support, not stronger.**
  Not "fakes are categorically unable to prove access control" — a fake that itself implements a
  correct, principal-aware check (as `test_review_routes.py`'s own `_FakeGraphPort.get_node` does)
  is fine to build on. The implication is narrower and, checked against all four instances, holds
  exactly: **a fake earns the right to stand in for an access-control claim only when something
  separately proves the fake's own simulated behaviour matches the real adapter's — and nothing in
  this repository currently does that for any fake.** Until something does, the practical rule is
  the same either way: an access-control claim needs a real adapter behind its test, the pattern
  `tests/resolve/test_projection_access_control.py` and `test_manual_resolution_access_control.py`
  already establish — compose the real adapter's own filtering with the pure logic under test,
  rather than trust a fake's silence about `principal` to mean it's handled. Instance three is a
  second, independent lesson on top of that one: even a *correct* read-time filter (the `expand`
  call both methods already made) does not automatically make a *write* derived from a broader,
  unfiltered population safe — the two have to be checked separately, and were not.

  Recorded here, spanning phases, rather than in Phase 3 (which built `FakeGraphPort`), Phase 6
  (which found instance two) or Phase 6a (which found instance three) alone — precisely so an
  audit of any of them finds the pattern without having to rediscover it, the same failure mode
  Phase 5's own `playback`/`multi-track` deferral sat unread in a component header for four phases
  before this document named it.

- **RESOLVED, same session it was found.** Three live instances of the fetch-then-check
  authorization bug class — `services/api/sites.py`'s `SiteStore.get_authorized`,
  `services/api/investigations.py`'s `InvestigationStore.get_authorized` and
  `services/api/studio_recipes.py`'s `StudioRecipeStore.get_authorized` — were found while scoping
  `06_DECISIONS.md` ADR-041, each fetching a row unscoped then comparing `owning_unit` against
  `principal.org_unit` in Python. Checked individually before fixing, so the record distinguishes
  a latent hazard from an actual leak (ADR-041's own account has the full check per store): **all
  three were hazards, not leaks** — the Python-side comparison was correct in every case and no
  other caller bypassed it, so no unauthorized data was ever actually returned; the defect was the
  unscoped row reaching process memory before the (correct) rejection, not a wrong rejection.
  ADR-041 was accepted (option (b), the mechanical `authorized-query-check` script) the same day
  it was proposed, all three stores fixed to the query-scoped shape and reverified against live
  Postgres, and the checker wired into `make ci`/`ci.yml`. **A residual, smaller gap found in the
  same pass, not yet closed:** `InvestigationStore` has no direct-Postgres test file of its own
  (`test_sites_store.py`/`test_studio_recipes_store.py` exist; nothing named
  `test_investigations_store.py` does) — its access control is proven only indirectly, through
  `app.py`'s own route-level fakes, the exact "fakes never exercise the real query" gap this same
  section already warns about elsewhere. Owning phase: **Phase 8** — a direct-Postgres
  `InvestigationStore` test file, mirroring `test_sites_store.py`'s own shape.

- **The class the entry above is one instance of, stated at its own level rather than left implicit:
  a conformance suite in this repository binds every *registered* adapter to one shared contract; a
  hand-written local test double, because it is never registered anywhere, bypasses that binding
  entirely and answers to nothing but whatever the one test file that defines it happens to assert.**
  Three concrete citations, not all the same kind of drift, which is the point — the class is
  "un-bound double," not "access-control double" specifically:
  - `_NullExtractionCandidateStore` (this session's own Part A, `test_phase6_exit_criterion_end_to_
    end`) — **interface drift.** The real `ExtractionCandidateStore` contract gained
    `store_document_text` in Phase 6a Stage 4; this local double, defined once inside
    `tests/scenarios/test_phase6_extraction_and_resolution.py` and registered nowhere, was never told.
  - `FakeGraphPort` (`tests/services/api/working_set/fakes.py`) — **behavioural drift**, the entry
    above's own instance one: it ignores `principal` on `expand`, so every test built on it proves
    `compute_clusters`' logic against input the fake declares safe by construction, never the
    filtering that safety actually depends on.
  - The `review.py`/`set_resolution_threshold`/`explain_cluster` fakes (instances two through four,
    above) — **silent-pass drift**: each kept returning a plausible result on either side of a real
    access-control fix, because the fake never ran the query the fix changed at all.
  Every one of these is a different failure shape (a missing method, an ignored parameter, an
  entirely bypassed query), which is exactly why "write more fakes carefully" does not close the
  class — carefulness is a property of one double at the moment it is written, not of the class over
  the life of the contract it stands in for.

  **What would have to be true for a double to be *covered*, stated as a criterion rather than a
  hope.** Either (a) the double is registered in the same adapter registry a conformance suite
  already iterates (`tests/conformance/registry.py`'s own `GraphAdapterFactory`/
  `AnalyticsAdapterFactory`/`ComputeAdapterFactory` shape — the same registration `06_DECISIONS.md`
  ADR-028's own Tier 1 compute entry uses for a non-database adapter, so "double" and "conformance-
  registered" are not mutually exclusive), and made to pass the same suite real adapters do for the
  properties it is relied on to simulate; or (b) a standalone parity test asserts the double's own
  behaviour matches a real adapter's for the *specific* property under test (the shape
  `test_resolution_threshold_access_control.py` and `test_manual_resolution_access_control.py`
  already use — composing the real adapter's own filtering with the pure logic under test, rather
  than trusting the double). Neither exists today for any double named above; a double with neither
  is unbound, and unbound is the actual defect, not any one double's own specific miss. **Not fixed
  here — recorded as a class, owning phase Phase 8**, the same close-of-build hardening pass this
  session's other disclosed gaps (A1, A2 above) already land in.

- **`deltaClient.integration.test.ts`'s own harness (`apps/workspace/test/glass_test_server.py`,
  its `seedOneNode` helper) cannot exercise any resolution endpoint that checks real node
  existence — `manual_link`/`manual_split`/`set_resolution_threshold` all now do, correctly, via
  `GraphPort`.** Found while trying to add a real WebSocket-level proof that `DeltaReproject.
  affected_cluster_ids` (Phase 6a Stage 2) round-trips end to end: `POST .../seed` only writes into
  the *working-set store* (`WorkingSetService.seed`'s own docstring: the caller-supplied objects
  are never handed to `GraphPort`), never into the real ArcadeDB adapter this harness's app
  actually runs against. A node seeded this way passes every working-set-store check but fails
  `GraphPort.get_node`/`expand`'s own seed-node query — a real `404 node_not_in_working_set` from
  the live server, not a fixture artefact — so `resolution/link`, `resolution/split` and `PUT
  resolution/threshold` are all, today, untestable through this particular harness. The existing
  three WebSocket-level tests never needed a real graph node (`add`/live-push/resync all work over
  the working-set store alone), so this went unnoticed until Stage 2 needed one. **Not fixed
  here** — closing it means giving the harness (or a small, explicit test-only route) a way to
  write a real node into `GraphPort` before seeding the working set, which is its own scoped piece
  of infrastructure work, not a Stage 2 line item. The Python-level proof
  (`tests/services/api/working_set/test_resolution_threshold_access_control.py`, against the real
  adapter directly) stands in for the WebSocket-level one in the meantime; `models.ts`'s own
  `DeltaReproject.affected_cluster_ids` addition is otherwise unverified against the real wire
  format beyond type-checking.

- **`keyboard.spec.ts`'s walkthrough had no auto-discovery of new canvas actions, and `CLAUDE.md`
  rule 13's standing rule was a stopgap for that, not a fix — closed by Phase 6a Stage 4, not left
  open.** Confirmed directly while closing Phase 6a Stage 1's own keyboard gap: the spec was a
  hardcoded sequence of steps, so a new action with no step added was invisible to it — Phase 4's
  own exit criterion ("keyboard navigation reaches every canvas action") was enforced by a test
  structurally unable to detect its own violation. Rule 13 made adding that step the new action's
  own author's responsibility, in the same change, rather than a follow-up — cheap, and adopted
  for Stage 2 onward, but it depended on being remembered, which was the exact failure mode it
  existed to close, and it had already let four actions go untested on its own by the time Stage 4
  checked, before that stage added anything.

  **The stronger fix, built in Stage 4 rather than left named:** `apps/workspace/keyboard/
  actionRegistry.ts` — `GlassCanvas` exports a plain list of its own action ids
  (`CANVAS_ACTIONS`); each `keyboard.spec.ts` case calls `registerCovered(id)` at the point it
  actually proves that action; a final test asserts every registered id was covered, failing with
  the exact missing ids rather than passing silently. The four pre-existing gaps (ring-cycling, the
  `"manual-split"` item, the per-edge-type item through the menu itself, dismissing a transient
  overlay) were retrofitted in the same change rather than left red against a newly-built gate.
  Whichever surface Phase 7's metrics panel, visual query builder or pathfinder add next is a new,
  separate keyboard-driven surface in this same sense — each should get its own action list and
  spec-level registry the way `GlassCanvas`'s did, not a shared one; this entry's own "how a
  non-canvas action registers itself" question was answered narrowly, for the canvas, and is worth
  re-checking rather than assumed solved generally the first time a genuinely different surface
  (not a further canvas radial-menu item) needs it.

  **That first genuinely different surface arrived in Phase 7 Stage 3 (the metrics panel), the
  re-check found a real gap, and Phase 7 Stage 4 fixed it rather than leaving it disclosed.**
  `GlassCanvas.tsx`'s own `onKeyDown` called `preventDefault()` on every `Tab` keydown once its
  container div held focus (the "establish/cycle the selection ring" branches) — correct for the
  canvas's own documented behaviour, but it meant native Tab-order focus could never leave the
  canvas to reach a sibling panel's own controls while the canvas held it: confirmed directly,
  not assumed, while writing `keyboard/metrics-panel.spec.ts` — a walkthrough starting focus on
  the canvas never reached the metrics panel's row buttons at all, in up to 20 Tab presses. Stage
  4 fixed it rather than carrying it forward disclosed — **not because its own query-builder
  surface turned out to be a second canvas needing the same fix** (`06_DECISIONS.md` ADR-032: it
  is a list/palette editor, never a `GlassCanvas` instance, so it never inherited this defect in
  the first place), but because a defect already found and left open is Stage 4's own closing
  pass's business regardless of what its own new surface turned out to need. Tab/Shift+Tab are
  no longer intercepted at all — establishing a ring moved to the container's own `onFocus`
  (reaching it by any means, not a keypress after arriving), and ring-cycling (needed for a
  lasso-selected set of non-adjacent nodes arrow-walk cannot reach) moved to
  `Ctrl`/`Cmd`+`ArrowRight`/`Left`, the key Tab's release freed up. `02_GLASS_FRONTEND.md` §6 is
  amended to describe the real behaviour. `metrics-panel.spec.ts`'s own work-around (starting its
  walkthrough from the panel's first control, not the canvas) is removed in the same change — the
  test now starts from the canvas and reaches the panel's row buttons in the real Tab order, the
  concrete proof the fix works rather than merely disclosing that it should.

- **A third instance of "an automated gate proves only the specific failure it was built to
  detect, not the class of defect its name suggests" — `Combobox.tsx`'s option selection was
  `onMouseDown`-only, on a control shipped since Phase 4 (`GlobalSearch`), and both `make
  glass-a11y` and every keyboard walkthrough written before Stage 4 passed it regardless.** The
  same shape as the other two instances already recorded in this list — the Fake-based-tests entry
  above ("each instance was found by someone deliberately going looking for coverage that turned
  out not to exist; none was found by a test failing") and `keyboard.spec.ts`'s own
  no-auto-discovery entry above it — but the detecting mechanism this time is neither a fake nor a
  hand-written walkthrough: it is `axe-core` itself, `glass-a11y`'s own gate
  (`02_GLASS_FRONTEND.md` §6). `axe-core` checks DOM structure and ARIA semantics — a `role`, a
  label, a contrast ratio — and a listbox option wired to `onMouseDown` instead of a real activation
  path is invisible to every one of those checks: the markup an assistive-technology user's own
  tooling reads (`role="option"`, `aria-selected`) was already correct, and a screen reader would
  have announced the option correctly. What was missing had no DOM signature at all — a plain
  JavaScript event-handler choice, checkable only by actually trying to select an option with a
  keyboard and observing that nothing happens. Found while wiring Stage 4's own `pin-node-from
  -search` keyboard action (`keyboard/query-builder.spec.ts`): the first walkthrough in this
  repository's history to attempt a keyboard-driven *selection* out of a `Combobox`, because
  `GlobalSearch`'s own prior callers (`App.tsx`'s global search box) had never been given a
  keyboard-only proving test naming a specific selected result. Fixed in the same change
  (`ArrowDown`/`ArrowUp`/`Enter`, `aria-activedescendant`) rather than worked around per-caller,
  the same "fix the shared primitive once" instinct `actionRegistry.ts`'s own namespacing fix
  followed alongside it.

  **The implication, at the strength this instance actually supports.** Not "axe-core is a weak
  tool" — it correctly proves what it is built to prove, the DOM/ARIA half of the accessibility
  floor, and continues to be the right gate for that half. The implication is narrower: **a gate's
  name (`glass-a11y`, "the keyboard suite") is not evidence of what it checks — only reading what it
  actually inspects is.** `axe-core` inspects structure; it cannot and does not execute an
  interaction and observe whether anything happened, which is exactly the class of defect a
  mouse-only handler is. For any gate this build adds next — `check-registry-coverage`-style static
  checks included — the question to ask before trusting a green result is not "does a gate with the
  relevant name exist and pass," but "what specific mechanism does this gate exercise, and what
  adjacent failure, however plausible-sounding under the same gate's name, would still pass it
  unnoticed." `apps/workspace/keyboard/registryCoverage.test.ts` (Phase 7 Stage 4, alongside this
  finding) is itself an instance of asking that question proactively: it is a static text scan, not
  an executed proof, and says so in its own header, rather than letting "the keyboard suite is
  green" imply more than a static scan can support.

- **Betweenness has no size-triggered Brandes-sampling fallback, though `02_GLASS_FRONTEND.md`
  line 206 already documents one should exist ("Betweenness (exact to 20k nodes, Brandes-sampled
  above)").** Found while building `services/api/compute_routes.py` (Phase 7 Stage 3): the same
  20,000-node figure is this route's own sync/job boundary, but neither `CentralityRequest`
  (Stage 2) nor `adapters/compute_rustworkx`'s own `centrality` method carries a sampling
  parameter or branch — the job-mode path runs the identical exact `rustworkx.
  betweenness_centrality` call regardless of population size, so a working set at or beyond the
  sync boundary gets an exact (slower, but not incorrect) result rather than the approximation
  the spec's own performance table assumes. Not fixed here — real algorithmic work (a sampled
  Brandes estimator, on both tiers, with its own accuracy/tolerance question for the cross-tier
  agreement case) that this route's own scope did not extend to invent unprompted, the same
  "disclose, don't silently fill" instruction the `Endpoint`-to-`Device` gap above and B15's own
  scoping already follow.

- **Phase 7's own metrics-panel bullet names three things — "two-metric comparison; size
  encoding; community hull overlay" — and Stage 3 built two of the three.** The ranked list, the
  second-metric comparison column and the community hull overlay (`metrics/MetricsPanel.tsx`,
  `metrics/hulls.ts`, `canvas/CommunityHullOverlay.tsx`) are real and tested; **node size scaled
  by the active metric's own value is not built.** `07_BUILD_PLAN.md`'s own Stage 3 plan priced
  size encoding's *performance* cost ("an `O(1)` reducer touch per node, not a new bottleneck")
  but that was a feasibility measurement, not the feature itself — actually threading a fetched
  metric value through to `canvas/nodeAttributes.ts`'s own per-frame `computeNodeFrameAttributes`
  (which currently sizes a node from its zoom band alone, `BAND_SIZE[band]`, nothing else) needs a
  real design pass of its own: how a value is normalised to a size range, how that interacts with
  the existing zoom-band scaling, and its own perf proof against `perf/perf.spec.ts`'s fixture —
  not assumed free just because the *per-node* cost was shown to be cheap. Disclosed rather than
  silently dropped from the bullet; not fixed here.

**On Phase 6's own citation of `test_review_routes.py`'s denial tests as evidence access control
is real (above): checked against this finding, and it survives unnarrowed, because it was never a
claim about `GraphPort`.** `run_extraction`/`accept_candidate`/`reject_candidate`'s access control
is `AuthorizedInvestigationDep` (real dependency-injection code, backed by a faked `Investigations`
store) and `ExtractionCandidateStore.get_authorized` (a Postgres-backed store in production, faked
here) — both Conduit-internal, neither one of the four ports `ADR-001` names, so `CLAUDE.md` rule
3's "access control lives in the adapter, injected into the traversal or the `WHERE` clause" does
not reach either: that rule is scoped to `GraphPort`/`AnalyticsPort`/`ComputePort`/`ModelPort`
specifically, not every store the Conduit happens to hold. The confirm/retract routes in the same
file *do* go through `GraphPort.get_node`, via that same file's `_FakeGraphPort` — a different,
unrelated fake from the one above, correctly simulating an `owning_unit` check — and that
composition is sound for a different, checked reason: `tests/conformance/graph_port/test_suite.py`'s
`test_unauthorised_get_node_matches_a_graph_where_the_node_never_existed` proves the real adapter
enforces the same thing the fake assumes. So both halves of Phase 6's own citation hold, for two
different reasons that happen to look similar: one because the rule they'd be checked against
doesn't apply to that store, the other because the real-adapter proof exists elsewhere and was
simply not the thing this particular bullet was citing.

**Not listed here: the `Endpoint`/`Device` traversal B15 needs.** It was found during the same
Scenario B re-check that surfaced the entries above, but it is a live contradiction between two
things the ontology already declares (`packages/ontology/default.yaml`'s `Endpoint.endpoint_kind`
and `Device.identifiers` both claiming `imei`), not an unclaimed intention — standing rule 7 makes
that an ADR, not a gaps entry. See ADR-023, resolved before Phase 7 rather than left open here.

- **The `graphify` `PreToolUse` hook had a zero compliance rate across the whole of Phase 6a,
  undetected for six days, and it took a direct question to surface it — not a test, not a review,
  not the hook itself.** `.claude/settings.json` (in place since 13 September) runs `graphify
  hook-guard read`/`search` before every `Read`/`Glob`/`Bash`/`Grep` call, printing a `MANDATORY`
  instruction to consult `graphify query`/`path`/`explain` first. Checked directly, not assumed:
  `graphify hook-guard read` and `graphify hook-guard search` both exit `0` unconditionally — the
  hook is advisory, not blocking, by construction of the installed tool itself, not a
  configuration choice this repository made. Across the whole of Phase 6a's Dossier work, `graphify
  query`/`path`/`explain` were called zero times; every lookup went through `Read`/`grep` instead,
  the `MANDATORY` reminder printed and not acted on, repeatedly, without anyone — human or model —
  noticing until asked directly whether the tool had been used at all. This is `CLAUDE.md` rule
  13's own admission ("depends on being remembered, which is the exact failure mode it exists to
  close") made concrete: not a suspicion this time, a measured zero.

  **A live test of the instruction's own accuracy, run in response to being asked, found a second,
  compounding problem: the instruction is also wrong often enough to teach ignoring it.**
  `graphify query "how does the radial menu handle Escape and keyboard dismissal in GlassCanvas"`
  — a real, focused question about the exact bug this phase's own closing pass fixed — returned a
  197-node BFS neighbourhood including files with no relationship to the question
  (`ConnectScreen.tsx`, `ingest/api.ts`), truncated at a 1200-token budget with the actually-useful
  answer plausibly among the 164 cut nodes. A direct `Read` of `GlassCanvas.tsx` and `Popover.tsx`
  found the real defect (a focus-loss bug, not anything a keyword-shaped BFS query was suited to
  surface) faster and more precisely. `CLAUDE.md`'s own instruction as written does not distinguish
  this case — a targeted read of a file already identified by reasoning — from the case the tool
  is actually built for: a broad "how does X connect to Y" question with no starting file in mind.
  An instruction that is wrong in the common case trains ignoring it in the case it would actually
  help, which is a real cost to every other "MUST"/"MANDATORY" instruction in `CLAUDE.md` by
  association, not only this one.

  **Decision: narrow the instruction, then enforce the narrower one — not one without the other.**
  Leaving it advisory, now that the compliance rate is measured at zero, changes nothing about why
  it was zero. Making the existing, over-broad instruction blocking (a `PreToolUse` hook can deny a
  call outright; `graphify hook-guard` itself cannot today, so this would need a new,
  locally-written hook script, not a settings change) would guarantee compliance and also guarantee
  the over-broad cases the live test above just found — forcing a worse answer on exactly the kind
  of question that surfaced this finding. Narrowing first closes the reason compliance was zero
  (an instruction wrong often enough to be worth ignoring); enforcing after narrowing closes the
  fact that "worth following" and "actually followed" are not the same thing once a control has an
  active mechanism and nobody is checking it. Narrowing alone, left advisory, repeats this same
  finding under a better-worded rule. **Narrowed** (`CLAUDE.md`'s own graphify section, this
  change): a scoped subgraph query is for a broad "how does X relate to Y" question or unfamiliar-
  codebase orientation with no file already identified; a targeted read of a file already named by
  reasoning, a prior message, or this document's own file-path references is a direct `Read`, not a
  query first. **Not yet enforced**: making the narrowed rule blocking needs a hook script this
  repository would own and maintain (deciding, per call, which case a `Read`/`Grep` falls into),
  real scoped work of its own, not a one-line `settings.json` change — named here as the next step,
  not built as part of recording this finding.

- **`graphify export wiki` had never been run on this repository; `graphify-out/wiki/index.md` did
  not exist, and `CLAUDE.md`'s own instruction to use it for broad navigation pointed at nothing.**
  Found and run in the same pass as the finding above (`graphify export wiki` — 334 articles,
  no LLM call, generated purely from the already-computed graph and labels). A rule pointing at a
  file that has never existed is a smaller instance of the same class of problem: an instruction
  nobody checks the truth of degrades the same way a nobody-enforces-it hook does.
- **The 130 communities `graphify update` renamed after Stage 4's own file changes are a labeling
  staleness, not a retrieval-precision one — checked against the installed tool's own source, not
  assumed.** `graphify/serve.py`'s `_query_graph_text` (the engine behind `query`/`path`/`explain`)
  reads `community`/`community_name` only to print a `community=<name>` annotation on each result
  line; neither field feeds seed-matching, BFS ordering, or the token-budget truncation that
  decides which nodes actually appear in an answer. The 130 renames themselves are the tool's own
  deterministic "named after its hub" fallback for a community whose *membership* changed enough
  that its old LLM-generated name no longer matched — membership is therefore already current;
  only the human-readable name for those 130 groups is a placeholder until `graphify label` is run
  to re-generate descriptive ones. A stale name could mislead a reader following it to a specific
  named group; it cannot cause `query`/`path`/`explain` to return the wrong nodes.

- **`GraphArcadeDBAdapter.paths()`'s two-query hydration (ADR-033) has no defined behaviour if the
  graph mutates between the traversal and the hydration queries, and nothing tests it.** Found
  during Stage 5's own post-hoc verification. `adapter.py:506-517` builds each `Path` by indexing
  straight into the `nodes_by_id`/`edges_by_id` dicts the hydration queries returned
  (`nodes=[nodes_by_id[i] for i in node_ids]`) with no membership check first. If an element the
  traversal already returned an id for is deleted, or a principal's access to it changes (a
  handling reclassification, an `owning_unit` change), before the hydration query runs a few
  milliseconds later, that id is simply absent from the hydration result and the dict lookup raises
  a bare `KeyError` — **not** a silently short path (rule 2 would forbid that anyway) but also not a
  typed, caller-meaningful error: `services/api/app.py`'s `paths_route` (§1524) has no
  `except`/`exception_handler` for it, and neither does `app.py`'s own exception-handling block
  (§600 onward, which has a named handler for every other domain error), so it falls through to
  FastAPI's default handling — an undifferentiated `500`. No test exercises this: `tests/
  conformance/graph_port/test_suite.py`'s own path tests (`test_paths_finds_the_chain_and_respects_
  max_hops`, `test_paths_returns_hydrated_nodes_and_edges_not_bare_ids`,
  `test_unauthorised_path_length_matches_a_graph_without_the_hidden_hop`) all traverse a static
  graph; grepping the suite for "race"/"concurrent"/"mutat" returns nothing. **Owning phase: Phase
  8.** The fix shape is a typed error (`PathStaleError` or similar, alongside the domain errors
  `app.py` already names) raised when a hydration id goes missing, proven by a conformance case that
  deletes (or reclassifies) a path element between the two queries and asserts the typed error, not
  a `KeyError`/bare `500` — the same "name the test that would fail" discipline rule 12 asks for
  every stated invariant.

- **Nothing bounds the *work* a `paths()` traversal does — only its inputs (`max_hops<=8`, `k<=10`)
  and its output (`.limit(k)`).** Checked directly: `PathBuilder.render_gremlin`
  (`builders.py:265-281`) compiles a bare `repeat().until()` Gremlin traversal with no `timeLimit()`
  or step-count modulator; `ArcadeDBClient`'s own `httpx.AsyncClient` (`client.py:104-108`) sets
  `timeout=30.0`, which is a *client-side* socket/read timeout — abandoning the HTTP connection
  after 30s, not a server-side query budget — so a runaway traversal keeps consuming ArcadeDB's own
  heap after the Conduit gives up on it. The only actual ceiling is the container's fixed JVM heap
  (`deploy/compose/dev.yaml`'s `arcadedb` service, `-Xmx6G`), and that ceiling is already documented
  to fail under load: the same file's own comment records two concurrent conformance suites OOM'ing
  at the unset ~2GB default, a single sequential HMP graph build OOM'ing at 4G, and `ollama`'s
  resting footprint OOM-killing ArcadeDB repeatedly in Phase 6 Stage 6 — `07_BUILD_PLAN.md`'s own
  Phase 6 known-gaps list (§647-668) and this document's "Gaps with no owning phase" entries record
  a fourth and (with `test_statelessness`'s Postgres-exhaustion incident) fifth occurrence of the
  same class. An 8-hop `repeat()`/`simplePath()` traversal over a dense neighbourhood — exactly the
  shape a real corpus can produce and a fixture graph is unlikely to — is unbounded work with no
  budget between the request boundary and the JVM's own OOM killer. Disclosed rather than fixed
  here: no owning phase claims a server-side traversal budget (a Gremlin `timeLimit()` step, or an
  ArcadeDB-level query-cost ceiling) today: **flagged for Phase 8's own hardening scope, not yet
  assigned a concrete mechanism** — this entry exists so it is not silently discovered as a sixth
  OOM incident.

  **Follow-up, checked rather than assumed: nothing retries a `paths()` call after the Conduit's
  own 30s client-side timeout expires — not the Conduit, not the Glass, not a proxy (none exists;
  `deploy/` has no reverse proxy or gateway in front of `services/api`).** `ArcadeDBClient.command()`
  (`client.py:239-265`, which `gremlin()` calls and `paths()` calls that) is a single `await self.
  _http.post(...)` with no `try`/`except` and no loop around it — contrast `commit_transaction`
  (`client.py:168-209`) and `schema.py`'s DDL apply, both of which *do* retry on a classified-
  transient failure with backoff; reads through `command()`/`gremlin()` have no equivalent. On the
  Glass side, `GlassCanvas.tsx`'s `findPaths` (`GlassCanvas.tsx:575-581`) is a single bare `fetch()`
  with no retry wrapper anywhere in `apps/workspace/src` (`grep -rn "retry" apps/workspace/src`
  returns nothing outside this search itself). **So the specific compounding-load risk this
  follow-up was checked for does not exist today** — a slow query is not currently multiplied by a
  client retrying against a server still working through the first attempt. One adjacent, smaller
  finding from the same read, noted rather than expanded into its own entry: `findPaths`'s own
  `if (!response.ok) return;` means a timed-out/failed `paths()` call — including the bare `500`
  A1 above already names — is dropped silently on the Glass side too, with no retry *and* no
  analyst-visible error; the same disclosure A1 already gives the Conduit side applies here without
  a separate entry.

- **`Path.nodes`/`Path.edges`' on-path node styling is not colour-only, checked directly rather than
  assumed from the WCAG 1.4.1 concern that prompted the check.** `nodeAttributes.ts:128-134`:
  `state.onPath` sets `{ borderColor: TEXT_PRIMARY_DARK_HEX, borderSize: 2 }` where an unmarked node
  gets `{ borderColor: "transparent", borderSize: 0 }` — a ring that is *absent* for an off-path
  node and *present* at size 2 for an on-path one is a shape/size channel, not colour. It is also
  not the dominant cue: `GlassCanvas.tsx:207`'s `dimmed: dimmedNodeIds.has(nodeId) || (pathActive &&
  !onPath)` means every node not on the active path is dimmed to a 32% channel-colour mix
  (`computeNodeGraphAttributes`'s own `mixOklab(channelHex, SURFACE_PANEL_DARK_HEX, 32)`), the same
  lightness-contrast cue `nodeAttributes.ts:163-168`'s own comment names as "the dominant 'everything
  else' cue for a found path," with edge thickening layered on top. One precise caveat, not a gap:
  the on-path ring is visually identical in *size* (2px) to the `selected` ring — they differ only
  by hue (`TEXT_PRIMARY_DARK_HEX` vs `BRASS_HEX`) — so a node that is simultaneously on-path and
  selected is distinguished from a merely-selected one by colour alone. That is a real but narrow
  case (both states already reduce to "this node is currently notable" for an analyst), not the
  on-path/not-on-path distinction WCAG 1.4.1 is actually about, which the dimming and ring-presence
  channels both already cover.

  **Addendum: the on-path/selected pair on its own is still a colour-only distinction and is still
  WCAG 1.4.1, even though it is narrow and low-severity.** `computeNodeGraphAttributes`
  (`nodeAttributes.ts:105-137`) gives both states the identical `borderSize: 2` and differs only in
  `borderColor` — for the one pair of states this applies to, colour is the sole visual means of
  distinguishing them, which is exactly what 1.4.1 prohibits regardless of how many other states
  are involved or how minor the practical consequence. **Disclosed gap, owning phase Phase 8.** Not
  fixed here: `02_GLASS_FRONTEND.md` §1.1/§4 is the authoritative statement of this surface's own
  interaction-state vocabulary (nine channels, three provenance strokes, six interaction states),
  and a size/shape distinction added only for this one pairing is a change to that vocabulary, not
  a local code tweak — a spec decision (which non-colour channel, and whether it belongs on the
  on-path state, the selected state, or both) rather than something to pick unreviewed. Recording
  it, not choosing for the spec's own owner.

- **The `PathBuilder`'s own `elementMap()`-inside-`path()` ArcadeDB limitation is already recorded
  correctly, not only as a workaround-site comment.** ADR-033 (`06_DECISIONS.md`) is the primary
  record — the same "checked against a live instance, not assumed from the TinkerPop spec"
  discipline ADR-030's `match()` finding established first. `builders.py:251-261`'s own `PathBuilder`
  docstring cites it by name (`` `06_DECISIONS.md` ADR-033 ``), so a reader who only ever opens the
  adapter still finds the full record. No move needed; this entry exists only to confirm the check
  was made rather than assumed, per this session's own A4.

- **The pathfinder (`POST /v1/paths`, ADR-033) appears in no acceptance scenario, and that gap has
  been disclosed (`07_BUILD_PLAN.md` §978-991, Phase 7's own exit-criterion note) but never
  owned.** That note explains *why* Phase 7 can close without it (standing rule 9) and draws the
  parallel to hotlists/saved-pattern monitors — but that parallel does not actually hold past
  Phase 7's own close: hotlists/monitors get B20 to run against once Stage 6 lands, inside Phase 7
  itself, while nothing anywhere commits the pathfinder to ever gaining a scenario step. Checked
  directly, not assumed: unlike the pathfinder, both of the other two corpus-wide query surfaces the
  Stage 5 code comment (`app.py:1509-1521`) compares itself to — `/v1/search` (B4, B5, B7) and
  `/v1/patterns/*` (B19) — are themselves exercised by named acceptance-scenario steps, so
  "permanently accepted, the same class as `/v1/search`" is not available as a disposition here; the
  precedent it would lean on does not support it. **Owning phase: Phase 8.** Concretely: either add
  a step to Scenario B (a B21, in the same "journey" table `08_ACCEPTANCE_SCENARIOS.md` §105
  already uses) that exercises `POST /v1/paths` end to end through the Glass, or — if the owner
  judges the pathfinder to be a general-purpose tool like search rather than a scenario-bound step —
  record that decision explicitly as an ADR addendum at that point. Recording the gap is not owning
  it; this entry gives it a phase.

- **Two items this session found while re-establishing a clean baseline** (`docker compose down -v`
  then a single `make dev-up` then one full, uninterrupted `make test` run — not layered on top of a
  prior run's leftover state, which produced a noisier, misleading count on the first attempt) **are
  named here for the first time; neither had an owning phase before this entry. One is a genuine
  test failure; the other, re-scoped below, is an unverified architectural claim rather than a
  failing test — the two are different in kind and should not be counted together as "two failing
  tests" past this point.**
  - `tests/scenarios/test_phase6_extraction_and_resolution.py::test_phase6_exit_criterion_end_to_end`
    — `AttributeError: '_NullExtractionCandidateStore' object has no attribute
    'store_document_text'` (`services/api/review.py:363`, inside `run_extraction`). This is
    interface drift, not the OOM-driven flakiness this same test's name already carries three dated
    incident notes for (§647-668 above): Phase 6a Stage 4 added `store_document_text` to the real
    `ExtractionCandidateStore` contract (the Dossier's "message content renders... in place" work),
    and this closing-pass scenario test's own local `_NullExtractionCandidateStore` fake was never
    updated to implement it. A real, fixable bug in test scaffolding, not a product defect — not
    fixed in this session (verification only), owning phase **Phase 8**, fix shape: add
    `store_document_text` to the fake (a no-op is sufficient, matching what the name promises) and
    re-run the closing-pass suite to confirm the underlying OOM-sensitivity notes above are the only
    remaining known flakiness for this test.
  - `tests/services/api/test_statelessness.py::test_a_second_process_continues_an_investigation_the_
    first_was_killed_mid` — re-scoped from "failing test" to what it actually is. This test exists
    to prove a specific, named architectural claim — its own docstring cites it directly:
    `03_CONDUIT_MIDDLEWARE.md` §1, "Any Conduit instance can serve any request for any session;
    kill one mid-investigation and the analyst notices nothing." Two real `uvicorn` processes, the
    first `Popen.kill()`-ed outright, the second sent the rest of the same scripted session and
    required to continue it seamlessly — this is the *only* proof anywhere in the repository of
    that sentence; nothing else exercises it. It currently cannot run in this environment
    (`httpcore.ConnectError: [Errno 61] Connection refused`, raised from `map_exceptions` during
    the real HTTP call this test makes to its own second, separately-spawned process) — and while
    it cannot run, **statelessness is an asserted, unverified architectural claim, not a confirmed
    property with one failing regression test against it.** Those are different findings with
    different urgency: a failing test on a working property is a test-scaffolding problem; an
    unrunnable proof of a load-bearing architectural sentence (the same sentence Phase 5a's own
    Publish-route gap, §370-382 above, already leans on when it says horizontal scaling is "not yet
    correct" for a different reason) is a verification gap in the claim itself. Owning phase
    **Phase 8**: needs process-level tracing (not a re-run — the failure was consistent across the
    clean baseline run this entry is built on, not intermittent within it) to determine whether the
    refused connection is this test's own process-spawn/port-binding mechanism failing under
    whatever host or sandbox it is run in, or a real statelessness regression — until that
    determination is made, treat `03_CONDUIT_MIDDLEWARE.md` §1 as unverified in this environment,
    not as verified-and-then-regressed. **One of three disclosures now bearing on the same
    horizontal-scalability claim** — see "Gaps with no owning phase"'s own consolidated entry,
    above, for the other two and the combined finding.

- **`sweep_stale_conformance_databases` (`packages/adapters/graph_arcadedb/testing.py`) has now
  failed to prevent a disk-exhaustion incident twice, and this session found why, live, rather
  than by inspection: it is not one gap but three independent ones, each capable of defeating it
  on its own.**

  **One — the sweep only runs when something collects `tests/conformance/graph_port`, and the
  routine local/CI invocation never does.** The sweep is a session-scoped autouse fixture in that
  directory's own `conftest.py`; pytest never instantiates a fixture from a directory it does not
  collect. `Makefile`'s `test` target — the one this build's own headline test count has been
  reported against all week — carries `--ignore=tests/conformance/graph_port` as the first of ten
  `--ignore` flags (see the entry below, found the same session). A developer or session running
  `make test` alone, repeatedly, against a persistent local `make dev-up` stack accumulates
  `conformance_*` databases across every one of those sessions with the sweep never once firing,
  until the volume fills — exactly the shape of the incident this module's own docstring already
  describes. Only `make conformance`, `make test-all`, or CI's `conformance` job (which invoke
  pytest against that directory directly) ever trigger it.

  **Two — even when the sweep runs, it can only drop what the live server's own `list databases`
  reports, and a database can exist on disk without ever being registered.** Found live, not
  hypothesised: this session's initial disk audit found `conformance_1789987107_b63147993fc8` on
  disk (via `docker exec ... ls`), 172 minutes old, well past the 60-minute staleness window — yet
  it was absent from `curl .../api/v1/databases` before the sweep ran, and the sweep's own return
  value (`sweep_stale_conformance_databases` dropped exactly one database that same run) confirms
  it was never a candidate. A `create_database_if_absent()` interrupted after the directory is
  created but before the server's own registration completes leaves exactly this: present on disk,
  invisible to the one call the sweep uses to find what to drop. Removed by hand
  (`docker exec compose-arcadedb-1 rm -rf`) this session — no code path removes it.

  **Three — a hard-killed run can leave a database that crashes the server itself at boot, before
  the sweep's own owning fixture ever gets a server to call.** Also reproduced live, not
  hypothesised: this session's own `make test` run OOM-killed the ArcadeDB container mid-suite
  (`docker inspect` confirmed `OOMKilled=true`, `ExitCode=137` — see the memory-pressure finding
  below for why), leaving `conformance_1789998411_5906c2b40764` mid-transaction. On restart,
  `ArcadeDBServer.loadDatabases` threw an uncaught `com.arcadedb.exception.SchemaException: File
  with id '0' was not found` while reopening it, and the JVM's `main` thread exited — the container
  stayed "Up" (its outer entrypoint survived) but never became healthy and refused every
  connection. The sweep fixture needs a running server to call `list databases` against; a
  database that prevents the server from starting is by construction unreachable by a sweep that
  runs inside a test session against that same server. Recovered only by deleting the corrupted
  directory directly from the container filesystem before ArcadeDB would boot at all.

  **A fourth, related finding, not a sweep gap but the reason the sweep keeps having work to do:**
  the OOM kill above is not a one-off — reproduced twice in this session alone (once during a full
  `make test` run, once during an isolated single-test rerun with Ollama freshly restarted).
  `deploy/compose/dev.yaml`'s own comment already names cross-container memory contention with
  Ollama's resting footprint against ArcadeDB's `-Xmx6G` heap on the shared Docker Desktop VM
  (measured this session at 8GB total) as a known, previously-hit case, with "restart recovers
  cleanly" as the stated remedy — true for a clean kill, false when the kill lands mid-transaction
  and produces finding three above instead.

  Owning phase: **Phase 8**, the same closing-pass home as this section's two immediately preceding
  entries. Concretely, in order of leverage: (a) move `sweep_stale_conformance_databases` (or an
  equivalent) to run from something that always executes before a local or CI test session touches
  ArcadeDB, not from a fixture scoped to a directory ten `--ignore` flags routinely skip; (b) make
  the sweep's own candidate list disk-based (or reconcile disk against `list databases` and treat
  a mismatch as itself stale) rather than trusting server registration alone; (c) either lower
  ArcadeDB's configured heap or raise the VM's memory budget so the documented contention case
  stops being reproducible on a single ordinary session's first run, since a corrupted database is
  a strictly worse outcome than the orphan the sweep was built to handle, and recovering from it
  today requires a human with container filesystem access, not a test fixture.

- **`Makefile`'s `test` target's ten `--ignore` flags mean the port conformance suites are not
  routinely run by the one target this build's own headline pass/fail count has been reported
  against all week — found while diagnosing the sweeper gap above, not the original object of the
  search.** Checked each of the ten directly rather than assumed:

  | Ignored path | Why | Run by (routine) | Runs in CI |
  | --- | --- | --- | --- |
  | `tests/conformance/graph_port` | needs a live ArcadeDB | `make conformance`, `make test-all` | Yes — `conformance` job, every PR/push |
  | `tests/conformance/model_port` | needs a live LiteLLM/Ollama | `make conformance-model`, `make test-all` | Yes — `conformance-model` job, every PR/push |
  | `tests/golden` | needs the same live LiteLLM/Ollama | `make golden-set`, `make test-all` | Yes — folded into `conformance-model` job's own pytest invocation |
  | `tests/ingest` | needs live ArcadeDB (+ MinIO for `test_staging.py`) | `make conformance`, `make test-all` | Yes — `conformance` job |
  | `tests/scenarios/test_witness_statement_extraction.py` | needs live LiteLLM/Ollama | `make conformance-model`, `make test-all` | Yes — `conformance-model` job |
  | `tests/scenarios/test_hmp_graph.py` | needs live ArcadeDB | `make test-all` | **Yes, added this session** — folded into `conformance` job's own pytest invocation |
  | `tests/services/api/test_sites_store.py` | needs live Postgres (corrected here — recorded as MinIO when this table was first written, checked directly against the file's own `PostgresConfig.from_env()` fixture) | `make test-all` | **Yes, added this session** — folded into `conformance` job's own pytest invocation |
  | `tests/services/api/test_tile_cache.py` | needs live MinIO | `make test-all` only | **No** |
  | `tests/services/api/test_prefetch.py` | needs live MinIO | `make test-all` only | **No** |
  | `tests/geocoder/test_match_live.py` | hits a live external geocoder | `make test-all` only | **No** |

  So the honest state, as first written here, was worse than "five of the ten never run in CI" —
  checked precisely while acting on this same entry: this job's own `--ignore` list on the `test`
  job was a **strict subset** of `Makefile`'s `test` target's ten, meaning `test_sites_store.py`
  and `test_hmp_graph.py` were not merely unrun, they were **attempted by the `test` job with no
  live store to connect to**, reproduced locally against an unreachable Postgres
  (`ConnectionRefusedError`, no `skip` mechanism in either file) — the `test` job's own comment
  ("every other test runs here") was not true, not merely under-disclosed. Closed for these two
  this session: both added to the `conformance` job's pytest invocation (it already has the one
  live service each needs — Postgres for the former, ArcadeDB for the latter) and excluded from
  the `test` job to match, so neither is attempted twice. `test_sites_store.py` mattered most of
  the five to close: its own module docstring names it as the one direct-Postgres proof of
  `SiteStore`'s access control, distinct from `test_sites_routes.py`'s own fake-backed route test
  (checked directly: that fake's `owning_unit` check is hardcoded in the fake itself,
  `_FakeSites.get_authorized`, so it proves the fake's own logic, never the real store's query —
  the exact class `07_BUILD_PLAN.md`'s "Fake-based tests" gaps entry above already warns about),
  and that proof ran nowhere routinely until now. `test_hmp_graph.py` is
  `08_ACCEPTANCE_SCENARIOS.md` Scenario A's own graph fixture.

  Six of the ten now run on every PR and push (`graph_port`, `model_port`, `golden`, `ingest`,
  `test_witness_statement_extraction.py`, and as of this session `test_hmp_graph.py`/
  `test_sites_store.py` count as one addition each but land in the same job) — via CI's own direct
  `pytest` invocations in dedicated jobs, not via `make conformance`/`make conformance-model`
  themselves, which is why those CI job commands and the Makefile targets of the same apparent
  purpose have quietly drifted apart (CI's `conformance-model` job also runs `tests/golden` inline;
  `make conformance-model` does not — a pre-existing drift, not touched this session). The
  remaining three — `test_tile_cache.py`, `test_prefetch.py`, `test_match_live.py` — stay
  deliberately unactioned here: narrower stakes than the two closed above (no access-control proof,
  no acceptance-scenario fixture behind either), reachable only via `make test-all` against a `make
  dev-up` stack by hand, and correctly excluded by the `test` job (`--ignore`s for both already
  present). Owning phase for these three: **Phase 8** — either wire them into a CI job
  (`test_match_live.py` may need an explicit "hits a real external service, nightly only"
  carve-out, the same reasoning `conformance-model-vision` already uses for its own heavier model)
  or record explicitly, next to wherever `make test`'s count is reported, which suites it excludes.

- **The `test_sites_store.py`/`test_hmp_graph.py` fix above was checked against the wider claim it
  sat inside — "the `test` job runs against nothing" — and the claim failed at a scale the first
  fix did not disclose. Asked directly: was CI red and unread, or did these tests skip silently on
  a failed connection and count as passes? Answered with evidence, not inferred.**

  **No skip mechanism exists anywhere in this codebase.** `grep -rln "pytest.skip\|skipif\|pytest.
  mark.skip" tests/ packages/ services/` returns nothing — zero matches, every test file, every
  directory. `tests/conformance/graph_port/conftest.py`'s own `try`/`finally` (the sweep fixture)
  and `tests/conftest.py`'s loopback JWKS server are the only `try` blocks near a fixture in the
  whole suite, and neither swallows a connection failure into a pass. Checked directly against
  `ci.yml` too: no `continue-on-error` anywhere. So the specific mechanism asked about — a test
  quietly skipping when its service is absent, counted as green — **cannot happen in this
  codebase, for any test, not only these two.** Confirmed live, twice: `test_sites_store.py`
  against an unreachable Postgres and `test_hmp_graph.py` against an unreachable ArcadeDB each
  raised their real connection exception (`ConnectionRefusedError`, `httpx.ConnectError`) and
  `FAILED`/`ERROR`, not a skip.

  **What could not be checked: the actual GitHub Actions run history.** `git ls-remote origin`
  shows `origin/main` at `5c2b51a` (`docs: ADR-033`) — every commit from `49e7864` (ADR-034)
  onward, including this whole session's own work, is local-only and has never been pushed.
  `curl https://api.github.com/repos/ayankarsolirius/ospreyflow` returns `404` with no `gh` CLI or
  token configured in this environment — consistent with a private repository this session cannot
  authenticate against, not proof either way of what any past run showed. **No CI run log is
  quoted here because none was reachable; the finding below rests on reproducing the job's own
  command locally, not on run history.**

  **The reproduction.** `test_sites_store.py`/`test_hmp_graph.py`'s own fix (`conformance` job
  gains both, `test` job excludes both) was verified by literally re-running the `test` job's own
  `pytest` invocation — every `--ignore` flag it had at the time, copied exactly — with
  `ARCADEDB_HOST`, `POSTGRES_HOST`, `VALKEY_HOST` and `MINIO_ENDPOINT` all pointed at unreachable
  addresses, the same "no live store" environment a bare `ubuntu-latest` runner with none of the
  `conformance` job's `services:` actually has. Result: **19 failed, 41 errored — 60 test
  functions across 17 files this job's own ignore list did not name**, none of them
  `test_sites_store.py`/`test_hmp_graph.py` (those were already fixed by that point). Three were
  already known and disclosed above (`test_tile_cache.py`, `test_prefetch.py`,
  `test_match_live.py`, 7 of the 60). **Fourteen were not previously found:**
  `tests/resolve/test_trigger.py`, `tests/resolve/test_projection_access_control.py`,
  `tests/scenarios/test_phase6_extraction_and_resolution.py`,
  `tests/scenarios/test_phase6a_glass_surfaces.py`, `tests/services/api/test_access.py`,
  `tests/services/api/test_dossier_access_control.py`, `tests/services/api/test_pattern_store.py`
  (this session's own new store — added without checking whether the `test` job could run it),
  `tests/services/api/test_review.py`, `tests/services/api/test_review_store.py`,
  `tests/services/api/test_studio_recipes_store.py`, and all three of
  `tests/services/api/working_set/test_compute_access_control.py`/
  `test_explain_cluster_access_control.py`/`test_manual_resolution_access_control.py`/
  `test_resolution_threshold_access_control.py` (four, not three — checked the directory listing
  directly rather than assumed). Every `graph_arcadedb[gremlin]`-parametrised access-control test
  in the repository is in this list: `GRAPH_PORT_ADAPTERS` (`tests/conformance/registry.py`) has
  exactly one entry, so there is no non-live-service variant for any of them to fall back to.

  **The answer to the question actually asked.** Since no skip mechanism exists, "did these skip
  silently and count as passes" is answered **no, categorically, for every test in this
  codebase** — the mechanism itself does not exist to have happened. If any commit touching these
  17 files was ever pushed to GitHub and `ci.yml`'s `test` job actually ran, the only outcome
  consistent with the evidence above is that **the job was red, and that red was not acted on** —
  not a false green. This session cannot confirm a run happened at all (see the access
  limitation above); what it can and does confirm is that a run, had it happened against this
  configuration, could not have been green.

  **Fixed in this session, for the `test` job specifically:** all 17 files added to its `--ignore`
  list (`ci.yml`'s own comment on the job now carries the full count and reasoning); the exact
  updated command re-run against the same unreachable-service environment above now completes
  **580 passed, 0 failed, 0 errored** — the "runs against nothing" claim is true of this job now,
  checked, not merely restored to how it read before.

  **CLOSED, a later session the same phase: 16 of the 17 wired into `conformance`, not deferred to
  Phase 8 after all.** The "genuine engineering work" framing directly above overstated the cost —
  checked, not assumed, before closing it: every one of the 17 needs only ArcadeDB, Valkey,
  Postgres or MinIO, all four of which `conformance` already stands up, so wiring them in needed no
  new job and no new service, only the run-list lines themselves. All 15 not already handled
  elsewhere (`test_pattern_store.py` was closed separately, above) were run as a set for the first
  time as part of this closure and all 15 passed — confirmed safe to add, not assumed. Seven of
  them prove an access-control invariant and had been unverified in any CI job until now:
  `test_access.py`, `test_dossier_access_control.py`, `test_projection_access_control.py`, and all
  four `working_set/test_*_access_control.py` files — exactly the `working_set` access-control four
  the paragraph above named as needing "careful placement," which turned out to mean fifteen lines
  in an existing job's run list, not new infrastructure.

  **`test_phase6_extraction_and_resolution.py` — CLOSED THE SAME SESSION, extending
  `conformance-model` rather than a new job.** The one file needing ArcadeDB *and* Ollama/LiteLLM
  *and* Valkey together, a combination neither `conformance` nor `conformance-model` individually
  provided. `conformance-model` already pays the Ollama/LiteLLM/speaches setup cost every run, so
  ArcadeDB (`-Xmx4G`, matching `conformance`'s own sizing exactly, not raised) and Valkey were added
  to that job instead of standing up a third — a marginal addition, not two setups paid from
  scratch. **Watched for the memory contention this combination is known to cause, not assumed
  safe:** `deploy/compose/dev.yaml`'s own ArcadeDB/Ollama note already documents six local OOM-kills
  from this exact pairing across this build. Simulated locally before committing to it — a fresh
  ArcadeDB at the configured heap, alongside the already-running Ollama/LiteLLM/speaches
  containers, run four separate times (the target test alone, twice more back to back, then the
  full 11-test command the job actually runs) — all four passed, no `OOMKilled`, ArcadeDB settling
  around 4.0-4.2GB rather than growing unbounded across repeats, comfortable headroom left under a
  ~7.6GB budget comparable to a standard hosted runner. Held on that evidence rather than reverted.
  `ci.yml`'s own comment on `conformance-model` carries the full simulation detail and the revert
  instructions if the actual runner disagrees with the local read.

  **Still not fixed, still Phase 8's own scope:** `Makefile`'s own `test`/`test-all` targets are now
  further out of sync with `ci.yml` than when this entry was first written — `test-all` still lists
  only the original ten files' worth of live-service coverage (`tests/conformance/graph_port`,
  `tests/conformance/model_port`, `tests/golden`, `test_witness_statement_extraction.py`,
  `tests/ingest`, `test_phase3_working_set.py`, `test_hmp_graph.py`, `test_valkey_store.py`,
  `test_statelessness.py`, `test_sites_store.py`, `test_tile_cache.py`, `test_prefetch.py`,
  `test_match_live.py`), never updated for `test_change_stream.py`/`test_alerts.py`/
  `test_pattern_store.py`/`test_hotlists.py`/`test_monitors.py`/`test_evaluation.py` (Phase 7 Stage
  6a/6b) or any of the 15 just wired into `ci.yml`'s own `conformance` job here — meaning `make
  test` (no ignore for any of those) would today attempt roughly twenty files against no live
  service and fail, and `make test-all` would not actually run several of them even against a real
  `make dev-up` stack. Not touched in this pass — out of scope for a `ci.yml`-only wiring session,
  and `make test`/`make test-all` are a local developer convenience, not what any CI job runs.
  Owning phase: **Phase 8**, same as before — bring `Makefile`'s own two targets back in sync with
  `ci.yml`'s current run/ignore lists in one pass, and decide whether `make test` should either
  guarantee no live-service dependency (matching its own name) or have that dependency stated
  plainly next to every place its count is quoted.

- **`make typecheck` was permanently red — 19 pre-existing `mypy` errors in five files, plus three
  more `tsc` errors this session found undisclosed alongside them. Fixed rather than split, same
  session.** A red gate that has been red long enough to be treated as background noise cannot
  catch a real regression landing next to it, so once found this was closed outright rather than
  carved out with an owning phase, unlike the two entries above: every one of the 22 was either a
  `cast` narrowing what runtime code already guarantees (DuckDB's untyped row tuples in
  `analytics_duckdb/adapter.py` and `prefetch.py`'s single-literal-row subquery, asyncpg's
  `Record.__getitem__` in `review.py`, ArcadeDB's JSON-decoded `Any` in `graph_arcadedb/
  client.py`, and `tile_proxy.py`'s already-`raise`d "missing" check) or a genuine, small logic
  fix — `map/geometries.ts`'s `resolveNodeCoordinates` was written when `GeometryRecord` was
  point-only and never updated for the `POLYGON` kind (Phase 5's known-gaps closure, above in this
  same list) making `lat`/`lon` optional; a `POLYGON` record's node now correctly drops out of the
  plottable-coordinates result (the function's own docstring already promised this: "only nodes
  with a *resolvable* geometry_ref appear") rather than being a type error nobody had reconciled.
  `ConnectScreen.test.ts`'s own fix is a non-null assertion on a locally-built fixture array, no
  behaviour change. None of the 22 were in a Part 3 file. `make typecheck` (`mypy packages
  services` and `npm run typecheck` both) exits 0 as of this entry — verified, not assumed.

- **`GlassCanvas.tsx`'s three remaining silent-drop call sites — `expandNode`, `manualAssertion`,
  `explainCluster` — closed, same session `findPaths` was, and for the same reason: raised once,
  each still read `if (!response.ok) return;` behind a comment claiming "surfaces via a Toast at
  the App layer," checked directly and found false (the App-layer Toast is driven only by
  server-pushed `notice` deltas over the websocket, never by a client-side `fetch` failure).
  `manualAssertion` was fixed and proven first, ahead of the other two: a failed *write* left the
  analyst believing a link (or split) was recorded in the case when it was not, worse than a
  failed *read* misleading them about what the data shows. All three now surface a shared
  `ActionErrorOverlay` (`role="alert"`, Escape-dismissed via the same `Popover` every other canvas
  overlay uses) rather than silence — one new keyboard action, `overlay-dismiss-action-error`,
  proven via manual-link (the priority), expand and explain-cluster each, red then green.
  **A residual, smaller gap found while fixing `expandNode`, not yet closed:** the typed
  `limit_exceeded` (409) response Phase 3's own exit criterion requires (`"returns the typed
  limit_exceeded error with its three options"`, above) is now surfaced as a generic error message
  rather than the three options themselves — checked directly, no frontend code anywhere renders
  them (`grep -rln "limit_exceeded" apps/workspace/src` matches only this fix's own comment).
  Phase 3's exit criterion is about the *backend* returning the typed error, which it does; this
  is a distinct, frontend-only gap Phase 3's own text does not cover. Owning phase: **Phase 8** —
  render `limit_exceeded`'s three options in `ActionErrorOverlay` (or a dedicated variant) rather
  than the generic message currently shown.

- **`make lint`/`ruff check .` is also pre-existing-red, found incidentally this session while
  verifying the fixes above, not investigated for its own sake.** 32 errors across 16 files, none
  touched by this session's own work (`packages/schemas/ingest.py`, `scripts/mint_dev_token.py`,
  `services/api/dossier.py`, `services/api/studio_profile.py`, and a further twelve test files —
  mostly `I001` unsorted-import-block and `F401` unused-import, 18 of the 32 mechanically
  `--fix`-able). Not fixed here — genuinely out of this session's scope, unlike `make typecheck`
  (fixed earlier this session because a prior entry in this same document asked directly whether
  it should be fixed or split). Owning phase: **Phase 8** — same closing-pass home as the
  gate-hygiene entries above it.

- **FIXED, Stage 6b's own carry-over 2 from 6a, closed rather than left re-scoped.** The finding
  stood as written through this stage's first report — a live defect in `Person` resolution,
  reachable by an entirely ordinary hyphenated British surname, not an incidental test-fixture
  finding. `packages/ontology/default.yaml` declares exactly one `resolution:` block in the whole
  ontology, on `Person`: `blocking: [soundex(family_name), year(date_of_birth)]` — the only call
  site. `resolve_entity_type` (`services/resolve/resolver.py:60` calling `duckdb_setup.
  new_connection()`, which registers the UDF Splink's compiled blocking SQL then calls once per
  row) failed for the **entire population being resolved**, not merely the one affected row —
  Splink compiles blocking into one SQL statement over the whole population, and DuckDB's own UDF
  exception aborted that statement outright — called from both the manual "resolve now" route and
  the automatic post-ingest hook (`06_DECISIONS.md` ADR-025, Phase 7 Stage 1, already live).

  **Checked broader than a hyphen before fixing it, not fixed narrowly first and widened later:**
  `phonetics.soundex()` indexes its digit table with `ord(c) - ord('a')` for every character after
  the first, with no bounds check, so *any* character outside `a`-`z` raises the identical
  `IndexError` — confirmed directly for an apostrophe (`o'brien`), an internal space
  (`van der berg`), digits (`smith2`) and an accented letter (`müller`), not only a hyphen. A fix
  scoped to hyphens alone would have left `O'Brien`/`O'Neill` — at least as ordinary a UK surname
  shape — still crashing.

  **Fix:** `services/resolve/duckdb_setup.py`'s `_soundex` now sanitises before calling
  `phonetics.soundex` — Unicode-normalises and folds accents to their base letter (`müller` blocks
  as `muller`, not as the accent-stripped `mller`), then strips anything still outside `a`-`z`, and
  returns `None` (the same "no blocking key" result an empty/`None` input already produced) if
  nothing letter-shaped survives, rather than a new failure mode. No other blocking or comparison
  function in the registry (`packages/ontology/resolution_functions.py`'s `BLOCKING_FUNCTIONS`/
  `COMPARISON_FUNCTIONS`) shares this fragility, checked directly rather than assumed: `exact` and
  `year` compile to plain DuckDB SQL with no custom function at all, and `jaro_winkler`/
  `levenshtein` resolve to Splink's own `comparison_library` constructors
  (`services/resolve/splink_config.py`) — `soundex` was the only registered function backed by
  bespoke Python indexing code.

  Proven: `tests/resolve/test_duckdb_setup.py` (seven cases directly against `_soundex` — hyphen,
  apostrophe, space, digits, accent-folding, punctuation-only input, and that a hyphenated and its
  unhyphenated spelling still share a blocking key) and
  `tests/resolve/test_resolver.py::test_a_hyphenated_family_name_does_not_crash_the_entire_
  resolution_pass`, the reachable-path proof: confirmed to fail with the pre-fix code (a
  `SplinkException` wrapping the same `IndexError`) and to pass with the fix, including a third,
  unrelated `Person` in the same pass to prove the *population-wide* failure mode is gone, not only
  the one hyphenated row.

- **NEW, found while closing the entry above, not fixed by it: an entirely non-Latin-script family
  name still crashes the whole `Person` resolution pass, same blast radius as the hyphen defect,
  different mechanism.** Full reasoning and reproduction: `01_DOMAIN_MODEL.md` §4's own "Splink
  configuration" section, in the note right after the accent-folding record. One line here: the fix
  above sanitises down to `None` when nothing letter-shaped survives sanitisation (a fully Chinese,
  Cyrillic, Arabic, etc. family name), and DuckDB's own UDF registration — `null_handling='DEFAULT'`
  by construction, no argument overriding it — forbids a UDF from ever returning `NULL` for a
  non-`NULL` input, so `resolve_entity_type` raises `SplinkException` the moment one such `Person`
  exists anywhere in the population, not only "every non-Latin name silently blocks with every
  other one" as first suspected. Owning phase: **Phase 8**, alongside the resolver-internals work
  the fix above was already filed under. Named test, not written un-owned:
  `test_a_non_latin_family_name_does_not_crash_the_entire_resolution_pass`.

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
9. **A phase closes when its exit criterion passes, not when its outcome bullet list is fully
   delivered.** An outcome bullet the exit criterion never exercised is real, promised work, not
   satisfied work — record it in the phase's own known-gaps list, or reattribute it to whichever
   later phase's bullet list actually claims it, as soon as it is found to be short. A bullet may
   legitimately go unbuilt at close; it may never go unrecorded. Practice already followed this
   three times (Phase 5's A1–A11 scoping, Phase 6's entities-only exit, Phase 6a's own disclosed
   review) before it was ever written down here — and once failed it silently: Phase 5's own
   closing commit (`dcd985c`) never carried `playback`/`multi-track`/`cross-case overlay` into its
   known-gaps list, and they sat claimed-but-undelivered in the outcome bullet for four phases
   until an unrelated audit found the deferral in `Timeline.tsx`'s own source comment. This rule
   does not mechanically prevent that recurring — closing against the exit criterion rather than
   the bullet list was already the practice when it happened — it only makes silence itself the
   one thing a future audit can call a rule violation rather than a judgement call.
