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
  does not have to be rediscovered from scratch.

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
3. **`explain` rendering (B10).** Per-*cluster*, not per-node — triggered from a clustered
   selection, rendered as a `Table` (already built) of per-comparison match weights. Demonstrated
   against the same seed as Stage 2.
4. **B6 — the Dossier.** Largest and last: a wholly new Glass surface (`apps/workspace/src/
   dossier/` is empty; `00_ARCHITECTURE.md` names the Dossier as its own component alongside
   Canvas/Timeline/Map/Query, not an Inspector tab) — the same shape of work Phase 5a's own Map
   screen was over Phase 2.

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
   Tier-3 questions answered here, before any adapter, per standing rule 1; independent of Stage 1
   and may run in parallel with it.
3. **`adapters/compute_rustworkx` and the metrics panel.**
4. **The visual query builder** — `01_DOMAIN_MODEL.md` §8.1's own pattern-binding-rule question
   (flagged since Phase 3, still unresolved) settled here, before an analyst is put in front of a
   canvas drawing arbitrary patterns.
5. **The pathfinder.**
6. **Hotlists, saved-pattern monitors, alert inbox** — genuinely demonstrable only once Stage 1
   exists.

**Exit.** Acceptance scenario B, scoped to B1–B5, B7, B12–B14, B15, B19 and B20 (ADR-022), passes
end to end. The Clique Metric ranks the insular-cluster fixture node above the broad-hub fixture
node, and all three compute tiers return identical values within tolerance. A12 (Phase 5's exit
criterion, scoped to A1–A11, deferred this one step here per ADR-019) is re-proven against the
same HMP fixture: the Clique Metric identifies the same insular subgroup Phase 5 already surfaced
by other means. B15 (a SIM `Endpoint` reaching its `Device` in one traversal) is re-verified here
specifically because this phase's own pathfinder and visual query builder compute over that same
traversal shape — see ADR-023, which must land before this phase's Session 5 (schemas and the
`ComputePort` conformance suite) so neither is built against a graph topology about to change.

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
- The two Scenario B Glass features no earlier phase built (ADR-022): cross-case timeline overlay
  and playback-driven snail trail (B16, B18) — small, incremental additions to Timeline and Map,
  the components Phase 5 already shipped, not a new surface the way Phase 6a is over Phase 6.

**Exit.** Both acceptance scenarios pass unchanged on `local-lite` and on `cluster`. A
`backup` → `restore` cycle across profiles reproduces the graph from staged Parquet. An export
containing an `S2`-marked item is blocked, names the item, and proceeds only with a recorded
justification.

---

## Gaps with no owning phase

Unlike the known-gaps lists inside Phase 5, Phase 5a and Phase 6 above — each a thing that stage's
or phase's own work found and deferred — an entry here is something no phase's bullet list claims
at all. A phase about to close checks this list the same way Phase 6's own stages checked the
previous phase's known gaps before scoping their work, so an orphaned intention doesn't sit
findable only from whichever phase happened to notice it.

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
  an assumption that Phase 2 closing or Phase 6a's Glass work already covers it.

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

- **`keyboard.spec.ts`'s walkthrough has no auto-discovery of new canvas actions, and `CLAUDE.md`
  rule 13's standing rule is a stopgap for that, not a fix.** Confirmed directly while closing
  Phase 6a Stage 1's own keyboard gap: the spec is a hardcoded sequence of steps, so a new action
  with no step added is invisible to it — Phase 4's own exit criterion ("keyboard navigation
  reaches every canvas action") is enforced by a test structurally unable to detect its own
  violation. Rule 13 makes adding that step the new action's own author's responsibility, in the
  same change, rather than a follow-up — cheap, and adopted for Stage 2 onward, but it depends on
  being remembered, which is the exact failure mode it exists to close.

  **The stronger fix, named here rather than built:** an explicit, machine-checked inventory —
  `GlassCanvas` (and whatever surface Stage 4's Dossier or Phase 7's metrics panel, visual query
  builder and pathfinder add) exports a registry of its own canvas actions, and a test asserts one
  `keyboard.spec.ts` case exists per registered action, so a new action with no step fails the
  build rather than passing it silently. This is real, unscoped engineering — what counts as "an
  action," how a metrics-panel or query-builder action registers itself the same way a canvas node
  action does — not a one-line change, which is why it is recorded here rather than folded into
  rule 13 itself. Whichever phase first adds a second keyboard-driven surface (Stage 4, on current
  sequencing) is the natural owner, and should either build the inventory then or say explicitly
  why the rule alone still suffices.

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
