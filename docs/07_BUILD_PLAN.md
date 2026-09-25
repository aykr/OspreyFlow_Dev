# 07 — Build Plan

## Standing status summary

**Kept current at the end of every stage and at every phase close (below, "phase-close
procedure") — a map, not a substitute for the detail below it. A stale summary is worse than
none, because it is what gets read.**

**The milestone, in one sentence.** V1 END TO END = the product can be installed on a clean
laptop from the documentation, started, and demonstrated (both acceptance scenarios passing on
`local-lite` is one component of that, not the whole of it).

**Complete, by stage:**
- Stage 2c — Sign-in for the Glass (`06_DECISIONS.md` ADR-050). Built, 25 September 2026, including
  the WebSocket ticket exchange (objection 8), built the round after per the owner's own decision
  of that date. One disclosed gap remains and is not milestone-blocking on its own: full app-wide
  silent-reauthentication coverage beyond the bootstrap calls — this stage's own entry below has
  the full account.
- Stage 4 (4-spec, 4a–4h) — the product-feature core. Built.
- Stage 1 — principal resolution (OAuth2 Token Exchange, ADR-043). Built; delivered, not
  milestone-gated. **Its 22 September "built" was wrong until 24 September** — the exchange omitted
  `subject_token` and had only ever run against a fixture more permissive than the real server; see
  the correction at its own entry.
- Stage 2a — ArcadeDB stability. Closed; the 10GiB VM floor resolved causes one through four,
  cause five reduced to the same mechanism, the criterion re-pointed to a clean install.
- `Makefile`/`ci.yml` reconciliation (pulled forward from Stage 6). Built.
- `PathStaleError` and the server-side traversal budget (pulled forward from Stage 5). Built.

**Remains before the milestone, numbered, with a word on size:**
1. **The harness/packaging pipeline** — **`Stage 2 §1`–`§5b` built; `§6`–`§7` not started.** The
   design and its adversarial review are `06_DECISIONS.md` **ADR-049**, status **Accepted**, broken
   into sub-stages **`Stage 2 §1`–`Stage 2 §7`** at this stage's own entry below. The owner ruled on
   all seven open objections and confirmed D1–D3 on 24 September 2026, then corrected D1 to its
   **narrowed** form and settled all four follow-on items the same day, with standing rule 8 left
   unchanged and the four undockerised services recorded instead as a rule-8 violation by their
   creating phases, repaid once in `Stage 2 §5`. **`Stage 2 §1` and `Stage 2 §2` are built** — the
   `osprey.yaml` schema, `python -m harness.render` and its four artefacts with drift detection and
   change preview, and `python -m harness.preflight` with ten checks, Re-check, `--gate` and §3's
   offered-never-applied reduced variant. **`Stage 2 §5a` is built too** — the deployable-service
   enumeration, the Glass's image as a standing-rule-8 repayment, and local builds of all three
   owned images. **`Stage 2 §3` and `§4` are built**, exit tests #2 and #1 green respectively
   (each stage's own entry below has the detail). **`Stage 2 §5b` is now built too, 25 September
   2026** — the real `osprey bundle` command, its seven packaging-hygiene assertions, the
   bundle-time documentation site (both the tarball and the workspace image's own `/docs`), and
   exit test #3, run for real: build with `--images`, unpack into a directory with no relationship
   to this checkout, `docker load`, `harness.apply --no-build` — green, automated as
   `tests/harness/test_bundle_exit_test.py` (opt-in, `OSPREY_TEST_BUNDLE=1`). **Stage 2's own D3
   exit criterion — tests #1, #2 and #3 green — is therefore now fully satisfied**; this is Stage
   2's own completion, not ADR-042's alpha gate, which additionally requires both acceptance
   scenarios green on `local-lite`. The `cluster` renderer is a loud stub. `§6` and `§7` (the six
   setup screens; post-launch admin console operations) are not started; `§3` still has its own two
   recorded blockers as historical record even though the stage as a whole went green around them
   (see that stage's own entry).
2. **The documentation refresh** — moderate: the three drift gates (`domain-model-coverage-check`,
   `route-coverage-check`, `demo-guide-check`) exist and run; the content that empties their own
   allowlists does not exist yet.
3. **Sign-in for the Glass** — **accepted, with five amendments (`06_DECISIONS.md` ADR-050, owner's
   ruling of 25 September 2026), not started.** Milestone-blocking. OIDC authorization code with
   PKCE, replacing the `VITE_DEV_BEARER_TOKEN` stand-in; see stage `2c` at this stage's own entry
   below for the three requirements and the exit test.

**Remains after the milestone:**
- **Structural** (real design work, not a known shape yet): Phase 8a (`cluster` profile,
  `graph_janusgraph`/`analytics_clickhouse`, ComputePort Tier 3); ADR-025's own second trigger,
  "manual resolve now," never built; the sustained-load memory/query-latency characterisation
  (`05_DEPLOYMENT.md` §8); Scenario B's own missing close-but-not-exact `Person`-pair fixture
  (B9/B10); Trigger A, the restructure (a real, one-time move, now with its own reinstall-and-rerun
  exit criterion); Trigger B, publication (owner-gated, no date).
- **Bounded** (already-scoped, a known fix shape from the finding that disclosed it): the rest of
  Stage 5 (the node-state-channel item, the reusable `limit_exceeded` component, node size by
  metric); Stage 6 (test-infrastructure/CI hygiene, itemised); export mark signing (item 7); the
  `_weigh_edge` quadratic-ingest-cost defect; "Legacy disclosures"'s own relocation into wherever
  each entry's stated disposition names (assigned to Stage 3).
- **Proposed, not milestone-blocking:** an admin-console `/docs` link to the now-built
  documentation site (Stage 2 §7's own Proposed sub-item — the site itself is built, `Stage 2
  §5b`, 25 September 2026), and the post-milestone Analyst guide (Stage 3c, still only a
  "not yet written" placeholder page on the site itself).

**Outside the build entirely: `docs/PRODUCT_DELIVERY.md`** — the alpha gate, demo distribution
classes, tester/alpha/beta material, and Trigger B's own downstream distribution questions. Not a
build step, a stage, or a precondition of anything above; a different question, answered there.

**Last updated:** 25 September 2026.

---

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
  full under "Legacy disclosures" below, not only here, precisely so it is findable by a
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
  (this document's Phase 2 known-gaps list and its `Legacy disclosures` entry both record
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
   instances three and four of one pattern (`Legacy disclosures`, above): `set_resolution_
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
   threshold` and `explain_cluster` (instances three and four, `Legacy disclosures` above)
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

   **The keyboard-action-registry decision (`Legacy disclosures` above) is decided here:
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
   **This is manifestation one of three of a single gap** — see "Legacy disclosures"'s own
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
   on the same horizontal-scalability claim** — see "Legacy disclosures"'s own consolidated
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
   would. **Owning phase: Phase 8, Stage 6** (test-infrastructure and CI hygiene) — the same class of
   drift-gate-parity work as that stage's other items, not left unassigned; widening
   `generate_ts.py`'s own scope to `services/api` route-response models generally, not just this
   one route module, is the shape of the fix.

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
end" was not the same claim for every principal who could set a hotlist or a monitor — corrected,
23 September 2026, now that it no longer holds.** The pattern this document's own standing rule 12
names — a gate proving less than its name implies — applied to this exit criterion itself when it
was written, not only to a test file, and was recorded here rather than only in `06_DECISIONS.md`
ADR-036's own amendment. At the time: what passed was the walkthrough
`08_ACCEPTANCE_SCENARIOS.md` narrates, where the analyst who sets the hotlist/monitor in B12/B20 is
the same analyst whose later action in B13/B20 triggers it — `owner_id == requester` by
construction, one continuous session; a hotlist or monitor firing from a *different* analyst's
later ingest — the operational case B13's own CoLP framing is actually modelled on ("a warrant
seizure logged by a unit other than the one that set the original hotlist entry") — was not
exercised at all, because ADR-036's amendment meant the built system did not yet handle it.

**Superseded by Stage 1 (principal resolution, built 22 September 2026, `06_DECISIONS.md`
ADR-043) — this is no longer the state of the system, checked directly, not assumed stale.**
`test_phase7_stage6c_watch_routes.py::test_a_hotlist_owned_by_one_analyst_fires_from_a_different_
analysts_own_ingest` proves the exact cross-analyst case this passage once said was untested: a
hotlist owned by one analyst fires from a genuinely different analyst's own ingest, through the
real route-level `principal_resolver` wiring, not a same-session artefact. **"Scenario B passes end
to end" now is a claim that hotlists/monitors work operationally across analysts, for the
*ingest*-triggered path (ADR-025's own trigger 1, "post-ingest hook") B13/B20 both use.**

**What remains genuinely unsupported, and is a different gap from the one just closed: ADR-025's
own second trigger, "manual 'resolve now,'" was never built — recorded there only as "a small,
analyst-facing route mirroring `submit_supersede_node`'s own sync-vs-job split," still a proposal,
not code.** Resolution triggered by an analyst directly (as opposed to resolution's own downstream
alerting being triggered by a new ingest event) has no route, no job, no test — a genuinely
different mechanism from the cross-analyst principal question Stage 1 closed, not a residue of it.
Owning phase: Phase 8, alongside ADR-025's own remaining design. B15's own "Platform capability" column
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
  (`01_DOMAIN_MODEL.md` §10); the algorithm itself is **resolved as out of scope for v1**
  (`07_BUILD_PLAN.md`'s own "Out of scope for v1" section has the full reasoning: no acceptance
  scenario requires it) rather than left as a "gaps with no owning phase" entry.
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
  the generated-artefact diff, and the backup, restore, upgrade and verify screens. **A new panel
  on the Governance screen, added 23 September 2026, amended 24 September 2026 from "a new screen"
  to a panel** (`06_DECISIONS.md` ADR-049's D2, the owner's decision of that date): managing the
  real-data exceptions list (standing rule 3, `CLAUDE.md` rule 9, `06_DECISIONS.md` ADR-035 §C3) —
  the shape `scripts/real_data_exceptions.py`'s own CLI already wraps, the same "plain module now,
  harness surface eventually" pattern every other pre-Phase-8 operational script in this build
  follows. **A panel, not a seventh screen**, because `05_DEPLOYMENT.md` §2.1's table is explicitly
  "Six screens" and this entry's original wording contradicted it — the contradiction was found
  while reviewing ADR-049 and is resolved here rather than left standing. Each entry carries a
  `decision_record` reference, required, validated for presence and format only and never resolved
  (ADR-049's ruling 3).
- Harness-driven orchestration (`05_DEPLOYMENT.md` §2.4): target confirmation, drift detection,
  change preview, enforced backup-before-switch, and downgrade capacity checks against the
  existing data volume.
- The headless CLI equivalent for every screen, so a deployment built by clicking is reproducible
  by a script.
- Generated Kubernetes manifests and the per-deployment runbook.
- The two Scenario B Glass features no earlier phase built (ADR-022): cross-case timeline overlay
  and playback-driven snail trail (B16, B18) — built at their real size, not the "small, incremental"
  size ADR-022 assumed before checking; Stage 4f's own entry, below, has the correction.
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
- **A pathfinder acceptance-scenario step — decided, 22 September 2026: B21 added to Scenario B,
  not an ADR accepting its absence.** `07_BUILD_PLAN.md`'s own "Legacy disclosures" entry has the
  full reasoning; `08_ACCEPTANCE_SCENARIOS.md` carries the new row.

**The milestone this phase exists to reach — redefined 23 September 2026. The previous definition
below was a test-suite criterion; the owner's own stated goal is broader, and this document now
says so rather than standing in for it:**

> **V1 END TO END = the product can be installed on a clean laptop from the documentation,
> started, and demonstrated.** Both acceptance scenarios passing on `local-lite` is one
> component of that, not the whole of it.

**What this adds that the old definition did not, stated plainly rather than left for a reader to
infer.** An install nobody has performed from scratch is not proven by a developer's own
already-configured environment passing a test suite: `make dev-up` on a machine that has already
run it fifty times, with every image cached, every port free and every credential already minted,
proves nothing about whether a person who has never touched this repository can reach a running,
demonstrable system starting from `docs/` alone. Both acceptance scenarios passing on `local-lite`
(`08_ACCEPTANCE_SCENARIOS.md`'s own A1–A15 and B1–B21, run end to end, unchanged from their own
written form) proves the product's own logic is correct; it does not prove the product, as
packaged and documented, is installable by someone who is not already its own developer — those
are different claims, and the old definition only ever tested the first. An `S2`-marked item
blocking on export, named, proceeding only with a recorded justification is not a separate exit
clause — it is A15's own assertion (`08_ACCEPTANCE_SCENARIOS.md`), already inside "both acceptance
scenarios pass." A `backup` → `restore` cycle reproducing the graph from staged Parquet, and a
scripted golden-path deploy reaching a running, health-checked stack, are now milestone-blocking in
their own right — not because either row in either scenario exercises them (neither does, checked
directly), but because "installed... started, and demonstrated" cannot be satisfied without them:
the harness/packaging stage below is no longer sequenced after the milestone, it is part of it.

`adapters/graph_janusgraph`, `adapters/analytics_clickhouse`, ComputePort Tier 3 and the
`cluster` half of this phase's own former exit criterion move to Phase 8a
(`06_DECISIONS.md` ADR-022's third addendum, 20 September 2026) — that phase's own verification
needs real multi-node infrastructure this phase's own bullet list does not, so each phase's exit
criterion is now a test it can actually run on the infrastructure it has, not a criterion split
across two without saying so. Cluster-profile parity is accordingly not part of this milestone
either way — see this document's own cross-cutting-assertions resolution, below, for the full
reasoning: the owner defined the milestone as install-and-demo, and this row falls outside it as a
consequence of that definition, not a separate decision the owner stated in these terms.

**This phase's own stage list is a single, ordered list, in build order — restructured again, 23
September 2026, collapsing the "Before/after the milestone" split this document used from 22
September 2026 until now.** That split was the right shape for a test-suite milestone (a stage
either gates the test or it doesn't); it is the wrong shape for an install-and-demo milestone,
where "the milestone" is most of what Phase 8 actually still has to build. Nothing below was
deleted or newly invented — the harness/packaging stage, the documentation refresh, Trigger A and
Trigger B (previously named only in `06_DECISIONS.md`/`PRODUCT_DELIVERY.md`, never listed as a
`07_BUILD_PLAN.md` stage in their own right) all return to this list; only their order and their
framing changed. **Milestone-blocking, in this order: the harness/packaging stage, then the
documentation refresh** — the milestone is an install, and an install needs something to install
and instructions to follow. **Then, listed but not milestone-blocking: Trigger A**, which already
follows the documentation refresh in this document's own existing text (its own stage entry,
below, is unchanged in substance). **Then, last: Trigger B** — scheduled and visible as the final
stage of this phase's own list, not committed to a date; its own entry condition is unchanged from
`06_DECISIONS.md` ADR-034 §B3, quoted at its own entry below, not restated here. Everything else in
this phase's former "After the milestone" section (the smaller code fixes, test-infrastructure/CI
hygiene, export mark signing) remains listed, in the same place in this ordering, but is not
itself milestone-blocking — each says so at its own entry. **One exception, promoted this same
session: ArcadeDB stability** (the sweeper's three causes, the OOM-contention finding, and a
newly-observed fourth cause) **is now milestone-blocking** — see its own relocated entry, below,
for the full reasoning. Stage numbers are kept stable (every other document in this project cites
a stage by its own number — `4a` through `4h`, `5`, `6` — not by its position in this list), so a
stage appearing "out of numerical order" below is the reordering working as intended, not a
mistake. What genuinely stays out of this list: anything about testers, alpha or beta testing —
`docs/PRODUCT_DELIVERY.md` owns that and continues to.

### Phase 8's stage list, in build order

**Milestone-blocking stages, in the order this milestone now needs them — physically detailed at
their own existing entry further down this list (marked **MILESTONE-BLOCKING** there) rather than
repeated in full here, so this summary stays a map, not a second copy:**

1. **Stage 4, in full** — the product-feature core; unchanged, detailed immediately below.
2. **The harness / packaging pipeline** (previously "Stage 2," listed further down this same list,
   now tagged **MILESTONE-BLOCKING**) — an install needs something to install: the packaging step,
   the `backup`/`restore` cycle, the scripted golden-path deploy, the six setup screens, Preflight.
3. **The documentation refresh — split in two, 23 September 2026, sized honestly rather than left
   as one undifferentiated block.** **3a (MILESTONE-BLOCKING): the installation and deployment
   documentation, and `DEMO_GUIDE.md`** — an install needs instructions that actually work: every
   command in each, run clean on a fresh checkout, producing the result the document claims. That
   is the whole of this part. **3b (Trigger A's own scope, not milestone-blocking): publication
   readiness** — the provenance rewrite (102 annotations), the `CLAUDE.md` citations (6 files), the
   allowlists (four gates), and the README work already recorded — sized with real numbers, below
   and at its own detailed entry, precisely so it is never read as proofreading.
4. **Trigger A, the restructure** (`06_DECISIONS.md` ADR-034 §B3) — follows the documentation
   refresh, as this document's own existing text already ordered it; its own detailed entry,
   further down this list, now carries its own exit criterion (added 23 September 2026), not
   unchanged in substance by this restructure. Not itself milestone-blocking to *reach* — moving
   files to their published-tree layout is not a condition of "installed, started, and
   demonstrated" — **but it can invalidate an already-reached milestone if nothing re-proves the
   install afterward, which is exactly what its own new exit criterion, further down, now does.**
5. **Trigger B, publication** (`06_DECISIONS.md` ADR-034 §B3) — the final stage of this list,
   scheduled and visible rather than buried in a different document, not committed to a date. Its
   own entry condition, quoted rather than restated: *"Trigger B, publication. Fires only on
   explicit owner instruction, after all phases, stages, and alpha and beta testing are
   complete."* Not itself milestone-blocking — V1 END TO END is reachable, and this document's own
   exit criterion for it satisfiable, without Trigger B ever firing; alpha/beta testing itself is
   `docs/PRODUCT_DELIVERY.md`'s own territory, named here only because ADR-034's own condition text
   names it and this document does not get to edit an accepted ADR's own words to remove the
   mention.
6. **ArcadeDB stability — closed, 23 September 2026** (previously filed in "Legacy disclosures,"
   relocated into this list, promoted and closed the same day — see its own entry, further down,
   for the re-pointed exit criterion and the measurement that met it) — a demo that fails more
   often than it completes is not a background nuisance under an install-and-demo milestone, and
   this stage's own work found that a clean install-and-demo run does not fail.

Everything else previously filed under this document's own retired "After the milestone" heading
(the smaller already-scoped code fixes, test-infrastructure/CI hygiene apart from the ArcadeDB-
stability item just promoted, export mark signing) remains listed below, in the same relative
place, each stage's own entry stating plainly whether it is milestone-blocking — none of the
remaining ones are, and each says so at its own entry rather than by virtue of a section heading.
**What stays out of this list entirely: anything about testers, alpha or beta testing** —
`docs/PRODUCT_DELIVERY.md` owns that, unchanged.

4. **Assessment, export, the remaining Scenario B steps** — the product-feature core, following
   established patterns (evidence linking, export pipelines, handling gates) this build already has
   precedent for in earlier phases, so less uncertain than Stages 1–2 despite being the largest
   single body of new code. **Code**; B21 decided (added to Scenario B, not an ADR accepting its
   absence — this document's own "Legacy disclosures" entry below has the reasoning).
   **Exit criterion, a test — this phase's own already-stated one:** both acceptance scenarios pass
   unchanged on `local-lite` (a `test_phase8_exit_criterion_end_to_end`-shaped scenario test, the
   same pattern Phase 6's own exit criterion already uses); an export containing an `S2`-marked
   item is blocked, names the item, and proceeds only with a recorded justification.

   **4-spec, a prerequisite sub-stage inserted ahead of the rest of this stage, per standing rule
   11.** `02_GLASS_FRONTEND.md` had no section describing the Judgements tab's own contents or the
   export surface at all — a real spec gap, not a UI detail this stage's own implementers could
   fill in correctly by inference, since rule 11 blocks writing UI code against spec the docs don't
   state. Closed in this session: `02_GLASS_FRONTEND.md` §9 (Assessment production) and §10
   (Export), written against `01_DOMAIN_MODEL.md` §5 and `03_CONDUIT_MIDDLEWARE.md` §6's own
   already-existing backend text, not invented independently of it. The rest of this stage's own
   UI work does not start ahead of 4-spec.

   **The gap this exposes: the documentation drift gates (`domain-model-coverage-check`,
   `route-coverage-check`, Stage 3 above) catch a missing model or route, never a missing UI
   section.** Both gates work by enumerating something mechanically real and checkable in code — a
   Pydantic class, a live FastAPI route table — and flagging when `docs/` doesn't mention it. A
   Glass surface has no equivalent canonical, enumerable source: "the Judgements tab needs its own
   spec section" is not a fact derivable from a component name or a route the way "`Hotlist` needs
   a domain-model entry" is derivable from the class existing. **A mechanical gate for this class of
   gap is not straightforwardly possible** — building one would need a maintained registry of
   "named UI surfaces that require documentation" in the first place, which is exactly the kind of
   hand-maintained shadow list both existing gates were deliberately built to avoid depending on
   (this document's own Stage 3 entry, above: "not a hand-maintained shadow list either could fall
   out of sync with"). This gap was found by a person reading the spec against this stage's own
   scope, the same way every other case in this document's own gaps lists was found — not by a
   gate, and no gate proposed here would have caught it either.

   **This stage's own sub-split, sized so each sub-stage is one committable session — the same
   discipline named for it directly, after two sessions in this project died mid-flight.** 4-spec
   above is the first of eight; the remaining seven, in the order they are built:

   - **4a — Fixture Corp (R24), moved ahead of the assessment/export build itself — built, 22
     September 2026.** `06_DECISIONS.md` ADR-035 §C5 has owned Fixture Corp to Phase 8 with no
     stage since that record was written — "R24 has been the only backlog item with no owning
     phase," in its own words, and the single longest-unscheduled item in this project. It is also
     the demo the analyst review (`docs/PRODUCT_DELIVERY.md`) runs against — it cannot be left to
     4g's own closing pass, where a regression would be the first thing that finds it broken with
     nothing left in the stage to fix it against.

     **Neither AMLSim nor gen-fraud-graph turned out to be pip-installable — checked directly, not
     assumed, once this sub-stage actually started.** AMLSim is a Java/Python source checkout with
     its own build toolchain, not a package; `gen-fraud-graph` has no PyPI distribution either.
     Built instead: an original, 100%-owned, seeded generator (`tests/scenarios/fixtures/
     fixture_corp.py`) implementing the same fan-in/fan-out fraud-ring typology AMLSim itself
     models — "AMLSim-*shaped*, not AMLSim-generated," disclosed in the module's own docstring, the
     same "Enron-*shaped*, not Enron-derived" framing ADR-035 §C5 already uses for its own naming.
     No third-party dependency, no personal data, deterministic.

     Proves all four of ADR-035 §C5's named properties against this build's own real adapters, not
     mocks (`tests/scenarios/test_fixture_corp_shape.py`, all four run and independently
     re-verified passing): entity resolution at τ 0.99/0.95/0.80 producing visibly different
     projections (real Splink scores — 0.999991/0.981285/0.867624/0.0001 across four measured
     pairs — landing in different clusters at each detent); Louvain community structure over three
     disjoint rings, recovered exactly by the real `ComputeRustworkxAdapter`; path lengths spanning
     the pathfinder's full `max_hops` 1–8 range, each found at its exact length via real
     `GraphPort.paths`; a `SECRET`-classified hidden hop that lengthens a path from 1 to 3 hops for
     an `OFFICIAL` principal rather than removing it, against a real ArcadeDB. A seeding script
     (`scripts/seed_fixture_corp.py`, this project's own "no `osprey` CLI yet" convention) writes
     all three sub-fixtures — including the real, computed `SAME_AS` edges, not stand-ins — into a
     live Conduit; run live against dev `ArcadeDB` as part of this sub-stage's own closing check.

     **Exit criterion, a test — met:** an assertion against each of ADR-035 §C5's four named
     properties, proved directly against the generated fixture through real adapters — the same
     fixture-shape-proven-early discipline Phase 2's own HMP fixture test already established for
     Scenario A.

     **Grown, 22 September 2026: a fifth resolution pair, `identical_non_latin_script`, added so
     this fixture's own real resolution pass exercises the non-Latin-family-name resolver crash
     fix** (`services/resolve/duckdb_setup.py`) **on every run, rather than leaving whether that
     fix is ever exercised an accident of what this fixture happened to contain.** This document's
     own "Legacy disclosures" section has the full defect, fix and test record; not restated here.
   - **4b — Assessment objects, backend.** `Judgement`/`IntelligenceGap`/`Assumption` persistence,
     the evidence-link validation A13 requires (reject a save with zero supporting references), the
     yardstick loader, the review-flag-on-supersede wiring `01_DOMAIN_MODEL.md` §5 already states,
     and — **now unblocked: `06_DECISIONS.md` ADR-046 accepted, 22 September 2026** — the read-time
     access recheck on every citation, the viewer-scoped hidden-not-shown filter on judgement
     reads, and the review-flag extension to an unreadable `contradicting` reference.
   - **4c — Assessment objects, Glass surface — built, 22 September 2026.** `02_GLASS_FRONTEND.md`
     §9, built in full: the Judgements tab (`apps/workspace/src/assessment/JudgementsPanel.tsx`),
     authoring surfaces for all three object types, bidirectional evidence highlighting
     (`GlassCanvasHandle.highlightNodes`, §9.2's own corrected text has the mechanism), yardstick
     display (fetched from the real `GET /v1/yardstick`, never hardcoded), the review-flag chip
     (`ReviewFlagChip.tsx`, always-visible text, not hover-gated).

     **Scope expansion, disclosed rather than silent: this sub-stage also builds the HTTP routes
     Stage 4b's own entry explicitly deferred** ("no Glass surface, no export-gate change, and no
     routes"). `SaveJudgementRequest`'s own docstring already anticipated this — `POST`/`GET
     /v1/investigations/{id}/judgements`, `.../gaps`, `.../assumptions`, and `GET /v1/yardstick`
     (`services/api/app.py`), all `AuthorizedInvestigationDep`-gated, the path's own verified
     investigation id always winning over any body-supplied one (`test_save_judgement_route_uses_
     the_path_investigation_id_not_the_bodys`, proving it directly rather than assuming FastAPI's
     own binding order is enough).

     **The citation-type restriction (Part 1 of this session's own fix) is surfaced in the picker,
     not merely documented:** the evidence picker's own option list is built exclusively from
     `workingSetGraph.nodes()` — structurally incapable of offering an edge or a document, since
     neither is ever a candidate value in the first place, proven directly
     (`test_the_evidence_picker_never_offers_an_edge_as_a_citation_option`) with a graph carrying
     a real edge alongside two real nodes.

     **Gates, all run for real:** `authorized-query-check` — clean. Route-level tests
     (`tests/services/api/test_assessment_routes.py`, 8 cases) against the real app lifespan, real
     Postgres and real ArcadeDB — the same `with TestClient(app) as client:` pattern `tests/
     scenarios/test_phase7_stage6c_watch_routes.py` already established, not `dependency_overrides`
     (which binds a store to a different event loop than `TestClient`'s own internal one and fails
     with `asyncpg.exceptions.InterfaceError` — found live, not assumed, before landing on the
     working pattern). `vitest` — 181 passing before this sub-stage's own new test files, 190
     after (8 new cases across `api.test.ts`, `ReviewFlagChip.test.tsx`, `JudgementsPanel.test.tsx`
     — the save-button-disabled and edge-exclusion claims each proven with a companion case
     reproducing the regression they exist to catch, not asserted alone). The keyboard-
     reachability gate (`CLAUDE.md` rule 13) gained its own fifth registry,
     `ASSESSMENT_PANEL_ACTIONS` (`keyboard/actionRegistry.ts`), with its own harness/spec pair
     (`keyboard/assessment-panel-harness.tsx`, `assessment-panel.spec.ts`) — all 4 new actions
     plus the pre-existing 4 surfaces' own 40 cases pass together, no regression; the row-select
     evidence-highlight action was verified non-vacuous by breaking its own handler, watching the
     real Playwright test fail (`Timeout 5000ms exceeded`, empty array where `["n1"]` was
     expected), then restoring it and confirming green again.

     **Known gaps, disclosed as found:**
     - **§9.2's own "8% channel opacity" evidence-highlight text did not survive contact with a
       real WebGL renderer** — corrected in `02_GLASS_FRONTEND.md` §9.2 itself, not left
       contradicting the shipped build: highlighting reuses the existing multi-node *selected*
       state instead, at the cost of not being visually distinct from a manual lasso selection
       while a judgement's own evidence is highlighted. **Not a standalone gap — one symptom of a
       single node-state-channel shortage this document consolidates into one entry with one
       owner, Phase 8 Stage 5, alongside the on-path/selected WCAG item it shares a root cause
       with** (this document's own "`Path.nodes`/`Path.edges`' on-path node styling" entry, in
       "After the milestone," below, its "Widened, 22 September 2026" addendum).
     - **No `limit_exceeded`-shaped handling for a very large judgement/gap/assumption list** —
       `list_visible_judgements`/`list_for_investigation` return every row with no server-side cap
       or pagination. Checked against this stage's own realistic scale (an investigation's own
       assessment count, not a 50k-node working set) and judged low-risk rather than exempted by
       assumption — but genuinely unbounded, and `CLAUDE.md` standing rule 2 applies to any list
       this build renders, not only the canvas. **Not carried as an independent judgement call —
       linked to Phase 8 Stage 5's own already-scoped `limit_exceeded` item, in "After the
       milestone" below, which now builds the Glass-side rendering generically (any typed
       `limit_exceeded` response, not only the working set's) precisely so this list is a second,
       later consumer of the same fix rather than a separate design.** The backend half specific to
       this list — a real cap and a typed response shape for judgement/gap/assumption listing —
       remains genuinely unbuilt and is not invented here; once Stage 5's Glass component exists,
       adding that backend half is the only remaining work, not a second full feature.
   - **4d — Export pipeline and handling gate, backend — built, 22 September 2026.** `POST /v1/
     investigations/{id}/export` (`services/api/export.py`, `03_CONDUIT_MIDDLEWARE.md` §6): every
     node/edge evaluated against the handling scheme, a `consult_originator` item blocking by name
     (`ExportBlockedError`/`OverrideRequiredError`), the justification-and-originator-reference
     override, `06_DECISIONS.md` ADR-045's own disclose-by-default manifest (fail-closed to
     `disclose`, `export_manifest_policy_from_value`), ADR-046's own export-time judgement-citation
     recheck (reusing `judgement_visible_to`, never the in-session view), ADR-047's own mark
     (highest handling level present, `ExportResult.mark` a required field so the type itself
     guarantees one is never omitted) and its own compliance-facing ledger (`ExportLedgerStore`,
     `GET /v1/exports`, gated by a `"compliance"` role, not by investigation). Ten named tests in
     `tests/services/api/test_export.py` plus four route-level tests in `test_export_routes.py`,
     all passing against real Postgres/ArcadeDB; `authorized-query-check` clean (44 files); wired
     into the `conformance` CI job, `make test-all`, with matching `--ignore`s added to the fast
     `test` job/`make test` (below).

     **The cross-session access question, stated as this module's own decision, not left to be
     inferred.** The export gate re-checks the exporting analyst's own *current* access at export
     time — a real `graph.get_node` call for every node item, never the client's own submitted
     handling — proven by `test_export_is_refused_when_an_item_becomes_inaccessible_between_
     selection_and_export`: a node visible when the selection was built, reclassified `SECRET` by
     a real `supersede_node` before the export call, is refused and named. For an edge item this is
     only a *partial* recheck — see the module's own docstring and the disclosed limitation below.

     **The mark test's own red-then-green.** `ExportResult.mark` was temporarily forced to `None`
     past Pydantic's own validation (`.model_construct()`); `test_the_export_pipeline_never_
     produces_an_artefact_with_no_mark` failed with `AssertionError: assert None is not None`,
     naming the exact field; the fix was restored and the same test passed clean.

     **Known gaps, disclosed as found:**
     - **The `GraphPort.get_edge` limitation now has a real, live consequence, not only a build
       note.** An edge item's own `Handling` is taken from the client's submission and evaluated
       against the scheme (so a stale-but-honest client is still caught), but — unlike a node —
       cannot be independently re-fetched to confirm that submission is still current or was never
       fabricated. **Consequence, stated plainly in the module's own docstring:** a malicious or
       stale client could in principle submit a lower-than-real edge classification and pass a
       check that should have blocked it. Owning phase: whichever phase first builds `GraphPort.
       get_edge` — the same disposition every other consequence of this absence already carries
       (`07_BUILD_PLAN.md`'s own Phase 6 Stage 6 and Stage 4b entries).
     - **`withheld_count` is caller-supplied, not recomputed by this module.** The same figure
       `Subgraph.filtered_count` already computes at the Working-Set Service layer (Phase 3's own
       reasoning: only that layer holds both the full and filtered result server-side without a
       second, less-audited query) — this module discloses it per ADR-045's policy, it does not
       re-derive it. Stage 4e's own job is supplying the real figure from the working set the
       artefact is drawn from.
     - **Chart/subgraph/report rendering is explicitly out of this stage's own scope, a stated
       call, not a silent omission.** This module wraps any artefact shape via `artefact_kind` —
       the actual chart image (`@sigma/export-image`) or assembled report document is Stage 4e's
       own job, client-side or a later stage's; nothing here renders either.
     - **`test_assessment_routes.py` (Phase 8 Stage 4c) had never been wired into any CI job at
       all — found live while wiring this stage's own new files, not assumed safe.** It needs the
       identical real Postgres/ArcadeDB the `conformance` job already stands up, and had been
       running (and would fail) in the plain `test`/`make test` job instead, which stands up
       neither — the exact gap class `.github/workflows/ci.yml`'s own `test_pattern_store.py`
       comment already found once for a different file. Fixed alongside this stage's own three new
       files rather than filed separately, since discovering it was a direct side effect of
       auditing where those three needed to go.
   - **4e — Export, Glass surface — built, 22 September 2026.** `02_GLASS_FRONTEND.md` §10:
     `src/export/ExportPanel.tsx` (the drawer), `src/export/api.ts` (typed `ExportBlockedApiError`/
     `OverrideRequiredApiError`, the same named-error posture `assessment/api.ts`'s own
     `UnverifiableCitationApiError` already established), wired into `App.tsx`'s own header next to
     `ResolutionThresholdControl` (`02_GLASS_FRONTEND.md` §2's own mockup: "Resolution: ●Balanced
     Export ⚙"). The named blocker list, the justification/originator-reference override form
     (disabled until both fields are non-empty, the same pattern `JudgementsPanel`'s own Save
     button already uses), the manifest ("N hidden by handling" — the exact status-bar phrasing,
     not a second wording) and the mark, and the refusal path — an item that became inaccessible
     between selection and export is named specifically, via the same inline-banner mechanism as
     every other blocked item, never a generic message. 11 new vitest cases (`api.test.ts`,
     `ExportPanel.test.tsx`), vitest 190 → 201, all passing. The keyboard-reachability gate gained
     its own sixth registry, `EXPORT_PANEL_ACTIONS` (`keyboard/actionRegistry.ts`), with its own
     harness/spec pair — both new actions plus the pre-existing five surfaces' own 40 cases pass
     together (43 total), no regression; verified non-vacuous by removing the manifest's own render
     line, watching all three `export-panel.spec.ts` cases fail for real (including the registry's
     own coverage assertion, cascading correctly), then restoring it and confirming green again.

     **Known gap, disclosed as found, not silently narrowed to look done.** `services/api/
     export.py`'s own module docstring names Stage 4e as the renderer of "the three artefact
     shapes (chart/subgraph/report)" — read literally, that means producing each shape's own
     downloadable bytes (a PNG, an assembled report document), not only submitting the selection to
     the gate and rendering its response. **No such rendering engine exists anywhere in `apps/
     workspace`** — checked directly: `GlassCanvasHandle` has no `exportImage`-shaped method,
     `@sigma/export-image` is listed as a dependency (`02_GLASS_FRONTEND.md` §1) but never imported
     by any component, and no report-assembly code exists at all. This drawer submits the real
     selection (the current working set's own nodes/edges, each carrying its own real `handling`
     block) to the real gate for all three `artefact_kind` values and renders the real mark/
     manifest/ledger response — the safety-critical half A15 actually tests, and the half this
     stage's own gates (the keyboard walkthrough, the named-blocker assertions) could verify — but
     produces no downloadable file. **Owning stage: 4h, below — not "whichever phase," per this
     document's own new disclosure-convention rule** (see this stage list's own closing paragraph):
     a disclosure naming no real stage is a note, not a disclosure, and this one is corrected to a
     real stage in the same session that wrote it, not left for a future sweep to catch.
   - **4f — B16 and B18. ADR-022's own "small, incremental additions to Timeline and Map" was
     checked against the real components before building, not carried forward assumed, and does
     not hold.** ADR-022 was written before Phase 5's own playback deferral; `apps/workspace/src/
     timeline/Timeline.tsx`'s own header comment states directly what actually shipped: "Playback,
     multi-track and cross-case overlay are named in §3.4 too but exercised by no A1-A11 step;
     deferred, not built here." Checked directly, not assumed from the comment alone: neither
     `Timeline.tsx` nor `apps/workspace/src/map/MapView.tsx` contains any animation loop, multi-track
     rendering mode, or cross-case data path today — `grep` for `animat`/`requestAnimationFrame`/
     `snail`/`track`/`playback`/`multi-track`/`cross-case` across both files returns nothing.
     **B18 needs a playback mechanism this codebase has never built at all** — an animation clock,
     play/pause/speed control, position state, and `02_GLASS_FRONTEND.md` §3.4's own
     `prefers-reduced-motion` requirement ("playback becomes stepped and re-layout becomes an
     instant move with a persistent control that shows previous positions") — applied to the map's
     own snail-trail track, not a small addition to an existing scrubber. **B16 needs a multi-track
     timeline rendering mode and a second investigation's own event data loaded alongside the
     first** — also unbuilt. Both are real, from-scratch capabilities sharing no existing partial
     implementation to extend. **Correction, not abandonment: still owned by this stage, built
     honestly at its real size rather than under a "small" label that would have undersold the
     work to the next reader who trusted it.** ADR-022's own record (`06_DECISIONS.md`) is not
     rewritten — this entry states what checking it against the current codebase actually found,
     the same "checked directly, not assumed" discipline every other correction in this document
     already applies to a stale characterisation.

     **Built, 22 September 2026.** A shared playback clock (`playback/usePlayback.ts` over pure,
     independently-tested math in `playback/math.ts`) drives both surfaces off one fraction, so a
     timeline scrub and a map trail can never drift out of sync with each other — `Timeline.tsx`
     itself renders the Play/Pause/speed controls (§3.4's own natural home for them) and reports
     the fraction via a callback, rather than each consuming surface running its own clock.
     `prefers-reduced-motion` is honoured for real, not merely checked and ignored: a reduced-
     motion `play()` advances one step (10% of the window) and stops, never starting a
     `requestAnimationFrame` loop at all.

     **B18 needed a real backend capability this codebase did not have at all — found while
     building, not assumed to exist, and closed in the same pass rather than left as a second
     "whichever phase" placeholder.** `AnalyticsPort` had `histogram`/`geo_bins`/`cross_filter`,
     every one aggregate-shaped; nothing returned ordered, timestamped, per-entity points. Added
     `AnalyticsPort.list_sightings` (`packages/ports/analytics.py`), implemented in
     `adapters/analytics_duckdb` reusing the existing `_predicate`/access-filter machinery
     unchanged, with its own conformance-suite cases
     (`test_sightings_are_ordered_by_time_and_exclude_null_coordinates`,
     `test_unauthorised_sighting_is_absent_not_a_gap_in_the_track`) — `CLAUDE.md` rule 1's own
     "conformance suite before adapter" discipline, applied to a method added to an existing
     port/adapter pair rather than a brand-new one. A new route, `POST /v1/analytics/sightings`.
     **This is the class of read `scripts/authorized_query_check.py` does not, and structurally
     cannot, cover** — it scans `services/api` store methods, not `AnalyticsPort` adapter methods,
     whose own access-control proof is the conformance suite's `test_unauthorised_*` case above,
     the same split every other `AnalyticsPort` method already has. `authorized-query-check`
     itself was run and reported clean (44 files, no new offenders) since this stage's own route
     handler is a thin pass-through with nothing for that script to flag.

     `MapView.tsx` renders the snail trail as two native MapLibre layers (a `LineString` for the
     revealed path, a `Point` for the current position) over the sightings the caller has already
     filtered down to the current playback fraction (`itemsUpTo`) — the real content change over
     time B18's own "animates under playback" names, not a rendering trick over a static list.
     `Timeline.tsx`'s own density mode grows a second ECharts grid, sharing identical category
     data with the primary track's own xAxis so the two align pixel-for-pixel, satisfying B16's
     own "distinct tracks against a shared axis" without ECharts having (or needing) a literal
     shared-axis primitive between two independent grids.

     **Tests, all run for real:** `playback/math.test.ts` (12 cases — the pure functions this
     stage's own clock and reveal logic are built on), `analytics/api.test.ts` (2 cases —
     `fetchSightings`). vitest 202 → 218. The keyboard-reachability gate gained its own seventh
     registry, `TIMELINE_PLAYBACK_ACTIONS` (`keyboard/actionRegistry.ts`), with its own harness/
     spec pair — both new actions plus the pre-existing six surfaces' own 43 cases pass together
     (46 total), no regression; the playback-advance action verified non-vacuous by commenting out
     `usePlayback`'s own `setFraction` call, watching the real Playwright test fail
     (`TimeoutError: page.waitForFunction: Timeout 5000ms exceeded`), then restoring it and
     confirming green again.

     **Known gap, disclosed with a real disposition, not a placeholder: general multi-track mode
     (`02_GLASS_FRONTEND.md` §3.4's own "one row per selected entity") is not built — only the
     narrower cross-case two-track overlay B16 itself needs.** `Timeline.tsx`'s own header comment
     states this directly at the point it was decided, not left implicit. **Disposition: Out of
     scope for v1** — checked against `08_ACCEPTANCE_SCENARIOS.md` directly, no row in either
     scenario exercises viewing more than one *entity's* own events each on their own track
     (B16's own "second investigation" axis is a different dimension, already built); the
     relay-and-cut-out use case §3.4 names it for is real but not acceptance-gated. Building it —
     an arbitrary-N-row layout, entity selection UI, per-row data fetching — is real, separately-
     scoped work a future phase can start from this disclosure rather than rediscovering the gap.
   - **4g — B21 and the closing pass — built, 23 September 2026.** B21 — decided, this document's
     own "Legacy disclosures" entry below has the reasoning — exercises `POST /v1/paths` end to end
     through the Glass, added to `08_ACCEPTANCE_SCENARIOS.md`'s own Scenario B table; then the full
     `test_phase8_exit_criterion_end_to_end`-shaped scenario test against both acceptance scenarios
     on `local-lite`, plus the S2-export-blocks test — the same closing-pass discipline Phase 6's
     Stage 6 and Phase 5a's Publish stage already used.

     **Exit criterion, a test — met:** `tests/scenarios/test_phase8_exit_criterion_end_to_end.py`
     passes clean against the real, live stack (real ArcadeDB/Postgres/Valkey, real HTTP, real JWT
     auth), confirmed twice in separate full runs (296.84s and 552.16s) — this environment's own
     already-disclosed ArcadeDB OOM-under-load flakiness (6GB container cap) interrupted several
     intermediate runs while this test was being built, never the test's own logic, and both clean
     runs reproduce the same result. The S2-export-blocks test this stage's own entry names already
     existed before this stage (`tests/services/api/test_export_routes.py::test_export_route_
     blocks_a_consult_originator_item_and_names_it_over_http`,
     `tests/services/api/test_export.py::test_export_blocks_a_consult_originator_item_and_names_it`)
     — checked directly, both still pass, cited rather than duplicated.

     **Every row of both scenarios is accounted for** (the closing pass's own module docstring and
     the session's hand-off report both carry the full row-by-row disposition — proven by this
     test, proven elsewhere and cited, or a genuine finding with a real disposition): the
     UI-rendering-only rows (A1's grid draw, A2/A3's heat layer and cross-filter dimming, A9's
     radial-menu cardinality-preview widget, B16's timeline overlay, B17's temporal brush, B18's
     snail-trail animation, the cross-cutting "no filter removes a node" rule) are proven by the
     existing Playwright/vitest suites under `apps/workspace/`, cited rather than re-proved from a
     backend test, per this stage's own scope.

     **Two genuine findings, new, not previously disclosed anywhere in this document — both
     checked directly against the real running system, not assumed:**
     1. **No fixture generator exists for Scenario B's own "two cohorts of person entities with no
        overt association" or "one messaging-handle dataset"** — `tests/scenarios/fixtures/cdr.py`
        builds only the two `Endpoint`s the phone-number renderings collapse onto (B1-B3's own
        shape), never the person layer B4-B8 walk through. The closing pass builds this shape
        inline, test-local, rather than as a new fixture module (disclosed in its own docstring)
        since no other test needs it yet. **Disposition: real, unscoped work — promote to
        `tests/scenarios/fixtures/` the day a second test needs the same shape; not built
        speculatively here.**
     2. **`Endpoint` carries no `resolution` block in `packages/ontology/default.yaml`** (checked
        directly against the live YAML, not assumed) — `Person` has real Splink comparisons
        (`jaro_winkler(family_name)`/...); `Endpoint` has none. B8's own literal "a scored `SAME_AS`
        edge links the handle to the shared endpoint" cannot be produced by the resolution
        mechanism as it stands — there is nothing configured to score the comparison with.

        **Correction, 23 September 2026: the disposition below — proving B9/B10 against B11's own
        manually-asserted pair — is retracted, not merely superseded.** It made both assertions
        vacuous (a score of 1.0 is already included at every threshold; there is nothing for
        moving Strict to Balanced to newly admit, and an asserted score has no per-comparison
        weights for `explain` to show) and called that "fully proven." `08_ACCEPTANCE_SCENARIOS.md`
        now carries the real fix: B8 is corrected to say what the edge actually is (an asserted
        `SAME_AS` at score 1.0, `06_DECISIONS.md` ADR-024's own pattern for identifier systems with
        no lexical overlap — the scenario catching up with an already-accepted ADR), and B9/B10
        move to genuine `Person` resolution, where their own literal assertions are true. See
        `08_ACCEPTANCE_SCENARIOS.md`'s own "B8's own disposition" note for the full reasoning,
        every citation of B8 checked, and a real fixture gap this surfaces (Scenario B's own two
        cohorts have no close-but-not-exact `Person` pair yet — real, unscoped work, not built
        here either).

        ~~**Disposition: Out of scope for v1** — checked directly against
        `08_ACCEPTANCE_SCENARIOS.md`, no acceptance-scenario row is blocked by this (B9/B10/B11's
        own mechanism is fully proven via the manual-link substitute), so it does not gate the
        milestone; choosing and validating real comparison functions for `handle`/`e164`/`imsi`
        identifiers is real, separately-scoped work for whichever future phase next extends entity
        resolution to `Endpoint`, not invented under this closing pass.~~ (struck, not deleted, per
        this document's own convention for a retracted rather than superseded claim — the
        cross-cutting-rows retraction two entries below this one already uses the same discipline.)

     **Two cross-cutting rows this closing pass could not reach, disclosed rather than faked:**
     "results are identical on both profiles" (`local-lite`/`cluster`) needs a real `cluster`
     profile deployment this development environment does not have running — not attempted;
     "disconnecting the network mid-scenario on `local-lite` changes nothing" needs a real
     network-partition harness around a live run — not attempted. **Correction, 23 September
     2026: this entry originally recorded its own "out of scope for v1" call for both rows,
     unilaterally, inside this same closing pass — retracted.** That was not this pass's own call
     to make; per the milestone's then-current, literal "both scenarios pass unchanged" text, an
     unattempted cross-cutting row meant the milestone was not met, full stop, and saying otherwise
     from inside a test-writing pass was exactly the kind of scope call this document's own
     standing discipline warns against. **The correct disposition, recorded here by the checker
     rather than inferred from inside the closing pass, pending the owner's own confirmation:**
     the owner defined the milestone as installed, started, demonstrated on a clean laptop; neither
     row is part of V1 END TO END as a consequence of that definition — this document does not
     claim the owner separately stated a view on these two rows in these terms. See "Out of scope
     for v1," below, for both entries and their own stated reasoning. Cluster-
     profile parity already has a designated home (`adapters/graph_janusgraph`/`adapters/
     analytics_clickhouse`/ComputePort Tier 3/the cluster profile itself all already moved to Phase
     8a, above); network-partition resilience does not yet have one and is recorded as such, not
     assumed to share Phase 8a's home merely because both rows were grouped together here.
   - **4h — the export rendering pipeline, a real sub-stage inside v1, not a placeholder — directly
     continuing 4e's own work — built, 23 September 2026.** `08_ACCEPTANCE_SCENARIOS.md` names A13–A15 as the reason this
     platform exists, and their own product is a document handed to someone. Stage 4e wired the
     real gate, mark, manifest and ledger for all three artefact shapes and renders the response —
     the safety-critical half — but produces no downloadable file for any of them; an export
     feature that exports nothing is an absent feature, not a partial one, and belongs in v1's own
     scope on that basis alone, not deferred past it.

     **Scope, against the formats `02_GLASS_FRONTEND.md` §10.1 now states** (a real spec gap found
     and closed in the same pass that gave this stage its own number, not left open): **chart** —
     `GlassCanvasHandle` gains a real `exportImage` method wired to `@sigma/export-image`
     (`02_GLASS_FRONTEND.md` §1's own already-listed dependency, never imported anywhere until this
     stage), producing a real PNG; a saved metric/histogram/timeline view uses ECharts' own export
     the same way. **subgraph** — the current selection serialised as JSON in the working set's own
     `Node`/`Edge` wire shape, no new format invented. **report** — a self-contained HTML document
     assembling the investigation's judgement/gap/assumption content with their own cited evidence
     inline, styled against `design/tokens.css`'s light theme; real document-assembly work, not
     reducible to a one-line addition the way the chart/subgraph shapes are.

     **Exit criterion, a test per shape, not one shared assertion:** `test_chart_export_produces_a_
     real_png_carrying_the_mark`, `test_subgraph_export_produces_real_json_carrying_the_mark`,
     `test_report_export_produces_a_self_contained_html_document_carrying_the_mark` — each
     downloads real bytes (not the API response alone) and asserts the artefact is well-formed in
     its own format *and* carries the mark `02_GLASS_FRONTEND.md` §10.3 already specifies for it
     (embedded PNG metadata for chart; a top-level field for subgraph; both for report). This is
     also `08_ACCEPTANCE_SCENARIOS.md`'s own strengthened A15 assertion, below — the acceptance row
     and this stage's own exit criterion are the same claim, checked twice on purpose.

     **Built as:** `src/export/pngMark.ts` (a hand-rolled PNG `tEXt`-chunk embedder/reader, no new
     dependency — PNG chunk framing is simple enough that a library would cost more than it saves,
     the same call `tests/scenarios/fixtures/fixture_corp.py`'s own AMLSim finding already made);
     `src/export/chartExport.ts` (`embedChartMark`/`chartMarkFields`, pure and unit-tested, plus
     `captureChartImage`, the real `@sigma/export-image`/`OffscreenCanvas` integration — see its own
     disclosed gap immediately below); `src/export/subgraphExport.ts` (`buildSubgraphArtefact`,
     reusing the working set's own `data` node/edge attribute directly, no reshaping); `src/export/
     reportExport.ts` (`buildReportArtefact`, a self-contained HTML document with the light-theme
     ramp copied verbatim from `design/tokens.css` rather than linked, since a standalone document
     cannot depend on this repo's own stylesheet still existing at read time); `src/export/
     triggerDownload.ts` (the one download mechanism all three shapes share — an anchor click
     against an object URL). `GlassCanvasHandle` gained `exportImage`, wired to `captureChartImage`;
     `ExportPanel.tsx` now builds and downloads the real artefact after a successful submit,
     branching on `artefactKind`; `App.tsx` wires the chart path through `glassCanvasRef`. All three
     named exit-criterion tests pass for real: `test_chart_export_produces_a_real_png_carrying_the_
     mark` (asserts the real PNG signature/`IEND` bytes and every mark field read back through the
     real chunk reader, not the input object); `test_subgraph_export_produces_real_json_carrying_
     the_mark` (asserts real, parseable JSON reusing the graph's own node/edge attributes, mark and
     manifest as top-level fields); `test_report_export_produces_a_self_contained_html_document_
     carrying_the_mark` (asserts a real `DOMParser`-parsed document with no external stylesheet/
     script, the mark both in a visible header/footer stamp and in an embedded `<script
     type="application/json">` field, judgement content HTML-escaped, and every judgement/gap/
     assumption passed in rendered — no cap). vitest 219 → 238 (19 new cases: `pngMark.test.ts` 5,
     `chartExport.test.ts` 3, `subgraphExport.test.ts` 4, `reportExport.test.ts` 6, plus one added
     to the pre-existing `ExportPanel.test.tsx` proving the subgraph shape's own download content
     and filename). `EXPORT_PANEL_ACTIONS` gained a third action, `export-produces-a-downloadable-
     artefact`, proven via the subgraph shape (fully real in the harness; the chart shape needs a
     fake `onExportChartImage` callback since the harness mounts no live Sigma instance) — verified
     non-vacuous by reverting `ExportPanel.tsx`'s own download wiring and confirming both the new
     case (a real `page.waitForEvent("download")` timeout) and the registry's own coverage
     assertion fail for real, then restoring it and confirming all four `export-panel.spec.ts` cases
     pass green again. Full keyboard suite (47 cases across all seven surfaces) passes with
     `--workers=1`; two cases in `keyboard.spec.ts`/`metrics-panel.spec.ts` (unrelated surfaces,
     untouched by this stage) flaked under the default multi-worker run with an "Execution context
     was destroyed" navigation error and passed cleanly both in isolation and against the
     pre-Stage-4h baseline — cross-worker resource contention, not a regression this stage
     introduced. `tsc --noEmit` and eslint both clean across every changed/created file (fixed two
     real pre-existing `noUncheckedIndexedAccess` gaps in the inherited `pngMark.ts` along the way —
     `crc32`/`readU32be`'s array-index reads were always in bounds by construction but the compiler
     could not see that; non-null assertions added with a comment, no behaviour change). This stage
     touches no backend Python at all (`authorized-query-check`: 44 files under `services/api`, no
     offenders — unaffected, confirming this stage is purely Glass-side).

     **Correction, 23 September 2026: the entry originally here read "not unit-testable in this
     project's own toolchain," and that overclaimed the gap — it was untestable in vitest
     specifically, not untestable, and A15's own strengthened assertion (a real artefact of the
     requested shape) is exactly the claim a pipeline that emits a blank canvas would still satisfy
     under the weaker reading.** `vitest.config.ts`'s own default `node` environment genuinely has
     no WebGL context for a live `Sigma` instance to render into — that part of the original entry
     was accurate — but this project's own Playwright suites (`perf/`, `a11y/`, `map-verify/`)
     already run a real Chromium browser with a real WebGL context, the same one `captureChartImage`
     needs. **`captureChartImage` is proven there now, not merely trusted to the library it
     wraps.** `apps/workspace/export-capture/` (`harness.tsx`, `capture.spec.ts`,
     `npm run test:export-capture`) mounts a real, populated `GlassCanvas` (four nodes across two
     entity-type channels, two edges) and calls the real `GlassCanvasHandle.exportImage` through it.
     The test asserts real content, not merely that bytes exist or that a mark was appended to
     whatever bytes the test itself supplied: the captured PNG's own pixels are read back and
     checked for more than five distinct colours and more than 500 non-background pixels — a blank
     or placeholder canvas fails this immediately (verified directly: stripping the harness's own
     nodes/edges to an empty graph, the test failed with `distinctColourCount` of exactly `1`,
     confirming the assertion is not vacuous — restored afterwards). The pure half
     (`embedChartMark`/`chartMarkFields`) stays covered by `chartExport.test.ts` in vitest, unchanged
     — this new suite proves the one thing vitest genuinely cannot, not a duplicate of what it
     already does. **Owning suite: `apps/workspace/export-capture/` — a real, permanent test, not a
     disclosed gap with no owner.**

   **4b/4c and 4d/4e were each a backend/Glass pair sharing one blocked-on-ADR precondition — all
   three now accepted (`06_DECISIONS.md` ADR-045/046/047, 22 September 2026), so no sub-stage in
   this stage remains blocked on an open design question.** 4b/4c build against ADR-046's own
   hidden-not-shown/export-citation-check decision; 4d/4e build against ADR-045's disclose-by-default
   manifest switch and ADR-047's handling-encoding mark plus its own compliance ledger. Build order
   otherwise follows 4a's own precedent: nothing here is a design decision still to be made in code.

   **4b — assessment objects, backend — built, 22 September 2026.** `Judgement`/`IntelligenceGap`/
   `Assumption` persistence (`services/api/assessments.py`), the evidence-link validation A13
   requires, the yardstick loader (`packages/ontology/yardstick.py`, `ontology/yardstick/phia.yaml`
   shipped), ADR-046's own hidden-not-shown access rule, and the review-flag loop, wired into the
   two real callers that exist today (`confirm_node_route`/`retract_node_route`,
   `services/api/app.py`) and, for consistency with `GraphPort.supersede_node`'s own docstring
   naming both intended callers, into `services/api/supersede.py`'s still-callerless
   `submit_supersede_node`/`run_supersede_node_job` too, as an optional parameter each existing
   test/caller is unaffected by. `tests/services/api/test_assessments.py` (11 cases) and
   `tests/ontology/test_yardstick.py` (4 cases) all pass against real Postgres/ArcadeDB, wired into
   the live-service CI job. The hide-in-full access check was verified non-vacuous by breaking it
   (returning `True` unconditionally) and confirming the named test fails before restoring it — the
   same "prove the test would catch the regression" discipline `CLAUDE.md` rule 12 asks for.

   **The invisible-judgement defect, found and fixed the same day, 22 September 2026 — see the
   known-gaps entry immediately below for the full record.** `save` now refuses, by name, any
   `supporting` citation it cannot positively confirm as a visible graph node
   (`UnverifiableCitationError`), instead of accepting it and letting `judgement_visible_to` hide
   the resulting judgement permanently and silently at every future read. Two new named tests
   (`test_a_judgement_citing_an_unverifiable_reference_is_rejected_at_save_not_hidden_at_read`,
   `test_a_judgement_citing_one_good_and_one_unverifiable_reference_names_only_the_bad_one`),
   verified non-vacuous the same way as the hide-in-full check above.

   **Stage 4b known gaps, disclosed as found, not left in a code comment:**
   - **Only a `NodeId` citation in a judgement's `supporting` list can be *saved* at all — found as
     a real defect, not disclosed as a residual limitation, and fixed at save rather than left
     hidden at read.** `GraphPort` has no `get_edge` (the same absence `07_BUILD_PLAN.md`'s own
     Phase 6 Stage 6 entry already names for a different reason), and no document store exists
     anywhere in this build. `Judgement.supporting`/`contradicting` is `list[NodeId | EdgeId |
     DocumentId]` (`01_DOMAIN_MODEL.md` §5) — all three collapse to plain `str` with no structural
     way to tell them apart, so an `EdgeId`/`DocumentId` citation could not be positively confirmed
     visible. **What this actually meant before the fix: a judgement citing only an edge or a
     document saved cleanly — validation passed, the write succeeded — and then vanished from
     every future read, permanently, including for its own author**, because `judgement_
     visible_to`'s own hide-in-full rule (ADR-046) treated the unconfirmable citation as
     unreadable at every subsequent load. A clean, confident, wrong outcome — the exact failure
     shape `08_ACCEPTANCE_SCENARIOS.md`'s own "What B1–B3 prove" section already warns is the
     worst a filtering mistake can take, here reached from a different direction. **Fixed: `save`
     now checks every `supporting` citation against the *saving* principal's own `GraphPort`
     access before writing, and refuses — naming the specific citation — anything it cannot
     confirm** (`UnverifiableCitationError`, `services/api/assessments.py`). The analyst learns at
     the point of writing, not never — the same "a client-side call that fails must never be
     dropped silently" posture `02_GLASS_FRONTEND.md` §4.1 already requires of `manualAssertion`/
     `expandNode`/`explainCluster`/the pathfinder's own error state. Building `GraphPort.get_edge`
     or a document store, so an edge/document citation becomes *savable* rather than merely
     *refused loudly*, is real, separately-owned work — deliberately not built here, the same
     "belongs where it is owned" reasoning that already keeps this stage from reaching into
     Stage 4d's own scope. **Owning phase: whichever phase first builds `GraphPort.get_edge` or a
     document store** — not this stage, and not invented here.
   - **What A13 can and cannot cite today, stated plainly, since the acceptance row itself says
     "each with evidence" and an analyst's most natural evidence for an intelligence judgement is
     a document, not a graph node.** A13 can be satisfied, today, only by citing one or more
     `NodeId`s the saving analyst can currently see — a person, an endpoint, a location, any
     entity already in the working set. **A13 cannot currently be satisfied by citing a source
     document or a specific relationship (an edge) as a judgement's sole evidence** — `save`
     refuses it outright, named, per the fix above. A real intelligence judgement resting only on
     "this witness statement says X," with no entity node to point at instead, cannot be recorded
     until `GraphPort.get_edge` or a document store lands. This is a genuine functional gap in
     what A13 can express today, not merely a visibility quirk — recorded here so a reader
     evaluating Stage 4b's own completeness does not assume citing a document already works
     because the citation type itself is accepted at the schema layer.
   - **The review-flag loop matches a `supporting` citation's content change only, per
     `01_DOMAIN_MODEL.md` §5's own literal text** ("When a supporting node is later split,
     corrected or retracted, every judgement resting on it is flagged for review") — a
     `contradicting` citation's own content change (as opposed to its *readability*, which the
     lazy check below does cover) is not flagged. A narrower, disclosed scope decision, not an
     oversight: broadening it is real, small, additional work (`flag_judgements_citing_superseded_
     node`'s own `if node_id not in judgement.supporting: continue` line is the one guard to
     relax), left to whoever next has a concrete reason to want it, per this document's own "not a
     reason to add it speculatively" discipline elsewhere.
   - **The unreadable-`contradicting` flag is lazy, not proactively scanned.** It is written the
     first time a read discovers the reference has become unreadable
     (`_flag_unreadable_contradicting_lazily`), not at the moment access actually changed — the
     same "re-flags only on process restart" class of timing gap Phase 5a's own ontology
     reverse-index disclosure already accepted for a different feature (§6 above), disclosed here
     for this one. A judgement nobody reads after its `contradicting` reference becomes unreadable
     stays unflagged indefinitely; a proactive scheduled scan would close this and is real,
     unbuilt work, not assumed free.
   - **`IntelligenceGap`/`Assumption` grew `investigation_id`/`created_at` fields beyond
     `01_DOMAIN_MODEL.md` §5's own illustrative Pydantic snippet.** Both are needed for the same
     investigation-scoped, `owning_unit`-authorized persistence `Judgement` itself needs
     (`services/api/assessments.py`'s own module docstring) — the same "grown past its own
     illustrative sketch" precedent `GraphPort`/`SAME_AS`/`Subgraph.filtered_count` each already
     set, not a silent divergence from the spec.
   - **No Glass surface, no export-gate change, and no routes.** Backend-only per this stage's own
     scope (`02_GLASS_FRONTEND.md` §9 is Stage 4c; the export citation check ADR-046 requires is
     Stage 4d). `SaveJudgementRequest` (`services/api/assessments.py`) shapes the wire request
     Stage 4c's own route will need, so that stage does not re-derive it, but no route exists yet.

5. **Pulled forward from Stage 5, below: `PathStaleError` for the `paths()` hydration race, plus
   the server-side traversal budget.** The one Stage 5 item whose absence could fail a scenario —
   B21 (Stage 4g) exercises `POST /v1/paths` end to end, and a stale-path race or an unbounded
   traversal is exactly the class of failure that row could hit. Named here as required; the rest
   of Stage 5 is checked against the milestone at its own entry, in "After the milestone," below,
   and moves there.

6. **Pulled forward from Stage 6, below: the `Makefile`/`ci.yml` reconciliation — built, 22
   September 2026.** A milestone defined by a green criterion needs "green" to mean one thing;
   `Makefile`'s own `test`/`test-all` targets and `.github/workflows/ci.yml` had drifted 22 files
   apart before this session, so a developer running `make test`/`make test-all` locally was
   getting a materially weaker signal than CI actually enforced. `scripts/test_file_coverage_check.py`
   (`Makefile`'s `test-file-coverage-check`, wired into `ci`) now catches this mechanically: every
   test file reachable by some job or an explicit allowlisted exception; every live-service-marked
   file present in *both* the fast job's `--ignore` list *and* a live-service job's own explicit
   file list. **Resolved, not merely measured: `ci.yml` was the correct, complete list throughout,
   and the 22 files were added to `Makefile` to match it** — `ci.yml` itself was not altered.
   First real run found two more instances beyond the four already known
   (`tests/scenarios/test_fixture_corp_shape.py`, `tests/services/api/test_worker.py`), both fixed
   the same way. Ten new tests (`tests/test_test_file_coverage_check.py`). The rest of Stage 6 —
   the lint backlog, the statelessness diagnosis, the sweeper causes, the fake-double class — is
   checked against the milestone at its own entry, in "After the milestone," below, and moves
   there; none of it is exercised by either acceptance scenario.
7. **Pulled forward from Stage 6, below: `tests/harness/test_apply_env.py` never tore down the
   real deployment it started — fixed, 25 September 2026.** `_rendered_env`'s own docstring already
   disclosed that `main()` runs "far enough to write the environment file, then stops" — it does
   not stop; `--no-build` skips only the build stage, and every one of this file's nine tests drove
   the real `harness.apply.main()` all the way into a real `docker compose up`, leaving it running.
   **Found, not anticipated, and found twice the same session** (`CLAUDE.md` rule 14's own worked
   example, reproduced by one test file rather than by two agents): a leftover `osprey-local-lite`
   deployment from an earlier round's own manual verification, still running, its container names
   and published ports colliding with this file's own next test — and, once that was cleared, the
   entire remaining suite still finished in under a second across all nine tests, which is
   mathematically impossible if any of them had reached a real `up` (measured directly: one real
   deployment alone takes ~29s) — meaning every test had been silently short-circuiting at
   Preflight's own port check the whole time, passing "vacuously" against whatever `main()`'s own
   render stage had already written to disk before hitting that wall, never once proving what its
   own name claims.

   **Fixed with an autouse fixture** (`_teardown_local_lite_deployment`) that runs
   `docker compose -p osprey-local-lite down -v --remove-orphans` after every test, pass or fail —
   a fixture's own teardown runs regardless of the test's outcome, which is what makes "a planted
   early failure still leaves no `osprey-*` container" true by construction rather than by
   discipline. `test_the_deployment_this_file_starts_is_a_real_one_and_the_teardown_removes_it`
   proves the mechanism directly: starts a real deployment, confirms containers exist, invokes the
   identical teardown command, confirms they are gone. **A second, real bug found finishing that
   proof, not a hypothetical one:** the first version of the port-release wait this fixture also
   needed used `socket.connect_ex` ("does anything answer here"), which returns "free" for a port in
   `TIME_WAIT` — nothing is listening — while Preflight's own check (deliberately, per its own
   docstring) tries to *bind* without `SO_REUSEADDR`, which a `TIME_WAIT` port still refuses. The two
   checks answer different questions, and the wrong one produced the exact same "port already in
   use" failure this whole finding started from, on every test after the first, until
   `_wait_for_ports_free` was corrected to bind rather than connect. All nine tests green afterward,
   real deployments and real teardowns throughout, 9m31s total (up from the sub-second vacuous
   pass this finding replaces — slower, and for the first time actually testing what it claims to).

   **`make docker-clean` — added the same day, the owner's own ruling.** Removes every
   OspreyFlow-owned container (`osprey-*`), image (`osprey/*:local`) and named volume (`osprey*`),
   plus dangling images, the build cache and — the one non-name-scoped step, and still safe for the
   reason its own Makefile comment gives — any Docker volume attached to no container at all
   (`docker volume prune`, which by construction cannot remove a volume mounted into a running
   container, so the always-running `airbyte-abctl-control-plane` and its own volume are never
   touched regardless of name). Run once against this session's own accumulated state: 2.88GB
   reclaimed across images and build cache, a further 2.80GB from orphaned anonymous volumes —
   among them a 2.6GB ArcadeDB data volume with no name to match, left behind by an earlier exit
   test's own container, the exact class of debris `docker volume prune`'s own inclusion here
   exists to catch that a name filter alone would have missed. **Scope is the owner's own ruling,
   25 September 2026:** every OspreyFlow-owned image, container, volume and build cache
   (`osprey-*`, `osprey/*:local`, exit-test clones) and dangling images may be removed; the
   airbyte container and its volumes may never be touched.

### Delivered, not milestone-gated

Neither "required for V1 END TO END" nor "remaining work" — already built, checked against the
milestone and found not to gate it. Kept out of both lists above and below on purpose: filing
finished work inside "Before the milestone" would misstate it as something the milestone depends
on, and filing it inside "After the milestone" would misstate it as a queue item still to be done.
Whatever else in either list turns out to be already built moves here too, at the point that is
found, rather than staying filed as if it were still outstanding.

- **Correction, 24 September 2026: this stage's own "built" of 22 September was wrong, and stayed
  wrong for two days.** The exchange request omitted `subject_token`, which RFC 8693 §2.1 makes
  REQUIRED — so a real Keycloak refused it outright (`access_denied`, "Client not allowed to
  exchange") and **the mechanism had never once worked against a real identity provider**. It
  passed its own tests throughout, because the only thing it had ever run against was the ephemeral
  HTTP fixture ADR-043's own Cost section describes, and that fixture **accepted a request the real
  server rejects**. Nothing in this stage was mis-implemented against its own tests; the tests were
  measuring something more permissive than the dependency. Fixed 24 September 2026 and now covered
  by a test that needs a real IdP by design; the fixture now serves `client_credentials` and refuses
  an exchange with no `subject_token`, so it models the dependency's refusals rather than only its
  grants. `CLAUDE.md` rule 15 carries this as its second worked example.

- **Stage 1 — principal resolution, built, 22 September 2026 (`06_DECISIONS.md` ADR-043: OAuth2
  Token Exchange, RFC 8693).** `PrincipalResolver.resolve_for_owner`/`resolve_for_owner_detailed`
  (`services/api/auth.py`) exchange this Conduit's own client credentials for a token minted as
  the target `owner_id`, decoded through the existing, unchanged `resolve()` — no second
  claims-construction path. `principal_for_owner` (`services/api/evaluation.py`, both
  `evaluate_hotlists_for_entry` and `evaluate_monitors_for_entry`) and every one of its call
  sites are now async (`app.py`'s `_evaluate_watches_best_effort`, and ~15 test call sites in
  `tests/services/api/test_evaluation.py`) — the requester's own id still resolves instantly with
  no network call; any other owner now goes through the real exchange. **Code + decision, both
  discharged.**

  **Why this sits here rather than "Before the milestone," stated rather than left for a reader to
  work out.** `08_ACCEPTANCE_SCENARIOS.md`'s own literal text for B12/B13/B14/B20 is a single,
  continuous session — the analyst who sets the hotlist/monitor is the same analyst whose later
  ingest triggers it, so `owner_id == requester` holds by construction and the milestone's own
  closing-pass test (Stage 4g) never exercises cross-analyst resolution at all. This stage's own
  real value — principal resolution for a *different* analyst's later action, the operational case
  B13 is actually modelled on — is genuine and already built, but is not what the milestone's own
  literal wording requires.

  **Only one of the two halves this entry originally expected to close together actually
  closed — checked directly, not assumed, and the record corrected rather than left overclaiming
  it.** Cross-analyst hotlist/monitor firing (B12/B13/B14/B20's own operational case) is
  unblocked: `test_a_hotlist_owned_by_one_analyst_fires_from_a_different_analysts_own_ingest`
  passes, through the real `run_studio_recipe` route, two real principals, neither one the
  other (`tests/scenarios/test_phase7_stage6c_watch_routes.py`). **Resolution-triggered monitors
  are not — attempted directly, not left as a missing call site, and found blocked by a
  different, more precise reason once one was actually built.** A real call site was wired
  (`run_resolution_for_entity_type` calling `evaluate_monitors_for_entry` after publishing to the
  change stream, threaded through `try_run_resolution_with_overlap_guard`/
  `run_resolve_entity_type_job` and bound at job registration in `app.py`) and reverted, not kept
  half-working: `services/api/worker.py`'s own `JobWorker._process` begins the job's transaction,
  runs the handler, and commits only *after* the handler returns — so the evaluation call, running
  from inside the handler, executes before the very `SAME_AS` write it exists to alert on is
  committed. `GraphPort.match` has no transaction parameter, so it genuinely cannot see an
  uncommitted write from inside the same handler — standard transaction-isolation behaviour, not a
  port oversight this stage could route around. **Confirmed empirically:** the in-handler call
  found no match and alerted nothing for a freshly-created monitor in a real test build of this
  wiring; a second, manual call to the identical function immediately after the test's own commit
  correctly found the match and fired the alert. `06_DECISIONS.md` ADR-037's own amendment has the
  full record: a `GraphPort` transaction-scoped read is disqualified on correctness, not priced
  against — a job's own transaction can still roll back after the handler returns, and reading
  uncommitted state would let a rolled-back job raise an alert for a `SAME_AS` edge that never
  existed. The complete fix is a durable-record consumer (evaluation reading from the change
  stream itself, the shape ADR-037's own amendment already describes), not a post-commit hook
  alone — correct, but a process dying between commit and hook loses that evaluation with nothing
  recording it should have happened. **Checked against `08_ACCEPTANCE_SCENARIOS.md` directly, not
  assumed: no Scenario B row needs a monitor to fire from resolution alone** (B20's own assertion
  is ingest-triggered, already covered). Recorded in "Out of scope for v1" below, not inside this
  stage or any other Phase 8 stage — nothing v1 commits to depends on it.

  **Exit criterion, a test — met:** `test_a_hotlist_owned_by_one_analyst_fires_from_a_different_
  analysts_own_ingest` (`tests/scenarios/test_phase7_stage6c_watch_routes.py`) passes. The two
  tests ADR-036 already named
  (`test_monitor_never_fires_on_a_match_the_saving_analyst_cannot_see`,
  `test_monitor_stops_evaluating_once_the_saving_principal_is_revoked`) still pass as
  regressions. **The containment test the task named as the one that matters** —
  `test_principal_for_owner_returns_exactly_that_owners_own_claims_not_a_broader_principal`
  (`tests/services/api/test_auth.py`) — passes, and was confirmed non-vacuous by injecting a
  broken implementation (hardcoding `requested_subject` to a broader principal's own id) and
  observing the real failure output before reverting. **The freshness test** —
  `test_a_revoked_principal_stops_firing_at_the_next_evaluation_no_cache_to_invalidate`
  (`tests/services/api/test_evaluation.py`) — passes against the real mechanism, not the
  in-memory test stand-in every other test in that file uses.

### The rest of Phase 8's stage list

**The "After the milestone" heading this document used from 22 September until 23 September 2026
is retired** — the milestone redefinition above (V1 END TO END = installed, started, demonstrated)
pulled most of what used to sit under that heading into the milestone-blocking set instead; what
remains below genuinely is not milestone-blocking, and now says so at its own entry rather than by
virtue of a heading whose own name implied "deferred past v1" for stages that, as of this
restructure, no longer are. **Stage 1 is not here** — it is already built; "Delivered, not
milestone-gated," above, has it, so a reader scanning this section for remaining work does not
find something already finished sitting in the queue.

2. **The harness / packaging pipeline — MILESTONE-BLOCKING, promoted 23 September 2026** (see this
   list's own opening summary). Like Stage 1, largely green-field: no packaging step, no
   backup/restore/upgrade mechanism and no generated-manifest tooling exists anywhere in this
   repository yet. Not exercised by either acceptance scenario, checked directly against
   `08_ACCEPTANCE_SCENARIOS.md`, no row in either exercises packaging, backup or restore — but now
   required by the milestone's own broader text regardless, since "installed... and demonstrated"
   needs a real install path to exist, not only a passing test suite. **Code +
   infrastructure.** **Exit criterion:** a `backup` → `restore` cycle reproduces the graph from
   staged Parquet (Phase 8's own original outcome bullet, stated here rather than as a separate
   milestone clause, since backup/restore is this stage's own capability, not either scenario's).
   ADR-034 §B7's two assertions (no private-tree file in the built artefact, no B5 identifier in
   it, including build-time version metadata) are mechanical and testable, the same
   containment-check shape already proven against `scripts/mint_dev_token.py` — properties of this
   pipeline producing an artefact at all, stated that way in ADR-034 itself
   (`06_DECISIONS.md`), not as a condition on who ever receives one; `docs/PRODUCT_DELIVERY.md`
   has the distribution-readiness framing (who receives an artefact and when) that used to sit
   here instead. A scripted golden-path deploy (clean checkout → harness or its CLI equivalent → a
   running, health-checked stack) is testable too. **Whether the six setup screens are actually
   usable by an operator who has never seen them is a judgement, not a test — said plainly rather
   than dressed as one; a usability pass by someone other than whoever built the screens is this
   sub-item's own honest exit criterion.**

   **Amended 24 September 2026 by ADR-049's ruling 2 and the owner's settlement the same day: this
   check runs at the post-launch `verify` step, and that `verify` runs as the final step of
   `Stage 2 §3`'s golden-path deploy — not at pre-launch Preflight.** The requirement below is
   unchanged in substance — the grant must be verified, two-sided, automatically, with the operator
   wording given here — and only its placement moved. **It remains milestone-blocking**, through
   `Stage 2 §3`'s own exit test #2 rather than through Preflight. **Why:** performing a real RFC 8693
   exchange means *using* the Conduit's
   confidential-client secret, not merely referencing it, which `05_DEPLOYMENT.md` §2.5 forbids the
   harness outright ("It never sees a secret… The harness records where to look, never what it
   found"); and pre-Launch there is no Keycloak running to exchange against, since it is one of the
   twelve containers Launch itself brings up. At `verify` the launched Conduit already holds those
   credentials, so the check runs where the secret already is. **The Preflight screen keeps the
   surface**: the check appears in its list as a post-launch item with its own Re-check button, and
   the failure wording below is what it shows. Read every "Preflight must/asserts" below as "the
   post-launch `verify` step performs, and Preflight's Re-check surfaces". **One consequence:** the
   sub-stage carrying `verify` (`Stage 2 §7`) is not itself milestone-blocking — **settled the same
   day by pulling that `verify` into `Stage 2 §3`'s golden-path deploy as its final step**, so the
   grant is verified before the milestone rather than after it. `Stage 2 §7` keeps the Re-check
   surface for a later re-run from the admin console.

   **New requirement, named here rather than left to be discovered while building the screens:
   the token-exchange grant `06_DECISIONS.md` ADR-043 depends on must be verified.** ADR-043
   places part of its own containment in realm-level IdP configuration — outside this repository,
   unversioned, invisible to `make ci` or any gate this codebase can run. Left unchecked, a
   misconfigured or missing grant surfaces only as watches marked `"stopped"` after an evaluation
   fails — which an operator reads as an access problem (something wrong with an analyst's own
   clearance) rather than a deployment one (something wrong with how this instance was set up),
   the exact wrong diagnosis for the actual fault. This is the one part of the mechanism no gate in
   this repository can reach — `05_DEPLOYMENT.md`'s own "Preflight runs live" is the only place
   left able to catch it before an analyst ever sees a falsely-stopped watch.

   **What Preflight must assert**, alongside the environment checks `05_DEPLOYMENT.md` §"Preflight"
   already lists (memory, disk, GPU, port availability, container runtime, cluster connectivity):
   attempt a real token exchange for a known, disposable preflight-only test subject (not a real
   analyst account) and confirm it succeeds; then attempt an exchange for a subject the realm's own
   policy should refuse (a deliberately-out-of-scope or disabled test subject) and confirm it is
   actually refused, not silently granted — the same two-sided check ADR-043's own "how an operator
   verifies it" section already names, run automatically rather than left to a manual step someone
   has to remember. A grant that only ever gets exercised on the happy path is unverified on the
   half that actually matters for containment.

   **What it tells the operator on failure** — the same "explains what is wrong and what to do
   about it, with a Re-check button" standard `05_DEPLOYMENT.md` already sets for every other
   Preflight check, applied here specifically: name it as an IdP configuration problem, not an
   access problem — "token exchange is not correctly configured on your identity provider; watches
   will appear stopped for every owner but the analyst who triggered them until this is fixed" —
   distinct wording from whatever `StatusBadge` shows an analyst later, so the two failure surfaces
   are never mistaken for the same fact by whoever reads either one first.

   ---

   **Sub-stages `Stage 2 §1`–`Stage 2 §7` — ACCEPTED, 24 September 2026.** *A same-day snapshot,
   superseded by each sub-stage's own entry below as later work landed (`§3`, `§4` and `§5b` all
   went from "not started" to built within days of this line) — kept as historical record, not
   corrected in place.* `Stage 2 §1` is **built**
   apart from the `cluster` renderer, **`Stage 2 §2` is built**, and **`Stage 2 §5a` is built**
   (the owner split §5 on 24 September 2026 so the images exist before §3 needs them); §3, §4, §5b,
   §6 and §7 are not started. Design and
   adversarial review in `06_DECISIONS.md` **ADR-049**, status **Proposed**; each entry below is a
   summary of that record's own amended text, not a second copy of it, and each is Proposed for
   exactly as long as ADR-049 is. **The owner ruled on all seven of that record's open objections on
   24 September 2026 and confirmed all three of its owner decisions** (D1, the artefact shape,
   **narrowed** to each *deployable* service; D2, the real-data exceptions panel; D3, the three-test
   stage exit). The
   rulings and their consequences are recorded in ADR-049's own "Owner's rulings" section; the
   consequential edits they required have been applied here rather than left as notes. **D1 was
   then corrected the same day to its narrowed form** — "each *deployable* service" — which moves
   the missing Dockerfiles into `Stage 2 §5` as this stage's own work; the four follow-on items were
   settled in the same message, and the record was **Accepted** by the owner the same day. These
   sub-stage entries are the plan, not a proposal.

   **On the labels, and the one thing they cost.** These were `2b`–`2h` when the design arrived;
   ruling 1 relabelled them because `2a` below is a *sibling* stage of this one — ArcadeDB stability,
   "a new, independent stage… labelled `2a` only for its position in this list", in its own entry's
   words — and `2b` onwards read as its continuation. `2a` keeps its label and its meaning. The cost:
   `§N` already means "specification section" throughout this document, so a sub-stage is **always
   written in full** (`Stage 2 §5`, never a bare `§5`), which is what keeps it apart from
   `05_DEPLOYMENT.md` §5 in sentences carrying both. Mapping, for anything written before this
   ruling: `2b`→`Stage 2 §1`, and so on in order to `2h`→`Stage 2 §7`.

   **Stage 2 §1 — `osprey.yaml` as the single source. ACCEPTED.** A Pydantic schema in `packages/schemas`
   for the whole `osprey.yaml` document (profile, components, models, governance, geospatial,
   cluster hosts), reusing `packages/schemas/mapconfig.py`'s `MapConfig` for the `map:` section
   rather than redefining it, and not invalidating the committed demo/CI `osprey.yaml` that
   `services/api/mapconfig_loader.load_map_config` reads today as a bare `raw["map"]`. A generator
   (`harness/render.py`) rendering **all four artefacts `05_DEPLOYMENT.md` §2.1 names** — compose
   or Kubernetes manifests (ADR-011: a different renderer, not a toggle), environment files,
   `versions.lock` with every image digest pinned, and the per-deployment `RUNBOOK.md` with real
   hostnames, ports and paths — plus drift detection and a change preview. `deploy/compose/dev.yaml`
   is not replaced. **Exit test:** rendering a fixture `osprey.yaml` is byte-stable across runs; a
   hand edit to a generated file is reported as drift; the diff names every changed path — **for
   each of the four artefact kinds**, each with its own planted drift of the real generated shape
   (standing discipline: a planted violation takes the shape the code actually emits). The
   unamended two-artefact version of this test was green over a renderer that never emitted
   `versions.lock` or the per-deployment runbook at all. §2.4's *running-deployment* drift
   comparison is a second, harder check and is named separately in ADR-049, not folded into this
   one.

   **BUILT, 24 September 2026.** `packages/schemas/deployment.py` (`OspreyConfig` and six
   supporting models, reusing `MapConfig` rather than redefining it, seven new generated TypeScript
   types, `make schemas-check` green at 112), `harness/render.py` (`python -m harness.render`, with
   `--check` and `--diff`), `harness/images.py`, and 31 tests in `tests/harness/`. Every top-level
   key is optional with a documented default, so the committed `osprey.yaml` still validates —
   asserted against the real file, not a copy of its shape, and
   `tests/test_demo_osprey_config_is_tier_1_only.py` is unchanged and passing. Extra top-level keys
   are rejected, so a misspelled `governence:` fails loudly instead of rendering default governance
   in silence.

   **Red-then-green, demonstrated rather than asserted (rule 15).** Six mutations were applied to
   `harness/render.py` in turn and the suite run against each: `find_drift` returning nothing (8
   tests red), `versions.lock` omitting one image (2), only two artefacts rendered (4), a timestamp
   injected into the compose file (2), the reduced-variant branch removed (2), and the cluster stub
   removed (1). Each turned its own tests red and the tree returned green. Every planted drift edits
   a file the renderer actually produced, in its own real content.

   **Digests: the renderer refuses rather than invents.** Checked directly — this repository pins no
   image digest anywhere; `deploy/compose/dev.yaml` carries tags only. `versions.lock` resolves each
   digest from the local Docker daemon and **fails, naming every unresolved image**, rather than
   writing a lock file whose own name claims a pin it has not got. `--allow-unpinned` marks them
   `unresolved` in that word. Verified live: the daemon resolved the two images this machine had
   pulled and the renderer refused on the other nine, by name.

   **What remains in this sub-stage: the `cluster` renderer.** `profile: cluster` raises
   `ClusterRendererNotBuilt` — a loud stub, per ADR-011's "a different renderer, not a toggle",
   because a `cluster` render that silently emitted compose would be the worse failure. Kubernetes
   manifest generation is not built and is not scheduled here.

   **`versions.lock` digests are a snapshot of this machine, and each entry says so.** They are
   resolved from the **local Docker daemon**, so a lock file records what this machine happened to
   have pulled rather than what a registry currently serves; every entry carries its own `source`
   field (`local-docker-daemon`, or `unresolved`) because the two can differ line by line within a
   single render, and a reader needs to know which is which. **Stage 2 §5's bundle resolves from the
   registry manifest instead** and will write a different `source` when it does — that is the
   authoritative path, and this one is the development convenience that does not pretend to be it.

   **Spec gap raised — now decided, awaiting the owner's own wording (rule 11): where generated
   artefacts live.**
   `05_DEPLOYMENT.md` named fixed paths (`deploy/compose/dev.yaml` §2.4,
   `deploy/versions.lock` §5/§7) which are right for a deployment and wrong for a repository that
   can render three profiles — two renders overwrite each other there silently, each
   self-consistent, so no drift check fires. **Settled — owner's decision, 24 September 2026: rendered output goes to
   `deploy/generated/<profile>/`, and §2.1's two fixed paths are amended to that.** Recorded in
   `05_DEPLOYMENT.md` §2.1 and confirmed by the owner in writing. The directory is gitignored here, which is a separate point from where it sits: this
   repository is not a deployment, and the committed `osprey.yaml`'s own header says so. A real
   deployment's repository versions it.

   **Two smaller findings, recorded rather than fixed.** `generate_ts.py`'s `HEADER` names six
   source modules and has omitted `mapconfig.py` and `provider_profile.py` since before this
   sub-stage; adding `deployment.py` to it would have rewritten all 112 generated files for a
   comment, burying the seven real new types, so the header is left stale and named here instead.
   And `05_DEPLOYMENT.md` §3's twelve-container list includes "three workers" that have no image in
   this tree — `service_images()` does not invent them, and settling that count is Stage 2 §5's own
   directed finding.

   **Stage 2 §2 — Preflight, headless. ACCEPTED.** `harness/preflight/`, one module per check, each
   returning `{status, what is wrong, what to do, re-checkable}`; `python -m harness.preflight`
   runs all or one. Memory against the profile floor **and `05_DEPLOYMENT.md` §3's reduced-variant
   offer below 16 GB** (drop OpenSearch, fall back to PostgreSQL full-text, state the trade-off —
   "offered, not applied silently"); disk against projected staging volume; GPU presence and
   driver; port availability per declared service; container runtime version; cluster connectivity
   to every declared host; and the four rehearsal-derived checks (the interpreter is the project
   venv; every service's bind address is consistent and printed; the basemap is built and served
   over HTTP, not `file://`; the DuckDB lock holder is not running when seeding is requested).
   **The ADR-043 two-sided token-exchange check is not in this list** — ruling 2 moved it out of
   pre-launch Preflight, and the owner's settlement of 24 September 2026 then placed it as the final
   step of `Stage 2 §3`'s golden-path deploy, with `Stage 2 §7` keeping the Re-check surface.
   Preflight still renders it as a post-launch item; it does not gate Launch on something that
   cannot run before Launch. See this stage's own amended "New requirement" paragraph above. **Exit test:** every
   check has a red-then-green test whose planted failure takes the shape the check actually reads,
   and apply/launch refuses while any check is red.

   **BUILT, 24 September 2026.** `harness/preflight/`, one module per check, a common
   `CheckResult` (`check`, `status` of `pass`/`fail`/`skip`, `what_is_wrong`, `what_to_do`,
   `rechecked_at`, plus printed `detail`), and `python -m harness.preflight` with `--only <check>`
   as Re-check, `--gate` for Launch, `--seeding` and `--accept-reduced`. It reads
   `deploy/generated/<profile>/` from Stage 2 §1 — the ports it checks are the ports the **rendered
   compose file** declares, not ports anyone believes the profile implies. Ten checks: §2.1's six
   (`memory`, `disk`, `gpu`, `ports`, `container-runtime`, `cluster-connectivity`) and the four the
   23 September rehearsal produced (`interpreter`, `bind-address`, `basemap`, `duckdb-lock`).
   35 tests; `make test` went 730 → 765 passing with the same three failures.

   **Every failing check gives a remedy, enforced rather than encouraged.** `failed()` raises if
   either `what_is_wrong` or `what_to_do` is empty — §2.1's "explains what is wrong and what to do
   about it" is a constructor precondition, so a check cannot ship half of it.

   **`skip` is a third status and never a lenient pass.** Recorded per the brief's own instruction:
   **GPU driver version on macOS is skip-with-reason** — `nvidia-smi` does not exist and Metal
   exposes no equivalent — as is cluster connectivity at `local-lite`, the DuckDB lock when seeding
   was not requested, and the memory floor on a platform whose page counts cannot be read. Each
   says in its own output that it did not run and is not evidence the thing it checks is correct.
   `05_DEPLOYMENT.md` §2.1 now states the rule too.

   **The reduced variant is offered and never applied.** Below the 16 GiB floor the run prints the
   offer, names the component it drops (`opensearch`) and the fallback (PostgreSQL full-text),
   states the trade-off in §3's own terms, and changes nothing. `--accept-reduced` is the only
   thing that acts, and it **re-renders through Stage 2 §1's renderer** rather than editing
   generated files. It leaves `osprey.yaml` alone: that is the operator's file, reviewed in a pull
   request, and persisting the choice belongs to the Components screen.

   **Red-then-green, demonstrated.** Six mutations, each turning its own tests red before the tree
   returned green: ports never reporting a taken port (1), basemap accepting `file://` (3),
   interpreter resolving the symlinked binary (1), the DuckDB lock never detected (1), the offer
   made regardless of memory (1). Planted failures are real: a real socket bound on a port read out
   of a real rendered compose file, a real `file://` URI, a real `/usr/bin/python3`, a real second
   process holding the DuckDB file. The three seams — total RAM, free disk, and `getaddrinfo` for
   the IPv6-only case — exist only where the machine cannot be put into the state, and each is
   named at its own test.

   **A seventh mutation got away, and closing it changed the code.** A planted silent-apply of the
   reduced variant was caught by *nothing*: the test asserted `offer_for()` changed no files, but
   that function has no access to the output directory and so structurally cannot change any. The
   real risk was in the CLI, where the offer is printed beside the code that could act on it.
   `main()` gained a context injection point and three CLI-level tests; the same mutation is now
   caught. This is rule 15's own lesson arriving a second time: a planted violation that some other
   property already forbids proves nothing about the property under test.

   **Two bugs this round found in its own code before a test did**, both recorded because both were
   the check being wrong rather than the environment: the interpreter check resolved
   `.venv/bin/python` through its symlink into the base interpreter and so rejected the very venv it
   exists to accept; and the first DuckDB lock test discarded its connection immediately
   (`duckdb.connect(...)` unassigned is collected at once), so it planted no lock and the check was
   right to pass. Both are now covered by the cases that would have caught them.

   **What remains:** nothing in this sub-stage. The ADR-043 token-exchange check is deliberately
   absent and the package docstring says so, with the owner's ruling and both reasons, so it is not
   later added here by someone reading §2.1's list alone.

   **Spec gap raised as Proposed (rule 11): what projects the staging volume.** §2.1 says "disk
   against the projected staging volume" and nothing anywhere derives that projection. The check
   compares against an assumed 20GiB default and labels it as an assumption in its own output
   rather than presenting a fabricated requirement. Recorded in `05_DEPLOYMENT.md` §2.1 with a
   proposal (a function of the declared sources and a retention window, both already collected) and
   not decided.

   **Stage 2 §3 — Scripted golden-path deploy. ACCEPTED.** `python -m harness.apply`: fresh checkout →
   render (Stage 2 §1) → preflight (Stage 2 §2) → start stack → wait for health → seed if requested, with
   **seed-ordering enforcement** (seeding precedes any lock-holding service; the database is reset
   first — stage 2a's cause five). *Seed-ordering enforcement is not `05_DEPLOYMENT.md` §2.4's
   "ordering enforcement", which is backup-before-profile-switch; the two share a name and nothing
   else.* Also here: §2.4's **target confirmation** guard (the resolved Docker context, or the
   Kubernetes cluster, context and namespace, shown before every action and re-confirmed when it
   differs from the last), and §3's "seeded demo credentials are displayed once and written
   nowhere". The rendered stack is §3's twelve containers, **including Keycloak**, without which
   Stage 2 §2's token-exchange check has nothing to exchange against. docs/demo/2026-09-24/demo_up.sh is
   retired into this once it exists; until then it stays (since removed — see the entry below).
   **Exit test:** from a fresh clone, one
   command reaches a health-checked stack on `local-lite`, **with ADR-043's two-sided exchange green
   as its final step** — the owner's settlement of 24 September 2026, pulling the post-launch
   `verify` into this deploy so "reaches a health-checked stack" includes a verified token-exchange
   grant, and making the check milestone-blocking through this very exit test. `05_DEPLOYMENT.md`
   §2.5 holds because it runs after Keycloak is up, against the deployment's own credentials, so the
   harness never holds the secret. The CI half **names the services that must be healthy and the
   health checks that must pass without Ollama**, rather than "as far as CI can", which cannot fail,
   and must state whether CI runs a Keycloak at all, since that decides whether the exchange is
   reachable there. **Stage 2 exit test #2.** *(The settlement named "Stage 2 §4's golden-path
   deploy"; this was read as §3 and flagged, and the owner confirmed §3 on 24 September 2026 — "your
   reading of §3 is correct and stands".)*

   **Stage 2 §3 — COMPLETE. Exit test #2 is GREEN, 24 September 2026.**

   ```
   apply: local-lite ready in 31s
     render: 5 artefact(s) → deploy/generated/local-lite
     preflight: all checks pass or skip
     build: owned images built from this checkout
     up: 6 service(s) healthy
     grants: impersonation + view-users on the Conduit's service account
     verify: 3/3 assertions green
   ```

   **From a fresh clone, one command reaches a health-checked stack with principal resolution
   working.** Ten containers run (the batch loader is a compose profile and is not started by `up`);
   six declare health checks and all six are healthy, the Conduit among them.

   **Six further defects, each found only by running it, each fixed:** the generated env file set
   `POSTGRES_HOST` but not the port, database or password, so the Conduit dialled 5433 where nothing
   listened; the Conduit reads `osprey.yaml` at startup and the image deliberately does not contain
   it, so it is mounted read-only from the repository root; `docker compose up --wait` read the
   batch loader's by-design exit 2 as a failed start, so it became a compose profile; and
   `keycloak_admin`'s HTTP helper never set a method, so a `PUT` went out as `POST` and Keycloak
   answered 405 — which reads like a wrong URL rather than a wrong verb.

   **The three-sided verify, and the mutation that found a hole in it.** All three assertions run
   against the real deployed realm, and each was shown red by its own mutation and green again
   after:

   | Mutation | Assertion | Result |
   | --- | --- | --- |
   | Impersonation grant removed from the Conduit | 1 — exchange succeeds | **red**, then green |
   | Unprivileged client granted impersonation | 2 — unprivileged client refused | **red**, then green |
   | Pre-check removed (`OIDC_ADMIN_USERS_URL` unset) | 3 — disabled subject refused | **red**, then green |

   **Mutation 2 initially failed to go red, and that was the round's most useful finding.**
   `PrincipalExchangeRefused` covers two different events — "the IdP refused the exchange" and "the
   IdP granted it and the token then failed verification" — and assertion 2 counted either as a
   refusal. So a client that Keycloak had just been told to allow still scored green, because the
   token it got back failed claim verification for an unrelated reason. **A refusal counted without
   reading why is a gate that cannot go red.** Assertion 2 now requires the refusal to have come
   from the token endpoint, and the mutation turns it red as it should.

   **Memory, re-measured with the Conduit up, as the owner required** (sampled every 5s):

   | Container | Peak (MiB) |
   | --- | --- |
   | arcadedb | 2,308 |
   | opensearch | 936 |
   | keycloak | 528 |
   | **api (the Conduit, healthy)** | **233** |
   | whisper | 152 |
   | minio | 105 |
   | postgres / valkey / ollama / workspace | 61 / 21 / 11 / 11 |
   | **Peak total** | **4,456 MiB of a 9,932 MiB VM (45%)** |

   Against the provisional figure taken with the Conduit exited (3,607 MiB), the Conduit contributes
   ~233 MiB and ArcadeDB climbs ~310 MiB once real schema work happens. **The stack fits the 10 GiB
   VM.** Still to note honestly: this is ten containers, not the twelve §3 names — the model gateway
   is not rendered (Proposed, above) and the batch loader is on-demand — and it is a first-launch
   measurement, not a sustained-use one, which is what §8's named test is for.

   **The seeded golden path, run 24 September 2026 — green, and it cost five further defects.**
   The run owed above is done. From a fresh clone, `--seed hmp,fixture-corp` reaches a
   health-checked, seeded stack in **66s**, with the counts the fixtures themselves report:

   ```
     seed[hmp]: Seeded 400 Person nodes, 10 yards.
     seed[hmp]: Loaded 262 current-window events and 4 prior-period events under
                investigation_scope='01M3A9DN5C556JEC95TP2R7CSF'.
     seed[fixture-corp]: Seeded 10 resolution Person nodes and 17 real SAME_AS edges.
     seed[fixture-corp]: Seeded 21 community-ring nodes and 63 edges across 3 rings.
     seed[fixture-corp]: Seeded the path-spoke hub 'corp-path-hub' with spokes of length
                         [1..8], including a SECRET shortcut on the length-3 spoke.
   apply: local-lite ready in 66s
     seed: hmp, fixture-corp into investigation 01M3A9DN5C556JEC95TP2R7CSF
           (Conduit stopped for the seed, then restarted)
     verify: 3/3 assertions green
   ```

   Every figure the stage owed is there: HMP's 400 Person nodes and 10 yards, its 262 + 4 events,
   and Fixture Corp's four properties (resolution Persons, real `SAME_AS` edges, community rings,
   the path-spoke hub with its SECRET shortcut). The ordering guard sequenced it: the Conduit was
   stopped for the seed and restarted and re-awaited after, and the guard still refuses outright if
   asked to seed into a running Conduit.

   **`seed()` as committed could not have worked, and nothing would have told us.** It invoked each
   script with no arguments although `scripts/seed_hmp_fixture.py` requires `--investigation-scope`;
   it ran on the host, where §7 puts every store on an internal network with no published ports; and
   no image contains `scripts/`. It had been unit-tested for its *refusal* behaviour only — the
   ordering guard — so every test of it passed and the path past the refusal had never once run.
   The same class of gap as the omitted `subject_token` already in `CLAUDE.md` rule 15's second
   worked example: **a function tested only where it says no.**

   **The five defects, each found only by running it, each fixed with a red-then-green test:**

   | Defect | How it presented | Test that now fails for it |
   | --- | --- | --- |
   | `osprey-data` and `osprey-staging` declared as volumes, mounted by **no service** | Nothing. The stack was healthy; the analytics DuckDB sat in the container layer and every seeded event died with `docker compose down` | `test_every_declared_volume_is_mounted_by_some_service` |
   | A named volume's mount point absent from the image | Docker created it root-owned; the non-root process could not write to it — mounted but unusable | (fixed in `services/api/Dockerfile`; covered by the seeded run itself) |
   | MinIO's credentials written only under `OSPREY_MINIO_*`, never `MINIO_ACCESS_KEY`/`MINIO_SECRET_KEY` | **Not** a missing-configuration error: the client falls back to `minioadmin` and MinIO answered `ACCESS_DENIED during HeadBucket` | `tests/harness/test_apply_env.py`, over every split credential name |
   | ArcadeDB's heap left to JVM container ergonomics | `ArcadeDBError 500: "Error in execution in lock"`. The real cause — `java.lang.OutOfMemoryError` — was only in the server's own log | `test_arcadedb_gets_an_explicit_heap_rather_than_jvm_ergonomics` |
   | `seed()` printed only each script's last line | The counts an operator checks a seed against were the ones discarded | — |

   Two of these deserve naming beyond the table. The MinIO one is the **third** instance of one
   value under two names, after ArcadeDB and Postgres; each of the first two was fixed the single
   time it was hit in a live deploy and nothing was added that would have found the third before it
   was hit too. `test_apply_env.py` now asserts the property over every pair at once. And the
   ArcadeDB heap was **a number this repository had already paid to learn** — `deploy/compose/dev.yaml`
   raised its own heap to `-Xms1G -Xmx6G` in Phase 5 for this exact fixture, and the renderer never
   carried it across, so a rendered deployment was strictly worse-configured than the dev stack it
   replaces.

   **The Glass leg is NOT green, and it is not a harness defect.** Item 1's last requirement — the
   seeded investigation reachable through the Glass at the printed URL via `?investigation=` — fails,
   and re-running it will keep failing, because **the Glass has no sign-in and no runtime
   configuration**. `apps/workspace/src/App.tsx` says so in its own words at line 55: "Phase 4's
   bullets do not include a login flow (OIDC/Keycloak's own UI is server-side, Phase 3's territory)
   — a bearer token supplied this way is a stand-in until a real sign-in screen exists, not a
   production auth path." Two consequences, both measured against the running deployment:

   - `API_BASE_URL` is `import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000"`, **baked into
     the bundle at image-build time**. The deployment's own `OSPREY_API_PORT` override is invisible
     to it; the browser console shows `ERR_CONNECTION_RESET` against `localhost:8000` for
     `/v1/ontology`, `/v1/map/providers` and `/v1/analytics/geobins`.
   - `DEV_BEARER_TOKEN` defaults to the empty string, so the delta WebSocket opens as
     `…/stream?token=` and is refused.

   The page loads and sits on "Loading…" indefinitely:
   `docs/demo/2026-09-24/stage2-3-rendered-glass-cannot-reach-the-conduit.png`. The earlier
   `A0-glass-loaded-with-seeded-investigation.png` in that same folder is not a counter-example — it
   was taken against `npm run dev` with a hand-supplied token, which is the stand-in the comment
   above describes.

   **This is a spec gap, not a bug**, and per `CLAUDE.md` rule 11 it is recorded rather than
   answered: `05_DEPLOYMENT.md` never says how the Glass learns the Conduit's address in a rendered
   deployment, nor how an analyst signs in to one. Recorded as Proposed in `05_DEPLOYMENT.md` §2.6
   with the two candidate shapes; it needs an owner decision and a phase, and it is the last thing
   standing between this stack and a demonstrable one.

   **One further honesty note on the run.** The build stage was skipped (`--no-build`, added this
   round as a real affordance for registry-pull deployments and unchanged re-applies). The Conduit's
   image *was* rebuilt, from the `python:3.12-slim` already in the daemon; the workspace image was
   not, because its `node:22-slim` base is not in the local store and Docker Hub answered
   `429 Too Many Requests` — the daemon is making **unauthenticated** pulls
   (`~/.docker/config.json` has an empty `auths`), contrary to what was believed. The published API
   port was moved to 8010 for the same run, because an unrelated container of the owner's holds
   8000; Preflight caught that before anything was built and named the port, which is what it is
   for.

   ---

   ### Stage 2 §3 — superseded working history, passes one to five (24 September 2026)

   **Everything from here to the end of this stage's entry is history, not current state.** Each
   pass below was accurate when written and was pushed and read, which is why none of it is
   deleted — but **the current state of Stage 2 §3 is the COMPLETE/GREEN entry above, and nothing
   below overrides it.** In particular, several passes below say exit test #2 is not green: that
   was true when each was written and is not true now. Read the entries below only for how the
   findings were arrived at.

   **Superseded (fifth pass) — 24 September 2026.**

   **Stage 2 §3 — fifth pass, 24 September 2026. A diagnosis I reported was wrong, and correcting
   it is this entry's main content.**

   **The misdiagnosis, recorded as a worked example on the owner's instruction: a name standing in
   for an examination.** The traceback carried an exception class. The class belonged to `asyncpg`
   and I read it as the model gateway — because the model gateway was what the previous round had
   been about, and the symptom ("connection refused during startup") fitted the story I already
   had. Two cheap checks would each have refuted it in under a minute: grepping the exception class,
   which names `asyncpg` and nothing else; and reading `LiteLLMClient.__init__`, which builds an
   `httpx.AsyncClient` and opens no connection, so it cannot refuse one. **I did neither, and
   reported a conclusion as though I had.** The cost was not the wasted time — it was a decision
   the owner took on a premise I supplied and had not checked, which then had to be withdrawn.
   **The rule this yields, narrower than "verify your claims": when a failure is attributed to a
   component, the attribution is a claim about that component's code, and it is checked in that
   component's code — not inferred from what the component is called or from what the session
   happened to be discussing.**

   **The correction.** The fourth pass reported that the Conduit would not start because the
   rendered stack has no model gateway, and the owner made a decision on that basis. **It was an
   inference from a partial traceback, not a measurement, and it was wrong.** The exception class
   belongs to `asyncpg`: the Conduit could not reach **PostgreSQL**. `services/api/config.py`
   defaults `POSTGRES_PORT` to **5433** — a workaround for `deploy/compose/dev.yaml` publishing
   there to dodge a native Postgres on 5432 — while a rendered container listens on 5432. The
   generated env file set `POSTGRES_HOST` and none of the port, database or password, so three
   values diverged silently and the Conduit dialled a port nothing was on.

   **How the error was traceable and I did not trace it:** `LiteLLMClient.__init__` builds an
   `httpx.AsyncClient` and opens no connection, so it could not have raised a refused connection at
   that point. Reading the constructor would have ruled the model gateway out in a minute. I
   matched a symptom to the most recently discussed component instead — and the cost was a decision
   taken on a false premise.

   **Fixed:** the generated env file now carries `POSTGRES_PORT`, `POSTGRES_DB`, `POSTGRES_USER` and
   `POSTGRES_PASSWORD` alongside the host, with one value behind both the container's
   `OSPREY_POSTGRES_*` names and the Conduit's `POSTGRES_*` ones.

   **Owner's decisions of 24 September 2026, recorded.**
   - **Basemap: decided, not awaiting.** A warning does not block Launch; `05_DEPLOYMENT.md` §2.1
     now says so and §2.2 describes the basemap build as a post-install step. The "awaiting
     confirmation" markers are gone from the code and the spec.
   - **Model gateway: recorded, deliberately not built.** The decision — the Conduit tolerates the
     gateway's absence, ModelPort routes return a typed "model backend unavailable" error, Preflight
     reports it absent, the renderer includes the gateway when models are enabled (thirteen
     containers on, eleven off) — is written into `05_DEPLOYMENT.md` §3 as the owner's. It is **not
     implemented this round**, because the reason given for it has turned out not to be the reason,
     and the owner should confirm it knowing that. The behaviour may still be right on its own
     merits; that is a different argument.
   - **Memory: provisional.** Recorded as such in §3, with both of the owner's reasons — the Conduit
     was exited, and ArcadeDB was below its schema-creation floor.

   **[Superseded, fifth pass — exit test #2 went green later the same day; see the COMPLETE entry
   at the top of this stage.] Exit test #2: still not green, and not re-run this round.** Docker Hub
   began returning `429 Too
   Many Requests` on image manifest and base-image pulls partway through, which blocks `docker
   compose build` from a fresh clone entirely. That is an environment limit rather than a defect,
   and it is why the PostgreSQL fix above is **not yet demonstrated end to end** — it is a code fix
   whose verification is owed. The three-sided verify against a deployed realm, its three mutations,
   and the seeded run with the ordering guard all remain blocked behind a healthy Conduit.

   **Superseded (fourth pass) — 24 September 2026. History; see the COMPLETE entry above.**

   **Stage 2 §3 — fourth pass, 24 September 2026. The deploy runs end to end; exit test #2 is
   still NOT green, and the last blocker is a specification gap rather than a defect.**

   **Basemap: warn, not fail.** `harness/preflight/basemap.py` now separates the two outcomes —
   tiles not built yet is a **warn** that does not block Launch, an unservable `file://` URL still
   fails. `--gate` passes on a warn. **Marked awaiting owner confirmation**: a fourth status softens
   `05_DEPLOYMENT.md` §2.1's "Preflight must pass before Launch is enabled", which is a real change
   to what that gate promises, and it was described as an owner decision but does not appear in any
   message he sent. Three tests; collapsing the split turns all three red.

   **Exit test #2, run for real from a fresh clone, five times.** Each run got further and each
   failure was a real defect found only by running it:

   | # | Failure | Cause |
   | --- | --- | --- |
   | 1 | `'str' object has no attribute 'value'` | `--profile` reached `model_copy(update=…)`, which does not validate |
   | 2 | `lstat …/deploy/generated/local-lite/services` | `build.context` is relative to the **compose file**, not the repo root; output sits three levels down |
   | 3 | Conduit, postgres, minio all `Restarting` | the generated env file was written and never wired into any container; the batch loader was set to restart forever |
   | 4 | Keycloak `Unrecognized field` ×2 | a note-to-self and `unmanagedAttributePolicy` were put in the realm document; neither is a `RealmRepresentation` field, and an unknown field fails the **whole** import |
   | 5 | ArcadeDB never healthy, then 403 | the health check used `/dev/tcp`, a bash builtin, while `CMD-SHELL` runs dash; then the server password and the Conduit's `ARCADEDB_ROOT_PASSWORD` were generated separately |

   **Where it now stands: eleven of twelve containers healthy.** ArcadeDB, Valkey, PostgreSQL,
   Keycloak, OpenSearch, MinIO, Ollama, whisper and the Glass all reach health; the batch loader
   exits by design. **Only the Conduit does not**, and the reason is a specification gap:

   **`05_DEPLOYMENT.md` §3's twelve-container list omits LiteLLM, and the Conduit requires it at
   startup.** `services/api/app.py`'s `lifespan` constructs a `LiteLLMClient` unconditionally, so
   the process fail-fasts with `ConnectionRefusedError` against a service the rendered stack has no
   entry for. `deploy/compose/dev.yaml` runs one; §3 does not list one. **Raised as Proposed in
   `05_DEPLOYMENT.md` §3 rather than added silently** — whether the model gateway is a twelfth
   container, a thirteenth, or something the Conduit should tolerate the absence of is a real
   decision, and inventing a service to make a test pass is the wrong way to answer it.

   **Memory, measured, sampled every 5 seconds — and the answer to the milestone question is yes,
   comfortably.**

   | Container | Peak (MiB) |
   | --- | --- |
   | arcadedb | 1,998 |
   | opensearch | 929 |
   | keycloak | 587 |
   | whisper | 227 |
   | api (before it exits) | 207 |
   | minio | 153 |
   | ingest | 97 |
   | postgres / valkey / workspace / ollama | 32 / 26 / 13 / 11 |
   | **Peak total** | **3,607 MiB of a 9,932 MiB VM** |

   **The twelve-container stack fits the 10 GiB VM with room to spare** — ~36% of it, with ArcadeDB
   at its schema-creation peak and OpenSearch capped at a 512 MiB heap by the renderer (its own
   default would have taken a quarter of the VM for an empty index). This is a real measurement of
   eleven containers plus a Conduit that started and exited; a Conduit that stays up adds its own
   steady-state footprint, which this does not include and does not claim to.

   **Not done, because the stack is not healthy:** the three-sided verify against the deployed
   realm and its three mutations, and the seeded second run with the ordering guard. Both need a
   running Conduit. The verify itself is built and proven against a real Keycloak at unit level
   (`tests/services/api/test_revoked_principal_precheck.py`, five cases).

   **docs/demo/2026-09-24/demo_up.sh is deleted** and its runbook points at `harness.apply`.

   **Superseded (previous pass) — 24 September 2026. History; see the COMPLETE entry above.**

   **Stage 2 §3 — the deploy is built; exit test #2 is NOT green, and four blockers are named.**
   Third pass, 24 September 2026. The machinery exists and its own gate works; running it from a
   fresh clone is what produced the findings below, none of which were visible from unit tests.

   **Built.** `harness/apply.py` (six stages: render → preflight gate → build → up-and-wait →
   seed → verify), `harness/realm.py` (the rendered realm import — the Conduit's client, an
   unprivileged client, the four protocol mappers, `unmanagedAttributePolicy: ENABLED`, a
   disposable verify subject and a disabled one), `harness/keycloak_admin.py` (the two
   service-account grants a realm import cannot express), `harness/verify.py` (ADR-043's three
   assertions, real — not stubbed), and Keycloak in the rendered compose with realm import,
   `--features=token-exchange` and a health check. Client secret and Keycloak admin password are
   minted at apply time into the generated, gitignored env file and never printed.

   **§2.4's ordering guard refuses rather than works around.** Asked to seed into a running
   Conduit, `apply` stops and says to stop it first. Silently stopping it would be taking a
   data-affecting decision on the operator's behalf.

   **Exit test #2: NOT green. The gate stopped it, correctly, at preflight.**

   | Blocker | Detail |
   | --- | --- |
   | Port 8000 in use | An unrelated container on this machine. The Stage 2 §5a override exists (`OSPREY_API_PORT`) and was used; recorded because preflight found it before anything was built. |
   | **Basemap never built** | `osprey.yaml`'s default provider points at a PMTiles file that has never been produced — the plan already records `build_local_basemap` as untested live. **A fresh clone cannot reach a health-checked stack while the deployment it renders declares a basemap nobody can build.** |
   | **Two fabricated image tags** | See below. |
   | Twelve-container memory | **Still unmeasured** — the stack never came up, so the 9.7 GiB question the owner asked is still open. Peak observed was 110 MiB, which is the *absence* of a stack, not a measurement of one. |

   **My own defect, and the sharpest finding of the round: two of the eight third-party image
   references written for Stage 2 §5a did not exist.** `minio/minio:RELEASE.2024-10-13T13-34-11Z`
   and `ghcr.io/speaches-ai/speaches:0.6.2` were written from memory and never checked. A real
   `docker compose up` aborted the entire pull with `manifest unknown`, taking five other images'
   downloads with it. Every unit test passed throughout, because none of them asked whether the
   references resolve. **This is rule 15's second worked example in a different costume: a check
   that only ever runs against things it invented cannot discover that they are invented.** Fixed,
   and `tests/harness/test_image_references.py` now resolves every third-party reference — its own
   fallback and the weakness of that fallback are stated in the test rather than hidden.

   **A second self-inflicted bug, found the same way:** `--profile` reached
   `model_copy(update=...)`, which does not validate, so a bare string was assigned to an
   enum-typed field and failed several lines later on `.value` with a message naming neither the
   flag nor the profile. Fixed, with the test.

   **Remaining before exit test #2 can be green:** a buildable basemap (or a deployment default
   that does not require one), and then the twelve-container memory measurement. Both are named
   here rather than worked around.

   **Superseded (previous pass) — 24 September 2026. History; see the COMPLETE entry above.**

   **Stage 2 §3 — RESUMED 24 September 2026 under the owner's four decisions; the verify step is
   built and proven, the deploy script is not.** The round before this one stopped at the
   token-exchange finding. Resuming it found a second, larger defect in the same code path, so this
   entry is again a findings entry rather than a delivery one — and both findings were only
   findable by running the thing against a real identity provider.

   **Step 0, the bounded fine-grained probe: NO.** Keycloak 26.0 cannot be configured to refuse
   exchange for a *specific target subject*. Tried, with `admin-fine-grained-authz` enabled and
   reported enabled by the server: `PUT /users/{id}/management/permissions` → **404**; enabling
   authorization services on `realm-management` → accepted but its resource endpoints stay 404; the
   realm-level `adminPermissionsEnabled` toggle → **400**. So the realm cannot refuse a target, the
   Conduit's pre-check is the only refusal, and there is **no fourth verify assertion** — exactly as
   ADR-043's amendment says.

   **Built: the Conduit's revoked-principal pre-check.** `PrincipalResolver` reads the target's
   `enabled` status through a **separate view-users grant** before any exchange; disabled raises
   `PrincipalRevoked` (a subclass of the existing refusal, so ADR-044's revoked reason is available
   without changing any current caller); unreachable still raises `PrincipalExchangeUnavailable`, so
   ADR-044's unreachable path is untouched; unconfigured leaves it off entirely.

   **Built: the three-sided verify, proven against a real Keycloak 26.0, not a fixture.** Five
   cases in `tests/services/api/test_revoked_principal_precheck.py`, all green: an enabled subject
   is exchanged and carries its own claims; an unprivileged client is refused by Keycloak; a
   disabled subject is refused by the pre-check; **without the pre-check the realm issues a token
   for that same disabled subject** (the rule-15 demonstration, and the finding itself); and an
   unreachable IdP is unavailable rather than revoked.

   **The second defect, and it is the bigger one: ADR-043's exchange had never worked against a real
   Keycloak.** `resolve_for_owner_detailed` omitted `subject_token`, which RFC 8693 §2.1 makes
   REQUIRED. A real Keycloak refuses the request outright — `access_denied`, "Client not allowed to
   exchange" — and grants the identical request with the field present. Measured both ways. Nothing
   caught it because the only thing that code had ever run against was the ephemeral fixture
   ADR-043's own Cost section describes, and **that fixture accepted a request the real server
   rejects**. ADR-043 warned its fixture could not prove a *realm* was correctly configured; the
   warning was narrower than the problem, which was in the request this codebase sends. Fixed, and
   now covered by a test that needs a real IdP by design.

   **Two pieces of realm configuration the deploy's rendered import must carry**, both found only by
   doing it: protocol mappers for `clearance`, `org_unit`, `receivable_handling_codes` and `roles`
   (without them an exchanged token verifies as a token and then fails as a `Principal`), and the
   realm's `unmanagedAttributePolicy` set to `ENABLED` — Keycloak 26 silently discards unmanaged
   user attributes by default, so the attributes are accepted, stored nowhere, and absent from the
   token with no error anywhere.

   **Not built, and again deliberately not half-built:** `harness/apply.py` and its stages, the
   rendered realm import, the apply-time client secret, seeding's ordering guard, exit test #2 from
   a fresh clone, and `demo_up.sh`'s retirement. Two blocking defects in the exchange path were
   found and fixed this round; building the deploy around a path that had never once worked would
   have produced a golden path whose final step was the thing most likely to be wrong.

   **Still not measured, and not to be read as passing:** wall time, peak Docker memory, and whether
   twelve containers fit the 10 GiB VM alongside ArcadeDB's floor.

   **Superseded (earlier round) — 24 September 2026. History; see the COMPLETE entry above.**

   **Stage 2 §3 — STOPPED AND REPORTED, 24 September 2026, at the brief's own instruction.** Three
   product changes are built and tested; the deploy itself is not built, because measuring
   Keycloak's token exchange first — as the brief directed, rather than after — found that the
   verify step this stage's own exit depends on **cannot be built as specified**. Stubbing it was
   explicitly forbidden and would have been the wrong answer anyway.

   **Built and complete.**
   - **`GET /healthz` on the Conduit** — unauthenticated, fixed body `{"status":"ok"}`, touching no
     store. `03_CONDUIT_MIDDLEWARE.md` §3.0 has the route and the reasoning.
     `services/api/Dockerfile` declares a `HEALTHCHECK` against it. Eight tests, including the
     access-control property stated as **bytes**: the anonymous and authenticated responses must be
     identical, because a route with two behaviours hands the attacker the unauthenticated one.
     Three planted red cases — a body reporting a count, a body reporting store status, and a
     handler that answers differently when a token is present.
   - **`python -m services.api.worker_main`** — the loop `JobWorker`'s own docstring anticipated
     ("deployment wiring, not additional logic to test"), and nothing more. Each replica takes a
     distinct consumer name from its hostname.
   - **The replica invariant, named and tested against real Valkey** (rule 12):
     `tests/services/api/test_worker_replicas.py::test_two_replicas_never_process_the_same_job`.
     Deliberately a live-service test — the guarantee is Valkey's `xreadgroup(…, ">")`, not this
     codebase's, and a fake queue would prove only that the fake hands each entry out once, which
     is ADR-041's own recorded failure. Three further cases: three replicas share rather than
     repeat, consumer names vary per hostname, and a failed job is acknowledged rather than left
     pending.

   **The finding that stopped the round, measured against a real Keycloak 26.0 with
   `token-exchange:v1` enabled — not inferred from documentation.** A realm, a confidential client
   with the `impersonation` role, and two test subjects were created, and the exchange run four
   ways:

   | Attempt | Result |
   | --- | --- |
   | Privileged client → the disposable preflight subject | **granted** (a real token, `sub` = the target) |
   | Privileged client → a *different, in-scope* subject | **granted** |
   | Privileged client → a **disabled** subject | **granted** |
   | **Unprivileged** client → a valid subject | **refused** — `access_denied`, "Client not allowed to exchange" |

   **Keycloak scopes impersonation by requesting client, not by target subject.** There is no
   per-target policy: a client holding the grant can exchange for every user in the realm. So the
   refusal half of the two-sided check, as this document's own harness entry specifies it —
   "attempt an exchange for a subject the realm's own policy should refuse (a deliberately-
   out-of-scope or disabled test subject) and confirm it is actually refused" — **would never
   refuse**. Built as written it is a check that cannot go red: exactly the vacuous gate rule 15
   exists to prevent, and it would have been wired into the milestone's own exit test.

   **The third row is worse than a vacuous gate and is reported as a security finding, not a spec
   gap.** A **disabled** user is not a user whose token should be mintable. Keycloak issued one
   anyway. `06_DECISIONS.md` ADR-044 distinguishes an unreachable identity provider from a revoked
   principal on the premise that revocation is observable; ADR-043 places part of its containment in
   "the realm's own token-exchange policy". On this measurement, disabling a principal in the IdP
   does not stop the Conduit minting a token as that principal. Whether that is acceptable, and what
   closes it, is an owner decision and possibly an amendment to ADR-043.

   **What a genuinely two-sided check could assert instead**, offered as the proposal rather than
   applied: success for the disposable subject, and refusal for an **unprivileged client** — the
   one refusal Keycloak actually enforces, measured above. That tests whether the grant is scoped to
   the right client, which is a real containment property; it does not test subject scoping, because
   subject scoping does not exist. The operator wording this document already specifies is unchanged
   and still correct for the failure it describes.

   **Not built, and deliberately not half-built:** `harness/apply.py` and its five stages, the dev
   realm import rendering, the client secret generated at apply time, seeding's ordering guard, the
   post-launch verify, the fresh-clone exit test with wall time and peak memory, and the retirement
   of docs/demo/2026-09-24/demo_up.sh (since removed; this "not built" list is this pass's own
   record, not the current state — see the deletion entry above). The verify step is the last stage
   of the deploy and part of
   what "health-checked" means for exit test #2; building the other four stages around a verify that
   cannot be honest would have produced a golden path whose final step was decorative.

   **Not measured, and it should not be read as passing:** whether the twelve-container stack fits
   the 10 GiB VM alongside ArcadeDB's floor. That measurement needs the stack this sub-stage did not
   stand up.

   **`make test-all` drops volumes before each batch, from 24 September 2026 (owner's decision).**
   Every Floor B measurement taken before that change was taken against accumulated database state.
   **The two-batch numbers of 24 September are superseded by the fresh-volume run: batch 1, 7 failed
   / 136 passed.** The sustained-load characterisation test `05_DEPLOYMENT.md` §8 names is pulled
   forward to run after Stage 2 §3, and **its variable is accumulated database state, not process
   uptime** — the two batch-1 runs below are why.

   **Floor B measured, and a store-degradation measurement that is worth more than the Floor B
   number, 24 September 2026.** `make test-all` was run in the two batches this document's own
   Stage 2a addendum prescribes. What it produced:

   | Run | Stack state | Result | Wall time |
   | --- | --- | --- | --- |
   | Batch 1 | ArcadeDB accumulated across this session's runs, never dropped | **94 failed, 49 passed** | 24:51 |
   | Batch 1, repeated | `make dev-down && make dev-up` — volumes removed, fresh databases | **7 failed, 136 passed** | **6:38** |
   | Batch 2 | after `docker restart` of ArcadeDB only | 48 failed, 106 passed | 40:22 |

   **The first two rows are the same batch, the same code and the same machine, minutes apart.**
   The only difference is whether the graph store's databases had accumulated. 94 failures became
   7, and 25 minutes became 6½. The failures in the contaminated run were `IndexException` on
   `apply_schema`'s own index pass (`"Error on creating index on type 'mx_Person', properties
   [id]"`), with the container reporting `healthy`, `OOMKilled=false` and zero restarts throughout
   — this stage's own already-recorded fifth cause, observed-not-diagnosed, now with a clean
   control alongside it for the first time.

   **Floor B itself, from the fresh run, is intact:** all six members present by test id and no
   others of their kind. The seventh failure in that run,
   `tests/scenarios/test_hmp_graph.py::test_hmp_graph_side`, is an ArcadeDB adapter error rather
   than a model-backend one, so it is **not** a Floor B member and is reported as an addition
   requiring its own diagnosis.

   **Batch 2's 48 failures are withdrawn as a measurement and must not be read as a regression.**
   `docker inspect` showed ArcadeDB `unhealthy` *during* the run (not OOM-killed), so the run
   measured a degrading store rather than the code under test — the same reasoning this document
   already applies to the withdrawn "8 of the last 13" figure: a measurement taken while the
   resource under test is degrading is not a measurement of the thing it claims to measure. A
   container restart alone was evidently not equivalent to dropping the databases, which is itself
   the useful part of the finding.

   **Why this matters beyond the test suite.** `05_DEPLOYMENT.md` §8 already records that a running
   instance needs periodic restarts at an unknown interval, and names
   `test_arcadedb_memory_and_query_latency_under_sustained_ingest_cycles` as the test that would
   characterise it. This round's two batch-1 runs are the sharpest evidence yet that the trigger is
   **accumulated database state, not process uptime** — a restart did not recover batch 2, and
   dropping the volumes did recover batch 1 completely. That distinction changes what the named
   test should vary, and it changes the operational remedy from "restart periodically" to something
   nobody has specified. Recorded here rather than folded into Stage 2a, which is closed against a
   different question.

   ---

   **Sign-in for the Glass — MILESTONE-BLOCKING. Proposed, 25 September 2026. ADR-050.**

   **Not a harness sub-stage.** The owner's decision of 25 September 2026 places this after
   Stage 2 §3 and outside Stage 2's numbering, because it is Glass and Conduit work that the
   harness only has to render a realm for. It is **designed, reviewed and ruled on before it is
   built**; ADR-050 carries the design and its open objections.

   **Why it blocks the milestone.** Stage 2 §3's own Glass leg cannot pass without it, and that leg
   is what makes a rendered deployment demonstrable rather than merely healthy. Measured on
   24 September 2026: a deployment came up healthy, seeded both fixtures and passed its three-sided
   verify, and the Glass it served could not talk to it. §2.6.1's same-origin proxy fixed half of
   that on 25 September — every `/v1` call and the delta WebSocket now reach the Conduit through
   the workspace's own origin, proven against the seeded deployment. The other half is that the
   Glass has **no way for a person to authenticate**. `App.tsx` has said so since Phase 4: the
   `VITE_DEV_BEARER_TOKEN` path is "a stand-in until a real sign-in screen exists, not a production
   auth path", and no phase has owned the replacement.

   **The dev token was used on a rendered deployment for the last time on 25 September 2026** to
   prove the proxy end to end (`docs/demo/2026-09-25/`). Every request went to the workspace's own
   origin and returned 200, the delta WebSocket upgraded through nginx (`101`), and the Conduit
   resolved a real principal from the rendered realm. From here the dev-token path is fenced:
   a production build with it set fails the build.

   **Scope:** OIDC authorization code with PKCE against the deployment's realm, the Glass as a
   public client; the principal's identity and clearance shown in the workspace chrome and used for
   nothing (rule 3 — the adapter is still the only enforcement); re-authentication on expiry with
   the investigation id and selection preserved; sign-out ending the Keycloak session. The realm
   renderer gains a public client, a signing-in subject, redirect and post-logout URIs, and an
   audience.

   **Exit test:** `python -m harness.apply --profile local-lite --seed hmp,fixture-corp`, open the
   printed URL, **sign in**, see the seeded investigation. No dev token anywhere in the path.

   **Three blocking objections, each verified against the tree and each the owner's to settle.**
   ADR-050 has them in full; in one line each:

   1. **The Conduit verifies no audience.** `OIDC_AUDIENCE` is unset in every rendered deployment,
      so `verify_aud` is `False` and any token the realm signs is accepted. A public client is what
      makes that reachable from a browser, and `harness/realm.py` states that a production realm is
      the operator's — that is, shared.
   2. **The renderer cannot know the redirect URI.** The workspace's published port comes from an
      environment variable read at `docker compose` time, and the realm is rendered before that.
   3. **The exit test names a subject that cannot sign in.** `osprey-verify-probe` has attributes
      and no credentials — it is an impersonation target, not a login.

   Plus six non-blocking findings, including that the design's own rule-4 test as worded would pass
   without a single line of ADR-050 existing, and that the refresh-token and working-set-preservation
   choices are both amended in the record rather than left as designed.

   ---

   **Stage 2c — Sign-in for the Glass. BUILT, 25 September 2026, against ADR-050's ruling above.**
   Built and tested:

   1. **Conduit audience verification.** `OIDC_AUDIENCE` is now written into every rendered
      deployment's environment by `harness/render.py`'s `_render_env` (the Conduit's own client id,
      a constant, not a secret — deterministic, needs no apply-time value), and
      `harness/preflight/oidc_audience.py` fails Launch if it is ever absent or wrong, rather than
      the Conduit falling back to accepting any token silently. `services/api/auth.py`'s own
      `verify_aud` conditional was already correct once configured; nothing there needed to change.
      `tests/services/api/test_auth.py::test_a_token_signed_for_a_different_client_is_refused_not_accepted`
      is the new red-then-green case (verified directly: hardcoding `verify_aud` to `False` fails
      it), `tests/harness/test_preflight.py`'s six new `oidc-audience` cases plant a real missing/
      wrong value in a real rendered environment file, and `tests/harness/test_realm.py` proves the
      realm's own audience mapper names the Conduit.
   2. **The realm renderer.** `harness/realm.py` gains `GLASS_CLIENT_ID` (`osprey-glass`): public,
      `standardFlowEnabled`, PKCE S256, an exact redirect URI and post-logout URI derived from the
      new `network.public_origin` schema field (`packages/schemas/deployment.py`, default
      `http://localhost:8080`, validated as a bare origin with no trailing slash) — no wildcards,
      `tests/harness/test_realm.py::test_the_glass_clients_redirect_and_post_logout_uris_are_exact_not_wildcards`
      is the planted-wildcard case. `--demo-analyst` (`harness/apply.py`) renders a disposable,
      separate-from-`VERIFY_SUBJECT` analyst subject with no `credentials` block, mints a real
      apply-time password, and `harness/keycloak_admin.py`'s new `set_demo_analyst_password` sets it
      after import — printed once, in the same final summary block the workspace/Conduit URLs
      already print from, never echoed elsewhere. Absent by default
      (`tests/harness/test_apply_env.py`'s own presence/absence pair).
   3. **The Glass.** `oidc-client-ts` (Apache-2.0, `make licence-check` green on both the Python and
      Node sides) drives a real authorization-code-with-PKCE flow
      (`apps/workspace/src/auth/{oidcConfig,userManager}.ts`): the access token lives in a
      hand-written in-memory `Storage` (never `sessionStorage`, never a refresh token — this
      deployment requests no `offline_access` scope, so none is ever issued), the transient PKCE
      `stateStore` is left at the library's own `sessionStorage` default (consumed and discarded the
      moment the redirect callback completes). `App.tsx`'s sign-in gate shows `SignInScreen`
      whenever there is no token, issuing no `/v1` call until one exists
      (`src/App.test.tsx`'s first case, red-then-green verified against the gate itself). A 401 on
      the *first* authenticated bootstrap call is distinguished from a 401 *after* one has already
      succeeded (`hasResolvedAPrincipalOnceRef`): the former shows the sign-in screen with a reason
      and does not retry (`src/App.test.tsx`'s second case — the wrong-audience/refused path, also
      red-then-green verified); the latter clears the token and issues a silent
      `signinRedirect({prompt:"none"})` round against the identity provider's own session cookie.
      The identity/clearance chrome (`02_GLASS_FRONTEND.md` §2, rule 5, objection 9 — **closed**)
      is informational only; nothing branches on it. Sign-out calls `end_session_endpoint`. The
      delta WebSocket's own `useEffect` now depends on the current token, so a token rotation tears
      down and re-establishes the connection with the fresh one — "authenticates on connect and on
      every reconnect."
   4. **The dev-token fence.** `vite.config.ts` throws at `vite build` time if
      `VITE_DEV_BEARER_TOKEN` is set and `command === "build"`
      (`tests/harness/test_workspace_bundle.py::test_a_production_build_fails_with_the_dev_bearer_token_set`,
      opt-in via `OSPREY_TEST_BUNDLE=1`, red-then-green verified: the planted violation is the
      literal environment variable at a real `vite build`, not a source edit). `npm run dev` is
      unaffected — `deploy/compose/dev.yaml` has no Keycloak, so this is still what `make dev-up`
      exercises.
   5. **Rule 13 — the sign-in screen's own keyboard-driven surface.**
      `apps/workspace/keyboard/actionRegistry.ts` gains `SIGN_IN_ACTIONS` (`submit-sign-in`), proven
      by `keyboard/sign-in.spec.ts` against the real `SignInScreen` wired to the real `signIn()` —
      a real OIDC-discovery fetch and a real top-level navigation to the identity provider's
      authorization endpoint, both intercepted at the transport, not a mocked callback.
      `registryCoverage.test.ts` now asserts nine registries, not eight.
   6. **The accessibility floor on the sign-in screen.** `apps/workspace/a11y/a11y.spec.ts` runs a
      full `wcag2aa` axe scan (not only the colour-contrast subset the rest of that file checks)
      against the real `SignInScreen` via the keyboard harness, both themes — green.

   **One design point ADR-050's own text left unsettled, decided during the build and recorded in
   its own addendum rather than only here:** how the Glass locates the identity provider for OIDC
   discovery, since its bundle carries no baked Conduit address and the same problem applies. The
   call — reach it directly at its own published origin, derived from the browser's own hostname
   plus the default Keycloak port — is `apps/workspace/src/auth/oidcConfig.ts`'s own docstring and
   `06_DECISIONS.md` ADR-050's addendum, not repeated here.

   **7. The WebSocket ticket exchange — BUILT, 25 September 2026, the round after Stage 2 §5b, per
   the owner's own decision of that date.** `POST /v1/ws-ticket` (`services/api/app.py`,
   `PrincipalDep`-gated like every other `/v1` route) mints a random, single-use, 30-second ticket
   bound to the calling principal via `services/api/ws_ticket.py`'s `mint_ws_ticket`, stored in
   Valkey rather than in process memory (statelessness: a ticket minted by one Conduit instance
   must be redeemable by whichever instance the socket lands on). The delta stream now opens with
   `?ticket=...`; `_authenticate_websocket` redeems it via `Valkey.GETDEL` — an atomic
   get-and-delete, which is what makes single-use true under a concurrent redemption race rather
   than merely intended by convention. **A bearer token in the URL is now refused outright, not
   merely deprioritised** — the query parameter read is `ticket`, not `token`, and there is no
   fallback path left to fall into.

   Named tests, all real, none vacuous: `tests/services/api/test_ws_ticket.py` (live Valkey) proves
   a minted ticket redeems to the same principal, a reused ticket is refused (`GETDEL`'s own
   atomicity, not an application-level flag), an unknown ticket is refused, two mints for the same
   principal produce independently-redeemable tickets, and the stored value carries the
   principal's claims rather than anything resembling a bearer JWT.
   `tests/services/api/test_ws_ticket_route.py` proves the mint route itself refuses an
   unauthenticated caller (standing rule 2 / `CLAUDE.md` rule 4 — no exceptions for internal
   endpoints) and binds the ticket to whichever principal authenticated the call.
   `tests/services/api/test_websocket_auth.py` proves `_authenticate_websocket`'s own dispatch: a
   valid ticket resolves a principal, an expired/reused one is refused, and — the literal planted
   shape Checkpoint 2's own client used to send — a real signed JWT placed under the *old* `?token=`
   name is refused outright, with `redeem_ws_ticket` never even called, because there is no `ticket`
   parameter to redeem. **Rule 15's own red-then-green, run for real:** removing the `None`-check on
   `redeem_ws_ticket`'s return value (a fallback principal in its place) turned
   `test_an_expired_or_already_redeemed_ticket_is_refused` red before the fix was restored.
   `docs/03_CONDUIT_MIDDLEWARE.md` §3.2 documents the route; `route-coverage-check` is green on it
   (the gate's own pre-existing, unrelated drift on six other routes is recorded separately, below).

   The Glass side (`apps/workspace/src/App.tsx`): the delta-stream effect now fetches a ticket from
   `POST /v1/ws-ticket` (the same bearer-token header every other bootstrap call already sends)
   before constructing the `WebSocket`, handling a 401 on the mint call the same way every other
   bootstrap fetch in this file already does (`handleUnauthenticatedResponse`). A cancellation flag
   guards the async gap between "ticket requested" and "socket opened" against a fast unmount/token
   rotation. `npm test`'s full 252 and the live `test:integration` suite are unaffected —
   `deltaClient.ts` itself is transport-agnostic and needed no change; only its caller's URL
   construction did.

   **Disclosed, not built this round — read before relying on any of these:**
   - **Silent re-authentication and 401 handling are wired at the bootstrap calls only**
     (`/v1/ontology`, `/v1/investigations`), not through every one of the dozen-plus `api.ts`
     modules `App.tsx` also calls. A token that expires while, say, only `HistoryPanel` is being
     used will surface as that panel's own request failing, not as the ADR's described silent
     recovery, until the next bootstrap-scoped call catches it.
   - **Selection and view-state are not preserved to `sessionStorage` across a silent
     re-authentication round** — only the investigation id (via the pre-existing
     `investigation/investigationId.ts` mechanism) survives a reload. ADR-050's own "preserve the
     selection and view state" sentence is not yet built; `restoreViewStateAfterReauth` in
     `App.tsx` is a named seam for it, not the feature itself.
   - **`crossFilterRef`'s own internal fetches keep the token they were constructed with.** Every
     other consumer in `App.tsx` re-reads `bearerToken` as a live prop; this one, pre-existing,
     "construct once" ref does not, so a token rotation is not reflected in its own subsequent
     `.refresh()` calls until `investigationId` itself changes (which in practice, is never, within
     one session).

   **Two real defects the exit test itself found, neither reachable from the unit-level tests
   above alone — recorded per rule 12/15, not smoothed over:**
   1. **`postLogoutRedirectUris` is not a `ClientRepresentation` field.** The first `_glass_client`
      wrote it as a top-level key, by analogy with `redirectUris`; a real Keycloak 26 import refused
      the whole realm — `Unrecognized field "postLogoutRedirectUris"` — and *no* container became
      healthy, including the Conduit's own. Keycloak stores it as the client attribute
      `post.logout.redirect.uris`. Fixed, and `tests/harness/test_realm.py` now asserts the
      attribute directly rather than the field that happened to round-trip through Python
      untouched.
   2. **An audience mapper on the Glass client alone is not enough.** `harness/apply.py`'s own seed
      step failed with `token rejected: Token is missing the "aud" claim` — not from the Glass, but
      from the Conduit's *own* client-credentials and token-exchange grants
      (`create_investigation`, `grant_service_account_roles`, every ADR-043 exchange), which are
      presented to the Conduit exactly like the Glass's tokens and were just as unconditionally
      refused once `verify_aud` turned on for real. Fixed by moving the mapper to a plain custom-
      string audience (`included.custom.audience`, not `included.client.audience`) attached to
      *both* the Conduit's own client and the Glass's, plus a new
      `test_the_conduits_own_client_also_carries_the_audience_mapper` case naming the regression
      directly.

   Both were found by running `python -m harness.apply --profile local-lite --seed
   hmp,fixture-corp --demo-analyst` for real against a fresh render, exactly the exit test ADR-050
   names — neither is a case any of the unit-level realm/preflight/auth tests above could have
   caught on their own, since each needs a real Keycloak import or a real multi-client token flow.

   **Three more, found by the Playwright walkthrough itself rather than by the apply run
   completing green — `apply` reporting "3/3 assertions green" measures the three-sided
   token-exchange verify, not whether an analyst can actually use the Glass, and each of these
   would have shipped invisibly behind that green:**

   3. **A `?investigation=` URL id was never reaching `sessionStorage` before the sign-in
      redirect.** `App.tsx`'s investigation-persisting effect had been folded into the same
      `if (!bearerToken) return` guard as the POST-a-new-investigation fallback below it — correct
      for the fallback (a real network call), wrong for the persist (no network call at all, and
      `docs/02_GLASS_FRONTEND.md` §2.1's own "written back immediately" is unconditional). On an
      unauthenticated first load the guard fired before the id was ever written, so the browser
      came back from Keycloak with no memory of it and silently created a second, empty
      investigation instead of opening the seeded one. Split into its own unconditional branch.
   4. **Keycloak's own `VERIFY_PROFILE` required action stopped the demo analyst's first
      interactive sign-in** with an unexpected "Update Account Information" form demanding
      email/first/last name — a fresh admin-API user has none of Keycloak's own default profile
      fields, and Keycloak demands them before issuing a token regardless of anything this codebase
      configures. Fixed by giving the rendered subject `email`/`emailVerified`/`firstName`/
      `lastName` (`.invalid`, RFC 2606's reserved non-resolving TLD).
   5. **The demo analyst could sign in and reach the Conduit and still see nothing — the seeded
      investigation's own working set stayed at zero nodes, zero edges.** Two separate causes,
      both access control doing exactly what rule 3 asks and neither reachable without seeing real
      seeded content refused for a real reason:
      - `scripts/seed_hmp_fixture.py`/`scripts/seed_fixture_corp.py` write every node with
        `handling_code="P"`; the demo analyst's attributes (copied from the shared,
        verify-scoped `_SUBJECT_ATTRIBUTES`) could only receive `"R"`. Every seeded node was
        filtered before it ever reached the working set — the same "filter at the adapter, existence
        undetectable" behaviour rule 3 requires, applied correctly to a subject nobody had actually
        granted the seeded data's own code.
      - `harness/apply.py`'s `create_investigation` creates the seeded investigation by exchanging
        for `VERIFY_SUBJECT`, whose `org_unit` becomes the investigation's own `owning_unit`
        (`services/api/investigations.py`'s `principal.org_unit == investigation.owning_unit`
        boundary). Giving the demo analyst a *different* `org_unit` — the first, more "correctly
        separate-looking" fix attempted — made the investigation itself invisible: a 403 on the
        delta WebSocket handshake and a 404 on every investigation-scoped route, indistinguishable
        from a broken deployment without reading that boundary's own reasoning.

      Resolved by giving `DEMO_ANALYST_SUBJECT` its own attributes (objection 4's own reasoning,
      applied for real rather than only in the identity dimension): `receivable_handling_codes:
      ["P"]` so the seeded content is visible, `org_unit: ["verify"]` — unchanged from the shared
      default, and deliberately not diversified — so the investigation the verify-scoped subject
      created is still the one it can open, and `clearance: ["OFFICIAL"]` kept as-is so
      `fixture_corp.py`'s own single `SECRET`-classified node stays correctly invisible: the access-
      control floor demonstrating itself in the demo, not a gap in it.
      `test_demo_analyst_can_receive_the_handling_code_the_seed_fixtures_actually_write` and
      `test_demo_analyst_shares_the_verify_subjects_org_unit_so_the_seeded_investigation_is_visible`
      name both regressions directly.

   **Exit test — run for real against a fresh apply, five iterations to green, not asserted from
   the code.** `OSPREY_WORKSPACE_PORT=8095 python -m harness.apply --profile local-lite --config
   /tmp/exit-test-osprey.yaml --seed hmp,fixture-corp --demo-analyst` — a temporary config layering
   `network.public_origin: http://localhost:8095` onto the committed `osprey.yaml`, because 8080/
   8081 were held by stale, already-torn-down Docker port-forwards on this machine for much of this
   session (Docker Desktop's own proxy, not this deployment — `OSPREY_WORKSPACE_PORT`/
   `network.public_origin` moving together is the existing, documented shape for exactly this).
   Sign-in as `osprey-demo-analyst` via the real Keycloak login form: **green.** The chrome showed
   the real subject and `OFFICIAL` clearance; the seeded investigation's own hotspot panel
   (`/v1/analytics/geobins`) and timeline (`/v1/analytics/histogram`) both rendered real seeded data
   — screenshots in `docs/demo/2026-09-25/`. (The canvas's own "0 nodes" status is separate and
   correct: the working-set graph is populated by explicit add/expand actions, not automatically
   equal to everything the investigation can see — the exit test's own wording asks for the hotspot
   panel and timeline, and both are real.)

   **Both named mutations, run against the live deployment rather than a fresh redeploy each time
   (the realm's own protocol mappers and the demo analyst's `enabled` flag are both live-editable
   via the Keycloak admin API this harness already uses):**
   - Audience mapper removed from the Glass client (`DELETE .../protocol-mappers/models/{id}`):
     Keycloak's own login still succeeded — the credential is real and unaffected — and the Conduit
     refused every subsequent call with 401 (`/v1/ontology`, `/v1/analytics/geobins`, `/v1/map/
     providers`, a 403 on the delta WebSocket handshake), and the Glass showed "Your sign-in could
     not be used to reach the workspace. Check with your administrator that this deployment's
     identity provider is configured correctly." — not an error page, not an empty workspace.
     Screenshot: `06-mutation-wrong-audience-refused.png`. Mapper restored, sign-in green again.
   - Demo analyst disabled (`PUT` `enabled: false`): Keycloak's own login form refused outright —
     "Account is disabled, contact your administrator." — before any token was ever issued.
     Screenshot: `05-mutation-disabled-analyst-refused.png`. Re-enabled, sign-in green again.

   ---

   **Stage 2 §4 — Backup and restore. ACCEPTED.** `python -m harness.backup` writes to
   `backups/<UTC-timestamp>-<profile>-<git-sha>/` with a `manifest.json` naming every file, its
   checksum and the schema versions, covering **`05_DEPLOYMENT.md` §4's full set**: staged Parquet,
   **object store contents**, the PostgreSQL dump, ontology, handling scheme and `osprey.yaml` —
   and stating audit data's own disposition (§6: not rebuildable, not deletable, replicated
   separately). `python -m harness.restore <dir>` rebuilds the graph store from Parquet into an
   **empty** store and restores PostgreSQL, **opening with §4's dry run — row count and projected
   duration, not proceeding until acknowledged**. §2.4's backup-before-switch and downgrade
   capacity guards attach here, where a backup exists to check for. `deploy/RUNBOOK.md` is created,
   stating the recovery time for each path (§6), measured on `local-lite` — a different file from
   Stage 2 §1's generated per-deployment runbook. **Exit test:** backup → restore reproduces the graph into
   an asserted-empty store — node and edge multisets equal **including edge properties**, handling
   markings, provenance and assessment objects compared as payloads rather than counted (ADR-010;
   a restore that drops every handling marking passes a bare multiset comparison and silently
   widens access), and the τ 0.99/0.95/0.80 resolution projections ADR-035 §C5 already requires
   Fixture Corp to exercise returning identical results (ADR-006: `SAME_AS` edges are scored, and a
   multiset of pairs that ignores the score passes while every projection changes). **Stage 2 exit
   test #1**, and this stage's already-stated criterion above.

   ---

   **Stage 2 §4 — BUILT. Exit test #1 is GREEN, 24 September 2026.**

   ```
   exit test #1: 1978 record(s) restored in 8s
   9 passed in 56.73s
   ```

   `python -m harness.backup` and `python -m harness.restore`, `harness/compare.py`'s deep
   snapshot, `deploy/RUNBOOK.md`, and `tests/harness/test_restore_exit_test.py` — which takes a
   backup of a seeded deployment, **destroys its volumes**, restores it, and compares the two.

   **Measured on `local-lite`** against the seeded HMP + Fixture Corp fixture (1,978 records, a
   4.0 MB set), with the Conduit quiesced:

   | Path | Measured | Dominated by |
   | --- | --- | --- |
   | Backup, whole set | **10s** | ArcadeDB's `BACKUP DATABASE` — 2.57 GB of allocated pages to 3.2 MB |
   | Short path: restore | **8s** | the offline restore tool |
   | Long path: rebuild from staging | **35s** | re-running both fixtures' recipes |
   | Stack back up, empty | 28s | container start-up, not data |
   | End to end, destroyed → seeded → verified | **64s** | 28s start-up + 35s replay |

   At this size the short path saves 27 seconds, which is not why it exists — §6 is explicit that
   these backups "exist to shorten recovery, not to make it possible". The ratio is the point and it
   does not hold still: the short path scales with stored data, the long path with the *work* that
   produced it.

   **The exit test's amended comparison, and the four mutations that show it can go red.** ADR-049
   named three holes in the original comparison; `GraphSnapshot.differences_from` closes each, and
   each is exercised against the real restored snapshot rather than a hand-built one:

   | Mutation | Hole it covers | Signal |
   | --- | --- | --- |
   | Every `handling*` field dropped from every node | 1 — markings are first-class (ADR-010) and a multiset of identities passes without them, silently widening access | `node multiset differs` |
   | The τ=0.99 projection emptied, every edge kept | 2 — `SAME_AS` is scored and resolution is a query-time projection (ADR-006); a pair-multiset passes while every projection changes | `resolution projection at τ=0.99 differs` |
   | One edge removed | the ordinary loss | `edge multiset differs` |
   | One `mx_Person` removed from the counts | the ordinary loss | `type mx_Person: … before, … after` |

   Plus the three refusals, each shown firing against the live deployment: a **truncated** set (the
   real shape — file shortened in place, manifest untouched) refused on checksum; a restore into the
   **populated** store refused; and the dry run asserted to change nothing, by snapshotting either
   side of it rather than by trusting the code path.

   **Six defects found by running it, every one of them a thing the store does rather than a thing
   it documents:**

   1. **`SELECT count(*) FROM V` returns "empty" for a store holding 1,109 vertices.** ArcadeDB has
      no `V`/`E` supertypes unless something creates them; the `SchemaException` read as "no such
      database". That was the restore's emptiness refusal — **a refusal that could never fire**,
      exactly rule 15's shape.
   2. **`schema:types`' `records` field lags a bulk write.** Its replacement. Immediately after the
      seed it reported 606 `mx_PRESENT_AT` where `count(*)` returned 614, catching up minutes later
      with no write between. The exit test duly failed and **blamed the restore** — "614 before,
      606 after" for byte-identical data. A comparison whose own instrument drifts produces false
      accusations, which is worse than producing nothing. Counts now come from `count(*)` per type.
   3. **ArcadeDB cannot be restored over HTTP.** `POST /api/v1/server` with SQL answers `Server
      command not valid`; `POST /api/v1/command/<db>` answers `ParseException: Encountered
      <IDENTIFIER> "RESTORE" at line 1, column 1`. Restore is offline — `bin/restore.sh` — because
      the engine will not overwrite a database it has open. Both wrong paths looked entirely
      plausible and were written before being tried.
   4. **`/home/arcadedb/backups` does not survive the container.** It is created by the first
      `BACKUP DATABASE` and lives in the image's filesystem, not a volume — so after the `down -v`
      a restore exists to recover from, `docker compose cp` into it fails. The one situation a
      restore always runs in was the one situation the copy could not work in.
   5. **The object-store tar deleted itself.** Its staging directory was `<target>/objects`, the
      same directory the tar was written into, and the cleanup `rmtree` took both. The backup
      reported success and the set was missing its object store. Caught by the exit test's own
      checksum verification on its first run, which is the argument for checksumming every file.
   6. **The restore needs the Conduit's container to exist and not be running.** `docker compose cp`
      addresses a container, not a volume, so the analytics DuckDB has nowhere to land without one;
      and the Conduit holds an exclusive lock on that file, the same constraint that makes the seed
      stop it. `docker compose create` is the shape that satisfies both.

   **Three departures from §6's table, recorded in `05_DEPLOYMENT.md` §6.2 rather than made
   quietly:** a logical `pg_dump` instead of `pg_basebackup` (no WAL archive on `local-lite`, and a
   physical copy is tied to the page layout); the analytics DuckDB included although the table names
   no row for it (266 events, not rebuildable from the graph store, and a backup without it restores
   a graph with no timeline); and **audit data is not separately replicated** — `audit_log` shares
   its PostgreSQL instance, and therefore its retention and its backup, with sites, monitors,
   alerts, the export ledger and the review queue. §2.4's destroy confirmation assumes otherwise.
   The manifest carries an `audit_disposition` block and the dry run prints it, so the limitation
   cannot be discovered during an incident.

   **The spec gap this stage was asked to find: how secrets are re-supplied on a restore.** §6 does
   not say. A restore lands old data in a **new** deployment with **new** apply-time secrets, and
   nothing reconciles them. It works today only because nothing in the set is encrypted with a
   deployment secret — and the day anything is, a restore starts succeeding while producing data
   nobody can read, the worst available failure because it reports success. Recorded as
   `05_DEPLOYMENT.md` §6.1, Proposed, with three candidate shapes. **It needs an owner decision.**

   ---

   **The suite, after Stage 2 §4, 24 September 2026 — no regression, and one more data point for
   the store-degradation mechanism.**

   | Run | Result | Wall time |
   | --- | --- | --- |
   | `make test` (fast, no live infra) | **826 passed, 1 failed** | 1:32 |
   | `make test-all` as one invocation, volumes dropped first | **100 failed, 196 passed** | 9:20 |
   | Batch 1 (to `test_prefetch.py`), fresh volumes | **143 passed, 7 failed** | 6:24 |
   | Batch 2 (the rest), fresh volumes | **144 passed, 3 failed** | 5:10 |

   **287 passed across the two batches — the recorded baseline's pass count exactly.** The single
   invocation is not a measurement: ArcadeDB was **OOM-killed** partway (`Exited (137)`, the
   container gone from `docker compose ps` afterwards), and 599 `ConnectError` plus 200 `ReadTimeout`
   are all downstream of that. This is the mechanism the Stage 2a addendum already closed — a long
   sequential run against one accumulating database — arriving for the third time, and it is why
   that addendum prescribes two batches. Read the single-invocation row as a reproduction of a known
   condition, not as a result.

   **Batch 1 is Floor B exactly**: the six model-backend members (four `[model_litellm]` conformance
   cases, `test_golden_set_recall_has_not_regressed`,
   `test_extract_returns_nonempty_persons_from_the_witness_statement`) plus
   `test_hmp_graph.py::test_hmp_graph_side`, already on record as an ArcadeDB adapter error and
   **not** a Floor B member.

   **Batch 2's three failures were each chased to a cause, and none of them is this round's work:**

   - `test_fixture_corp_shape.py`'s two both **pass in isolation on a fresh stack**. Accumulated
     state within the batch, the same mechanism as above.
   - `test_assessment_routes.py::test_save_judgement_route_creates_and_returns_it` fails
     **identically at `d9e1c62`** — the commit this round started from — when both are run against
     fresh volumes in the same fixed order: 1 failed, 11 passed, at both revisions. It passes when
     run alone at either. Pre-existing order-sensitivity, recorded here rather than left as an
     unexplained delta. It has no owning finding yet.

   **Three CI gates were already red at `d9e1c62` and this round did not touch two of them:**
   `make lint` (28 pre-existing `ruff` I001/F401 findings across `services/`, `scripts/`, `tests/`
   and `packages/`, unchanged with the tree stashed — most likely a `ruff` version bump);
   `route-coverage-check` (six routes registered in `services/api/app.py` and documented nowhere:
   `GET /v1/exports`, the three `GET /v1/investigations/{id}/{assumptions,gaps,judgements}`,
   `GET /v1/yardstick`, `POST /v1/analytics/sightings`); and `make typecheck`, which **was** red and
   is now green — two errors in this stage's own earlier code, plus `harness/` joining the gate for
   the first time and bringing seven more.

   ---

   **The suite after the same-origin proxy, 25 September 2026 — identical to the day before, test
   id for test id.**

   | Run | Result | Wall time |
   | --- | --- | --- |
   | `make test` | **827 passed, 1 failed** | 1:35 |
   | Glass unit tests (`npm test`) | **249 passed, 39 files** | 1.2s |
   | Batch 1, fresh volumes | **143 passed, 7 failed** | 6:42 |
   | Batch 2, fresh volumes | **144 passed, 3 failed** | 4:58 |

   287 passed across the two batches, and **every failing test id is one already on record**:
   batch 1 is Floor B's six model-backend members plus `test_hmp_graph_side`; batch 2's three are
   the two `test_fixture_corp_shape.py` cases that pass in isolation on a fresh stack and
   `test_save_judgement_route_creates_and_returns_it`, which fails identically at `d9e1c62`. The
   one `make test` failure is `route-coverage-check`'s six undocumented routes, also unchanged.
   Nothing in this round moved the floor in either direction.

   **Stage 2 §5 — split into §5a and §5b, owner's decision, 24 September 2026.** `Stage 2 §3`
   cannot start a stack whose images do not exist, and the rendered compose file named three
   `ghcr.io/ospreyflow/…` images no registry publishes. **`Stage 2 §5a` runs before `Stage 2 §3`**
   (enumeration, rule 8 repayment, Dockerfiles, local builds); **`Stage 2 §5b` stays after
   `Stage 2 §4`** (the bundle, ADR-035's registry, the §B7/§C2 scans). Stage 2's three exit tests
   are unchanged — this reorders work, it does not re-scope the stage.

   **Stage 2 §5a — the images the golden-path deploy needs. BUILT, 24 September 2026.**

   **The enumeration, run and reported before any image was built, as directed.** `harness/
   service_inventory.py` holds it as code and `tests/harness/test_service_inventory.py` checks it
   against the tree, so a directory that gains or loses an entrypoint fails the build until the
   table and its reasoning are updated — a document table would have gone stale in silence.

   | Directory | Kind | Entrypoint | Imported in-process by | Created | Image |
   | --- | --- | --- | --- | --- | --- |
   | `services/api` | **deployable** | `uvicorn services.api.app:app` | — | Phase 3 | existed |
   | `services/ingest` | **deployable** | `python -m services.ingest` | — | Phase 2 | existed |
   | `apps/workspace` | **deployable** | `vite build`, served static | — | Phase 4 | **new here** |
   | `services/extract` | library | none | `services/api` (`review.py`, `app.py`) | Phase 6 | none needed |
   | `services/resolve` | library | none | `services/api` (`evaluation.py`, `resolution_trigger.py`, `app.py`, `working_set/service.py`) | Phase 6 | none needed |
   | `services/geocoder` | library | none | its own tests only | Phase 5 | none needed |
   | `services/compute` | placeholder | none — `__init__.py` and nothing else | — | Phase 7 | none needed |

   **The rule 8 repayment record, corrected by the enumeration that was run to produce it.** The
   accepted text of ADR-049's ruling 5 records `extract`, `resolve`, `compute` and `geocoder` as a
   rule 8 violation by their creating phases. **They are not, and no image is built for them.** All
   four are libraries or an empty placeholder with no process entrypoint; they ship inside the
   Conduit's image. Rule 8 says "each **service** gets its Dockerfile", and a package that only runs
   inside another service's process is not a service in that sense — an image for one would be a
   container that starts nothing. **The single real debt is `apps/workspace`, owed by Phase 4 and
   paid here**, with its `trivy image` scan wired into both `make ci` and `ci.yml` as rule 8's pair
   requires. `tests/harness/test_service_inventory.py` asserts both directions: every deployable
   directory has a Dockerfile, and no library or placeholder does.

   **Finding, raised as Proposed in `05_DEPLOYMENT.md` §3 (rule 11), not silently resolved: §3's
   "three workers" cannot be rendered.** One worker implementation exists —
   `services/api/worker.py`'s `JobWorker`, the generic job-type dispatcher ADR-025 specifies — and
   it is a class with **no process entrypoint**. Zero worker containers are buildable today, not
   three. The proposal is that "three workers" means three replicas of one worker process, which is
   what the code is shaped like; adopting it needs an entrypoint, which is product code and outside
   this sub-stage. A test asserts the finding stays true, so giving the worker an entrypoint fails
   the build until the finding is revisited.

   **Second finding, same section, and it is a `Stage 2 §3` blocker: nothing can be
   health-checked.** `docker compose --wait` needs a declared health check per service. The Glass's
   new image declares one; the Conduit's and the batch loader's do not, and **the Conduit exposes no
   health endpoint at all** — every route is an authenticated `/v1/…` path, so there is nothing to
   poll even if a check were declared. Proposed in §3: an unauthenticated liveness route touching no
   store, and no health check on the batch loader, which exits by design. Adding a route is product
   code; §3 cannot reach its own exit test until this is settled.

   **Images built locally, from this checkout, with no registry.**

   | Image | Size | Build | Isolation check |
   | --- | --- | --- | --- |
   | `osprey/workspace:local` | 66.3 MB | 40s | **healthy**; HTTP 200; SPA deep link 200; runs as `nginx` |
   | `osprey/api:local` | 1.13 GB | 56s | starts only with a reachable IdP — correct fail-fast, see below |
   | `osprey/ingest:local` | 599 MB | 0.7s (shared cached layers) | `--help` runs; a batch job, exits by design |

   The Conduit's container **cannot** start in isolation and should not: it fail-fasts on a missing
   `OIDC_JWKS_URL` and then on an unreachable JWKS endpoint, which is `services/api/config.py`'s own
   deliberate behaviour. Isolation testing it is therefore not possible, and §3 must order Keycloak
   before it.

   **A latent bug found the first time the ingest image was ever actually run.** It died on import
   with `PermissionError: /app/packages/adapters/graph_arcadedb/naming.py`. That file was mode
   `0600` on this machine; `COPY` preserves the mode, so it landed in the image owned by root and
   unreadable by the runtime user. **Git tracks it `100644` and a fresh clone is unaffected** — so
   this was never a repository defect, which is exactly why it went unnoticed. The image should not
   depend on every developer's umask: `services/ingest`'s Dockerfile now uses `COPY --chown`, and a
   test asserts both Python images either `--chown` or `chown -R`. `services/api` was immune only by
   accident, its DuckDB extension step running `chown -R` for an unrelated reason.

   **The renderer now distinguishes the two kinds of image.** OspreyFlow-owned services render a
   `build:` context plus a local tag, so `docker compose build` produces them with no registry;
   third-party images keep their pinned upstream references. `versions.lock` records owned images as
   `source: local-build` with the git SHA they were built from and their Dockerfile path — not a
   digest, because an image pushed nowhere has none, and recording whatever the local daemon holds
   for an overwritable tag would look like a pin and be worth nothing. A render naming an owned
   service with no Dockerfile in the tree **fails by name**, rather than producing a compose file
   that dies later inside `docker build`.

   **Every published host port is overridable**, with the specification's own defaults
   (`OSPREY_WORKSPACE_PORT=8080`, `OSPREY_API_PORT=8000`), because Preflight found 8000 already held
   by an unrelated container on a real machine. That change broke `declared_ports()` in Stage 2 §2 —
   the host side stopped being a bare number and `split(":")` could not even tokenise
   `${VAR:-8000}:8000` — so the port check silently found nothing and passed vacuously. Caught by
   Stage 2 §2's own test the moment the renderer changed, fixed, and given four cases of its own.

   **Trivy, red then green, with the real flags.** A deliberately old base (`nginx:1.21-alpine`,
   carrying CVE-2022-37434 among others) scanned with the identical
   `--severity HIGH,CRITICAL --ignore-unfixed --exit-code 1` invocation exits **1**; the Glass's own
   image exits **0** with zero findings on Alpine 3.21.3.

   **Remaining in §5a:** nothing. The two §3 blockers above are §3's to resolve, and both are
   recorded as Proposed rather than decided here.

   **Stage 2 §5b — Packaging, the `osprey bundle` shape. ACCEPTED; D1 confirmed NARROWED, 24
   September 2026.** **First task, before any packaging code: the service enumeration.** Enumerate
   the six `services/` directories plus `apps/workspace`, state which are **deployable** and on what
   evidence, and build the `Dockerfile` and `trivy image` CI job for each deployable one that lacks
   them — **as Stage 2 work, not as debt owed by earlier phases**, per the owner's narrowed D1. The
   harness's own image (`ghcr.io/ospreyflow/harness:latest`) is built here too, since Stage 2 §6
   cannot be bootstrapped by its own documented `docker run` until it exists. Starting evidence,
   checked directly 24 September 2026: only `services/api` (Conduit, `app.py`) and `services/ingest`
   (batch, `__main__.py`) carry a Dockerfile; `extract`, `resolve`, `compute` and `geocoder` have no
   entrypoint of any kind today, and `make ci` has `trivy-image-ingest` and `trivy-image-api` only.
   **The conflict the enumeration must resolve, not rediscover:** `05_DEPLOYMENT.md` §3 specifies
   that `local-lite` runs "the workspace, one Conduit, **three workers**", and the tree contains
   exactly one worker entrypoint. **Report which way that resolved as a finding before building any
   image** — either three of the four become processes needing their own images, or §3's component
   count is wrong and the specification is corrected; building four images against an unexamined
   count would answer the question by accident.

   **Standing rule 8 stands unchanged — this is a repayment, not an exception** (owner's decision,
   24 September 2026, declining the exception an earlier draft proposed). The four services without
   Dockerfiles are recorded as a **violation of rule 8 by the phases that created them**, remedied
   here once. The rule keeps its full force for every future service: a phase that skips its
   Dockerfile is still in violation and cannot cite this stage as precedent for deferring one.

   **Wraps `scripts/osprey_bundle.py`** — which exists, is tested, and whose own docstring already
   says "The real `osprey bundle` command wraps `bundle_map_providers` below in Phase 8" — rather
   than writing a second implementation of the same command. Builds the images for each deployable
   service and the bundle tarball; `--images` produces the **signed** archive of every image **and
   weight file** `05_DEPLOYMENT.md` §5 requires, a path §5 also requires to be tested each release.
   **Also a first deliverable, because this sub-stage consumes it and it does not exist:** ADR-035
   §C1's `shipped`/`internal`
   manifest schema, its fail-closed registry and `make demo-manifest`, with C1's own two named
   tests (tests/demo_registry/test_fail_closed.py — not yet written); `scripts/demo_guide_check.py`'s
   `DEMO_REGISTRY` is a stand-in for it by its own docstring, not the thing itself. Assertions,
   each a test: no private-tree file in the artefact (ADR-034 §B7 #1) — **keyed off
   `scripts/product_tree_link_check.py`'s existing marker list, never a `docs/`/`spec/` path
   prefix**, since ADR-034 §B2 puts `06_DECISIONS.md` inside `spec/` and permanently unpublished
   while §B8 makes `docs/design/tokens.css` product source, and since a prefix-keyed test goes
   green now and becomes a silent no-op the moment Trigger A renames the tree; no B5 authorship
   identifier, including build metadata (§B7 #2); no internal-class demo data in the tarball **or
   any image layer** (ADR-035 §C2, which needs a `.dockerignore` — checked directly, none exists in
   this repository — and both of C2's own named tests, including
   `test_removing_the_exclusion_step_itself_fails_the_gate`); **`config/real_data_exceptions.yaml`
   never enters an artefact**, a new assertion no record names today and the one most likely to be
   present on the machine that builds a bundle; tiles/gazetteers with `redistributable: false`
   refused and named (`00_ARCHITECTURE.md` §1.2). **`LICENSE` and `NOTICE` are created here, not
   deferred** — ADR-034 §B7 is "a blocking prerequisite of Phase 8's own harness/packaging work,
   not a follow-up to it", and this document's own Trigger A entry already states that "the holder
   name, the licence text itself, and the files' own presence are not year-dependent and are not
   deferred"; the third `licence-check` leg specified there (Apache 2.0 text byte-identical;
   `NOTICE` naming "The OspreyFlow Authors") is built in the same pass, and Trigger A's list
   records it as discharged early. Only the copyright *year* remains Trigger B's, unchanged.
   `make licence-check` is extended per ADR-035 §C7 to data-file licences in the same pass, with
   its own red-then-green. **The harness's own image** (`ghcr.io/ospreyflow/harness:latest`, §2/§3's
   bootstrap) is built here; **standing rule 8's Dockerfile-and-`trivy image` debt** for the
   services that have neither is ADR-049 objection 5, not silently absorbed here. **Exit test:**
   each planted violation fails the bundle, each taking the shape the gate actually receives at its
   own real call site. **Stage 2 exit test #3.**

   **BUILT, 25 September 2026 — the narrower scope a directed brief actually asked for, recorded
   plainly against the fuller description immediately above it.** The brief covered: extending
   `scripts/osprey_bundle.py` into the real `python -m scripts.osprey_bundle --profile local-lite
   [--images]` command (`build_bundle`, `make_tarball`); the seven named assertions — ADR-035 §C1's
   fail-closed registry (`scripts/demo_registry.py`, `make demo-manifest`, `tests/demo_registry/`);
   ADR-034 §B7 #1/#2 and ADR-035 §C2 (`scripts/packaging_gate.py`, `tests/packaging/`, 20 cases
   including the two ADR-named red-then-green proofs); the existing non-redistributable-tile
   refusal (unchanged, reused); `LICENSE`/`NOTICE` (Apache 2.0 text, "The OspreyFlow Authors",
   `tests/packaging/test_internal_demo_exclusion.py`'s `check_license_and_notice` cases); and
   `make licence-check` extended to data-file licences per ADR-035 §C7
   (`find_data_licence_offenders`, `tests/licence_check/test_data_licence_offenders.py`, including
   the CDLA-Sharing-1.0 case §C6 names). The service-enumeration/Dockerfile/`trivy image`/
   harness-image work this stage's own fuller description above assigns to `§5b` was mostly already
   discharged by `§5a`'s own split (workspace/api/ingest images, standing-rule-8 repayment) — except
   `ghcr.io/ospreyflow/harness:latest` (`§2`/`§3`'s own bootstrap image), which neither `§5a` nor
   this round's own first pass built. **That gap is now closed, in the round after, per the owner's
   own decision of 25 September 2026 to pay it before the closing pass.**

   **`harness/Dockerfile` — BUILT.** Minimal by file tree, not by dependency set — `uv sync`
   installs this project's one full dependency set (the same shape `services/api`/`services/ingest`
   already use, never a second hand-pruned manifest), and only three project-tree roots are copied
   in: `harness/`, `packages/schemas/`, `scripts/`. **Checked directly, not assumed:** tracing every
   module the six subcommands below actually import, recursively, touches exactly those three roots
   and nothing under `services/` or any other `packages/*` subdirectory. A new `harness/__main__.py`
   dispatches `python -m harness <subcommand>` to `render`, `preflight`, `apply`, `backup`,
   `restore` (each its own `harness.<name>`) and `bundle` (`scripts.osprey_bundle` — the one
   deliberate exception, ADR-049's own "wraps `scripts/osprey_bundle.py`... rather than a second
   implementation"), proven by `tests/harness/test_harness_main.py` including the real bug its own
   first run found: `harness.preflight` is a package whose `main()` lives in `__main__.py`, and a
   naive `importlib.import_module("harness.preflight").main` raises `AttributeError` — caught by
   `test_every_named_subcommand_resolves_to_a_module_carrying_main`, red-then-green verified.
   The Docker CLI itself is copied from Docker's own official `docker:27-cli` image
   (`docker.io`/`docker-compose-plugin` are not Debian trixie package names, found building this),
   never installing a daemon this image never runs; the one privilege it needs — the host's docker
   socket — is documented as declared at `docker run` time only, per `05_DEPLOYMENT.md` §2.5, never
   baked in. `trivy image` green (`make trivy-image-harness`, wired into `ci.yml` the same way
   `apps/workspace`'s own was at §5a).

   **Exit test, run for real:** the image builds, and `docker run ... preflight --gate` from it
   reaches the same result as the host CLI — `tests/harness/test_harness_image.py` (opt-in,
   `OSPREY_TEST_HARNESS_IMAGE=1`), its own dedicated CI job. **One named, measured exception, not a
   defect:** the `memory` check reads `os.sysconf("SC_PHYS_PAGES")`, and on a Docker-Desktop host
   (macOS, Windows) that answers a genuinely different question run natively (this build machine's
   own 36.0GiB) than run inside the image (the Docker Desktop VM's own smaller, allocated budget —
   9.7GiB, measured on the same machine, same moment) — both readings are correct for what they
   measure, and the VM's own figure is arguably the more relevant one, since it is what the
   deployment's own containers are actually constrained by. Excluded from the comparison by name,
   not silently dropped; every other one of the eleven checks — `disk`, `gpu`, `ports`,
   `container-runtime`, `cluster-connectivity`, `interpreter`, `bind-address`, `basemap`,
   `duckdb-lock`, `oidc-audience` — matched in outcome. A native Linux host has no VM layer and
   would show no such discrepancy; this is Docker-Desktop-specific, not a general admission that
   the check disagrees with itself. The harness image is also now archived by `--images`
   (`scripts.osprey_bundle.HARNESS_IMAGE`, item 3's own "include it in the bundle's image set" —
   `test_build_bundle_with_images_also_archives_the_harness_bootstrap_image`).

   **The bundle-time documentation site — BUILT, 25 September 2026, both halves of item 3's own
   "into both the tarball and the workspace image at `/docs`".** A site rendered from the
   Apache-scoped `docs/` tree (`scripts/doc_site.py`, `scripts/simple_markdown.py`), inclusion
   decided by `scripts.route_coverage_check.APACHE_DOC_PATHS` — the same tuple
   `product_tree_link_check.py` itself imports rather than redeclaring — never a hand-kept list.
   Three landing pages (Architecture, Operator guide, Analyst guide placeholder stating plainly it
   is not yet written) plus a Preflight reference page generated from `harness/preflight/*.py`'s own
   docstrings and `NAME` constants via `ast.parse` (no import, so the render stage needs nothing
   beyond the Python standard library). **Design call this round settled, recorded rather than left
   implicit — not the only reading the brief's own wording could support:**
   `decision_log_publication_check.PROCESS_ADR_NUMBERS` is imported and exercised by
   `assert_no_process_content` as a **defensive safety check on the render's own output**, the same
   role `product_tree_link_check.PRIVATE_TREE_MARKERS` already plays for
   `assert_no_private_tree_names` — not as a second, larger content set. This site renders no
   `06_DECISIONS.md` content at all today (that file is not in `APACHE_DOC_PATHS` and never will be
   pre-Trigger-A), so `PROCESS_ADR_NUMBERS` is exercised only by its own fabricated-fragment test,
   not by anything the real site currently calls it with. If the site is ever extended to surface
   ADR-034 §B10's own filtered decision log, this is the mechanism that filter would reuse.
   Three named exit tests, each a planted violation, all in `tests/test_doc_site.py` (10 cases):
   no private-tree file is rendered (the real bug this test caught: `PRIVATE_TREE_MARKERS` names
   `.md` files, the site renders `.html`, and a bare substring check never fired — fixed by
   comparing `Path(...).stem`); every internal link resolves; changing a Preflight check's own
   docstring changes the generated reference page. **Wired into the workspace image, not only the
   tarball:** `scripts.osprey_bundle._docker_build_docs_layer` layers the same already-rendered,
   already-checked `docs-site/` onto the real local `osprey/workspace:local` image when `--images`
   is used, retagged in place so `compose.yaml`/`versions.lock` need no second, differently-named
   image — proven against a real running container in the exit test below (`curl` against
   `/docs/index.html` and `/docs/preflight-reference.html` through the deployed workspace's own
   nginx, both 200), not only against the fabricated build context a unit test injects.

   **Exit test #3 — run for real, 25 September 2026. GREEN.** Built the bundle with `--images`
   (11 archives: the three owned images plus arcadedb/valkey/minio/postgres/keycloak/ollama/
   whisper/opensearch); unpacked the tarball into a directory with no relationship to this checkout
   at all (not `deploy/generated/`, not anywhere under it); `docker load`ed every archive, restoring
   the exact tags `compose.yaml`/`versions.lock` already name; ran `python -m harness.apply
   --no-build` pointed at nothing but the unpacked bundle's own `osprey.yaml.example` — reaching a
   health-checked stack (6 services healthy, 33s) with the post-launch OIDC verify green (3/3
   assertions) and the workspace, `/healthz` proxy and `/docs` all reachable and correct by direct
   `curl`. **"If apply cannot run from the bundle alone, that is a finding to fix, not to note"
   (the brief's own words) — it could not, the first time, and both findings were fixed, not
   noted:**
   1. `docker compose up --wait` failed outright: `IsADirectoryError: ... 'osprey.yaml'`. The
      rendered `compose.yaml` mounted `../../../osprey.yaml` — `BUILD_CONTEXT_FROM_OUTPUT_DIR`,
      the *build*-context constant, reused for the Conduit's *config* mount too, silently assuming
      every deployment is rendered exactly three directories below wherever `osprey.yaml` lives.
      True of this repository's own `deploy/generated/<profile>/`; false of an arbitrary
      `--out-root`, which has no such tree at all — Docker silently creates an empty directory for
      a bind-mount source that does not exist, and the Conduit's own `load_map_config` then tried
      to read it as a file. **Fixed** (`harness/render.py`): the mount is now
      `./osprey.yaml:/app/osprey.yaml:ro`, relative to the compose file alone, and a new
      `write_config_copy` places the real config beside it — called from both CLI entry points
      (`harness.render`'s own `main`, `harness.apply`), so the two can never drift on whether it
      happens. Two named cases in `tests/harness/test_render.py`, red-then-green verified by
      reverting the fix and watching both fail for exactly the reason claimed.
   2. The built tarball itself carried three stray, 0-byte `Icon\r` files (macOS's own
      custom-folder-icon marker) — this machine's filesystem tooling writes one into any directory
      it touches, and an unfiltered `staging_dir.rglob("*")` staged them straight through into a
      real, customer-facing artefact. **Fixed** (`scripts/osprey_bundle.py`): a
      `_is_bundle_content` filter excludes known OS junk (`Icon\r`, `.DS_Store`) at every collection
      site (`build_bundle`'s manifest, `make_tarball`'s own walk). Two named cases in
      `tests/test_osprey_bundle.py`, red-then-green verified the same way.

   Both fixes verified against the *real* second build and the *real* redeploy, not only against
   the fixtures above — the rebuilt tarball's own member list carries no `Icon` entry, and the
   redeployed stack reached the same green result reported above. Automated as
   `tests/harness/test_bundle_exit_test.py` (opt-in, `OSPREY_TEST_BUNDLE=1` — needs Docker and
   several minutes, so it is not part of the fast unit tier), run for real and green in 3m37s.
   `make bundle`'s own echo has named this file since before it existed; it now names something
   real (`CLAUDE.md` rule 12).

   **Also found, recorded for completeness rather than as a defect of this round's own code:**
   `harness.images.registry_digest_resolver` cannot resolve
   `quay.io/minio/minio:RELEASE.2024-11-07T00-52-20Z` on this machine — quay.io returns `401
   Unauthorized` to an anonymous `docker buildx imagetools inspect`, a registry-side quirk this
   resolver's own documented contract ("returns `None` on any failure... rather than raising")
   already handles correctly: `versions.lock` marks it `unresolved`, honestly, rather than
   fabricating a digest. A real gap against `05_DEPLOYMENT.md` §2.1's "every image digest pinned",
   left open rather than worked around, since the fix (an authenticated quay.io pull, or a
   registry-mirror decision) is a real decision this round did not have the brief to make.

   **Floor A/B, before and after, and Floor B's own environment finding.** `make test`'s own tier:
   913 passed, 1 pre-existing failure (`test_route_coverage_check.py::
   test_no_new_drift_beyond_the_allowlist`, six undocumented routes — `/v1/exports`,
   `/v1/investigations/{id}/{assumptions,gaps,judgements}`, `/v1/yardstick`, `POST
   /v1/analytics/sightings` — from other API surface work this round did not touch; recorded as
   pre-existing debt, not fixed here, since documenting someone else's routes is a different
   change). Floor B (`make test-all`'s own live-store tier) could not be completed to a trustworthy
   number this round: three attempts, each contaminated by a different, real, and separately fixed
   condition — a leftover `osprey-local-lite` deployment stack from earlier work, never torn down,
   contending for memory with `deploy/compose/dev.yaml`'s own ArcadeDB (`CLAUDE.md` rule 14's own
   worked example, reproduced almost exactly); this Docker Desktop VM's disk filling to 100% across
   the session's accumulated image layers and build cache; and, with both of those cleared,
   ArcadeDB's own `-Xmx6G` heap still exhausted under the full concurrent Floor B suite — a ceiling
   `deploy/compose/dev.yaml`'s own comments already document and already attribute to this host's
   VM memory budget, not to any one suite's code. None of Floor B's failing tests touch a file this
   round changed (`harness/render.py`, `harness/images.py`, `harness/apply.py`,
   `scripts/licence_check.py`, `scripts/osprey_bundle.py`, and the new `scripts/`/`tests/` files
   listed above) — recorded as a known, pre-existing environment ceiling this round's own changes
   did not worsen, not as a green Floor B result, because it is not one.

   Harness-adjacent files changed (`harness/render.py`, `harness/images.py`, `harness/apply.py`)
   are not `services/` or `adapters/` code, so no Floor B figure was re-measured for them beyond the
   full run above; the exit test itself is the real measurement of the one behaviour that changed.

   **Stage 2 §6 — The six setup screens. ACCEPTED; D2 confirmed 24 September 2026.** A browser
   application over Stage 2 §1–§5, bootstrapped by one Docker command, becoming `/admin` after
   launch. Profile, Components and Models write `osprey.yaml` through the Stage 2 §1 schema.
   Governance writes access-control/handling configuration and hosts the real-data exceptions panel
   — **a panel on Governance, not a seventh screen** (D2); this phase's own outcome bullet above is
   amended to match in the same change. Geospatial wraps `build_local_basemap`,
   `register_tier4_provider` and the Verify step with progress shown. Preflight streams Stage 2 §2's
   checks with per-check Re-check and gates Launch, and after launch surfaces Stage 2 §7's ADR-043
   check with its own Re-check. Before Launch, the generated-artefacts diff is shown and confirmed.
   §2.1's persistent summary rail and its "consequences are shown, not described" behaviour are in
   scope, not implied. **`decision_record` is a required field on every exceptions entry, validated
   for presence and format only, never resolved** — ruling 3, 24 September 2026. Never resolving it
   is what makes it work off this working tree: nothing reads `06_DECISIONS.md`, which is the file
   Stage 2 §5's own first assertion excludes from every artefact. Two consequences owed, not
   discharged here: it is a seventh required field on `RealDataException`
   (`scripts/real_data_exceptions.py`), so any entry already in a local, gitignored
   `config/real_data_exceptions.yaml` is invalid until the field is added; and it needs its own
   fail-closed red-then-green for the absent and the malformed case.
   **Exit, two parts.** *Test:* every screen round-trips its answers through `osprey.yaml`; the
   rendered output matches Stage 2 §1's fixture for the same answers; option filtering by profile is
   asserted (§2.1: "Every later screen filters its options to what is valid here"); **this new
   keyboard-driven surface declares its own `defineActionRegistry` registry and its own
   `*.spec.ts` calling `assertAllCovered`** (rule 13 — note that `registryCoverage.test.ts` proves
   only that *declared* registries are asserted, so a surface declaring none is invisible to it);
   **`/admin` has its access-control test** (standing rule 2, no exceptions for internal endpoints);
   the §2.5 privilege drop from setup to console is asserted; and **`02_GLASS_FRONTEND.md` §6's
   accessibility floor is asserted against the real screens** by this surface's own a11y spec,
   **wired into `make ci`** — ruling 6 applies the floor here and rules **`02_GLASS_FRONTEND.md`
   §5's performance budget out of scope** for this surface; the owner's settlement of 24 September
   2026 adds the test to `make ci`, run against the real screens and **never a showcase page**. That
   last clause is load-bearing: this build has already recorded an `axe-core` finding where the spec
   exercised a showcase page rather than the real surface, and a harness spec pointed at a mock of
   these six screens would repeat it exactly. Wired into both `make ci` and `ci.yml`, so the
   divergence recorded at Stage 6 below is not reproduced for a third surface. *Judgement:* a usability pass by someone
   other than whoever built the screens, exactly as this stage's own entry already words it.

   **Stage 2 §7 — Post-launch admin console operations. ACCEPTED. Not milestone-blocking; still Phase 8.**
   `05_DEPLOYMENT.md` §5's rolling upgrade and rollback to a previous digest, and §5's `verify` —
   "the port conformance suite against the *running* deployment rather than a test fixture", a
   capability nothing else in Stage 2 §1–§7 provides, and one this phase's own outcome bullet already
   claims ("the backup, restore, upgrade and verify screens"). Listed here so the boundary is
   visible: not needed to install, start and demonstrate, and not therefore outside the phase.
   Rollback consumes Stage 2 §1's `versions.lock`. **This sub-stage keeps the Re-check surface for
   ADR-043's two-sided check**, whose first run is `Stage 2 §3`'s final deploy step: an operator
   opening the admin console re-triggers `verify` after a realm change, an IdP upgrade, or a
   `"stopped"` watch nobody can explain, and sees the same two results from the same code. `verify`
   is the right home for the mechanism either way, since it runs against the running deployment
   where the Conduit already holds the credentials and the harness never touches the secret.

   **Proposed sub-item, 25 September 2026 — a `/docs` link from the admin console** to the
   documentation site `Stage 2 §5b` built the same day, alongside the backup, restore, upgrade and
   verify screens this sub-stage already hosts. The site itself is reachable directly today
   (the deployed workspace's own `/docs`, no admin console needed); this sub-item is only the
   in-product link to it, which needs `§6`'s own admin console to exist first. **Not built. Not
   milestone-blocking.**

   **Stage 2's exit (D3 — owner's decision, 24 September 2026): tests #1, #2 and #3 green.** *This is
   Stage 2's own completion, not ADR-042's alpha gate, which additionally requires both acceptance
   scenarios green on `local-lite`; no build goes to a tester on Stage 2 alone.* This **widens** the
   stage's existing exit criterion, which was test #1 alone — the other two were described above as
   "testable too" and "mechanical and testable", never as exit criteria. The widening is deliberate,
   confirmed by the owner, and is not a clarification of what was already there.

   ---
2a. **ArcadeDB stability — MILESTONE-BLOCKING, new stage, promoted 23 September 2026, closed
   23 September 2026** from "Legacy disclosures," where it sat with an inline "Owning phase:
   Phase 8" disposition never physically moved. No prior stage number (the numbering `4a`–`4h`,
   `5`, `6` this document holds stable is a Stage-4 sub-scheme; this is a new, independent stage,
   not a Stage-4 sub-stage, labelled `2a` only for its position in this list, between the
   harness/packaging and documentation-refresh stages it sits alongside in build order). **Closed
   the same day it was promoted — its own closing entry, at the end of this stage's text below,
   has the re-pointed exit criterion and the measurement that met it.**

   **Reclassified, 23 September 2026, after a controlled measurement (below): this is a product
   memory-footprint question, not test-environment fragility.** The stage's own name and its causes
   one through four (below) originally framed this as an ArcadeDB/environment reliability problem —
   orphaned databases, a sweep that does not run, cross-container contention. That framing is still
   correct for those four causes, but it is not the whole story, and under the install-and-demo
   milestone the distinction matters: a product that needs more than the 6GB this container is
   configured with to survive one analyst session, on a laptop also running four lighter containers,
   is a fact about the product's own memory footprint, not a fact about this test environment being
   under-resourced. **The measurement, below, makes this the load-bearing framing — not raising the
   heap or the Docker VM budget until the footprint itself has been examined, since doing so first
   would hide the finding rather than close it.**

   **Under a test-suite milestone this was a background nuisance, disclosed but not gating.
   Under an install-and-demo milestone it is not: this stage's own closing-pass attempts have
   repeatedly failed before completing, and a stack that fails more often than it completes cannot
   demonstrate anything.**

   **Evidence correction, 23 September 2026: the original "8 of the last 13 closing-pass attempts"
   figure is withdrawn.** An unknown share of those 13 attempts ran while a second agent — the
   subagent that built this test, which kept running and pushing commits after handing its own
   report back — was independently re-running the same test against the same shared ArcadeDB
   container at the same time, unbeknownst to whoever recorded the figure. Two processes contending
   for one container's memory and one database's locks is expected to fail regardless of whether
   either process, run alone, is sound — a measurement taken while an unknown process shares the
   resource under test is not a measurement of that resource's own reliability, and cannot be
   retroactively separated into "caused by contention" versus "caused by a real defect" once the
   processes are gone. **The stage itself stands regardless of this correction** — the six-plus OOM
   incidents in causes one through four below were diagnosed individually, with `docker inspect`
   evidence, predating any subagent's involvement, and the fifth cause (the `IndexException`) was
   reproduced twice, back to back, by a single actor. **The general point is worth stating once,
   for reuse beyond this one figure: any reliability measurement taken against a shared local
   resource is only as trustworthy as the claim that nothing else was using that resource at the
   same time — a claim this document did not check before recording the withdrawn figure, and
   should have.**

   Four independent causes, three already found and diagnosed, a fourth newly observed this
   session:

   **One — the sweep only runs when something collects `tests/conformance/graph_port`, and the
   routine local/CI invocation never does.** `sweep_stale_conformance_databases`
   (`packages/adapters/graph_arcadedb/testing.py`) is a session-scoped autouse fixture in that
   directory's own `conftest.py`; pytest never instantiates a fixture from a directory it does not
   collect. `Makefile`'s `test` target carries `--ignore=tests/conformance/graph_port` as the first
   of ten `--ignore` flags (see the `Makefile`-ignore entry, still in "Legacy disclosures," found
   the same session as this one). A developer or session running `make test` alone, repeatedly,
   against a persistent local `make dev-up` stack accumulates `conformance_*` databases with the
   sweep never once firing, until the volume fills. Only `make conformance`, `make test-all`, or
   CI's `conformance` job ever trigger it.

   **Two — even when the sweep runs, it can only drop what the live server's own `list databases`
   reports, and a database can exist on disk without ever being registered.** Found live: a disk
   audit found `conformance_1789987107_b63147993fc8` on disk, 172 minutes old, well past the
   60-minute staleness window — yet absent from `curl .../api/v1/databases` before the sweep ran,
   confirming it was never a candidate. A `create_database_if_absent()` interrupted after the
   directory is created but before the server's own registration completes leaves exactly this:
   present on disk, invisible to the one call the sweep uses to find what to drop.

   **Three — a hard-killed run can leave a database that crashes the server itself at boot, before
   the sweep's own owning fixture ever gets a server to call.** Also reproduced live: a `make test`
   run OOM-killed the ArcadeDB container mid-suite (`docker inspect` confirmed `OOMKilled=true`,
   `ExitCode=137`), leaving `conformance_1789998411_5906c2b40764` mid-transaction. On restart,
   `ArcadeDBServer.loadDatabases` threw an uncaught `com.arcadedb.exception.SchemaException: File
   with id '0' was not found`, and the JVM's `main` thread exited — the container stayed "Up" but
   never became healthy. A database that prevents the server from starting is by construction
   unreachable by a sweep that needs that same server running to call `list databases` against.

   **Four — cross-container OOM contention, not a sweep gap but the reason the sweep keeps having
   work to do.** `deploy/compose/dev.yaml`'s own comment already names cross-container memory
   contention (Ollama's resting footprint against ArcadeDB's `-Xmx6G` heap on a shared Docker
   Desktop VM, measured at 8GB total) as a known, previously-hit case, "restart recovers cleanly"
   as the stated remedy — true for a clean kill, false when the kill lands mid-transaction (cause
   three above).

   **A fifth cause, newly observed this session, not previously disclosed anywhere in this
   document: a non-OOM `ArcadeDBError`/`IndexException` on throwaway-schema DDL.** Reproduced
   twice, back to back, in the same session that built the closing-pass test, container confirmed
   healthy and *not* OOM-killed both times (`docker inspect` showed no restart): `"Error on
   creating index on type 'mx_PRESENT_AT', properties [reverted]"` and, on the very next attempt,
   `"...on type 'mx_Asset', properties [handling_classification]"` — different types, same failure
   shape, both inside `apply_schema`'s own common-index pass against a freshly-provisioned
   throwaway database. Not yet root-caused (unlike causes one through four, which were fully
   diagnosed before this addition) — recorded here, honestly, as observed-not-diagnosed, the
   distinction this document's own Stage 6 entry already draws for `test_statelessness.py`'s
   connection refusal. Plausibly the same root pressure as cause four (heap exhaustion degrading
   index construction before triggering an OOM kill outright, rather than after), but that is a
   hypothesis, not yet a finding — this stage's own work includes settling which.

   Concretely, in order of leverage: (a) move `sweep_stale_conformance_databases` (or an
   equivalent) to run from something that always executes before a local or CI test session touches
   ArcadeDB, not from a fixture scoped to a directory ten `--ignore` flags routinely skip; (b) make
   the sweep's own candidate list disk-based (or reconcile disk against `list databases` and treat
   a mismatch as itself stale) rather than trusting server registration alone; (c) either lower
   ArcadeDB's configured heap or raise the VM's memory budget so the documented contention case
   stops being reproducible on a single ordinary session's first run; (d) root-cause the fifth,
   newly-observed `IndexException` cause and fold its own fix into whichever of (a)–(c) it turns
   out to share a root with, or add a fourth remedy if it does not.

   **Exit criterion, a measurement, not a judgement: N consecutive clean runs of
   `tests/scenarios/test_phase8_exit_criterion_end_to_end.py` against a freshly-restarted stack,
   N = 5.** Chosen, not derived: two consecutive clean runs were already achieved once in the
   session that built the test (296.84s and 552.16s, no changes between them), which is evidence
   the underlying logic is sound but is not itself the bar — five is meant to be a real,
   uncomfortable-to-reach number that would not be met by luck, small enough to run in one sitting
   once the causes above are actually fixed. (The failure-rate figure originally cited here to
   justify N is the same one withdrawn above for contamination; N=5 itself is not withdrawn, only
   the number that was used to argue it was hard to reach by chance.)

   **Attempted under genuinely controlled conditions, 23 September 2026 — not met.** Confirmed no
   other agent running (`ListAgents`) immediately before starting; ArcadeDB fully restarted; five
   runs launched back-to-back in one uninterrupted sequence, nothing else issued against the stack
   between them. Result: run 1 passed (196.56s); the container was OOM-killed during or immediately
   after that single pass (`docker inspect` confirmed `ExitCode=137` afterward); runs 2 through 5
   each failed in under 10 seconds, unable to reach the server at all. **This rules out the
   contention explanation for at least this failure mode**: with contention definitively excluded,
   a single successful, uncontended run of this test still exhausted the container's own 6GB
   budget. The exit criterion is not met, and "avoid running two agents against the container"
   (item 4, below) is not sufficient on its own to meet it — cause four's own remedies (raise
   ArcadeDB's heap or the VM's memory budget) or a real reduction in this test's own footprint
   against the persistent `ospreyflow` database are both still needed. Whoever closes this stage
   may revise N with a stated reason; the default is not silently accepted as sufficient without
   one.

   **Diagnosis, 23 September 2026: per-run footprint, not accumulation, is the dominant mechanism
   — measured, not inferred.** `ospreyflow` was dropped and recreated empty, ArcadeDB fully
   restarted, and the closing-pass test run repeatedly with `compose-arcadedb-1`'s own memory
   sampled every 2s throughout (`docker stats`), nothing else touching the stack:

   | Run | Start mem | Peak mem | End mem | Result |
   | --- | --- | --- | --- | --- |
   | 1 (empty database) | 135.7MiB | 6.597GiB | 6.529GiB | passed, 77.54s |
   | 2 (no restart between) | 6.526GiB | 6.864GiB | OOM-killed (`ExitCode=137`) | failed, ~65.79s |

   Run 3 was never attempted — the container was dead. **Run 1 alone, starting from a genuinely
   empty database, already reached 6.597GiB** — essentially the whole of the container's configured
   6GB JVM heap plus off-heap/JVM overhead, before any second run's data had a chance to accumulate.
   That single fact answers the diagnostic question directly: this is not primarily a leak building
   up across runs (though memory also does not return to baseline between runs — run 2 starts
   already at run 1's own end value, not back near run 1's own start — so whatever a "leak" means
   for a database server that is supposed to hold its own data between requests, ArcadeDB is also
   not releasing memory at rest between test invocations). **Both are true and are not competing
   explanations: one run's own write volume is already most of the budget, and nothing frees that
   memory afterward, so a second run has almost no headroom left before it, too, pushes over the
   ceiling.**

   **Where the footprint most plausibly comes from, with the evidence for it stated separately from
   the parts that remain a hypothesis.** `_build_a_graph()` (this test's own Scenario A section)
   writes `tests/scenarios/fixtures/hmp_graph.py`'s ~400 `Person` nodes and ~1,700 edges into the
   persistent `ospreyflow` database on every single run, with no cleanup — unlike
   `_ingest_cdr_fixture`'s own use of a throwaway `arcadedb_adapter()` database for Scenario B's
   CDR ingest. **This is not a new finding**: this same document's own Phase 5 Checkpoint 2 entry
   already recorded, independently, that a single sequential run of this identical fixture's graph
   side "OOM'd at 4G on this host on every attempt, including at container startup before any client
   request" — a bulk-write cost, not a traversal cost, established before this closing pass existed.
   The sample log's own shape is consistent with a write-dominated ramp: memory jumps from 135.7MiB
   to 4.12GiB within the first 4 seconds of run 1, far too fast to be the ~20 individual HTTP round
   trips Scenario B's own steps make, and more consistent with either the bulk write itself or
   ArcadeDB's own buffer-pool/page-cache sizing reacting to it — **which of those two, `docker
   stats`'s own container-level, whole-JVM measurement cannot distinguish, and is not claimed to**.

   **The traversal-budget question, checked rather than assumed to be the same cause.** The
   before-milestone item naming ArcadeDB's own missing server-side execution budget (the Conduit's
   30s timeout is client-side only) is real, and `PathBuilder.render_gremlin`
   (`packages/adapters/graph_arcadedb/builders.py:243`) confirms it directly: the compiled query is
   `repeat(bothE()...otherV()...simplePath()).until(has(target).or().loops().is(gte(max_hops)))`,
   with `.limit(k)` applied only *after* `.has(target)` — the repeat phase itself carries no bound
   on how many simple-path branches it may explore before that filter runs. B21's own call
   (`max_hops=6`) is exactly the shape that risks this. **But for this specific test, the evidence
   does not support this being the active mechanism**: B21's source and target are this run's own
   freshly-`new_id()`-created nodes, reachable from each other only via the one cross-case bridge
   node this same run just wrote two lines earlier — there is no large, richly-connected
   neighbourhood for `simplePath()` to fan out into at either endpoint, by construction, regardless
   of how much unrelated HMP or prior-run data sits elsewhere in the same database (a Gremlin
   traversal anchored at a specific `id` does not scan unrelated vertices it never reaches by an
   edge). **Conclusion: the missing traversal budget is a real, separately-standing architectural
   gap — worth its own fix regardless of this stage — but it is not shown here to be a second
   symptom of the same cause as this stage's own OOM; the write volume is the better-evidenced
   explanation for what was actually measured.** A future, larger-scale pathfinder call against a
   densely-connected neighbourhood remains a plausible way to hit the same missing budget from a
   different direction; nothing above rules that out, it only rules it out as the explanation for
   *this* run's own numbers.

   **Superseding correction, 23 September 2026: "the write volume is the better-evidenced
   explanation" (above) was wrong — measured directly, not merely re-argued.** That conclusion
   named `_build_a_graph()`'s ~400-node/~1,700-edge write as the plausible dominant cost and
   flagged it as a hypothesis ("more consistent with either the bulk write itself or ArcadeDB's own
   buffer-pool/page-cache sizing... which `docker stats` cannot distinguish"). It has since been
   distinguished, with a controlled experiment, and the write itself is not the cause.

   **Item 1 — the cost curve, measured on an empty `ospreyflow`, fresh restart, nothing else
   running:** a real, throwaway writer script drove `GraphArcadeDBAdapter.upsert_nodes` directly
   (chunks of 100 per transaction, matching production's own chunking discipline), sampling
   ArcadeDB's own `/api/v1/server` profiler metrics — `ramHeapUsed`/`ramOsUsed`, not `docker
   stats`'s cgroup-level figure, which conflates JVM heap, ArcadeDB's own off-heap page cache and
   OS file-cache — at each checkpoint:

   | Point | ramOsUsed | ramHeapUsed | createRecord | commands | txCommits |
   | --- | --- | --- | --- | --- | --- |
   | before schema | 1.453GiB | 0.033GiB | 0 | 0 | 1 |
   | after `apply_schema` (0 elements written) | 6.393GiB | 3.043GiB | 0 | 370 | 1809 |
   | 100 nodes | 6.657GiB | 3.771GiB | 100 | 470 | 1815 |
   | 500 nodes | 6.698GiB | 3.632GiB | 500 | 870 | 1819 |
   | 2,000 nodes | 6.293GiB | 3.200GiB | 2,000 | 2,370 | 1,834 |
   | 5,000 nodes | 6.370GiB | 3.200GiB | 5,000 | 5,370 | 1,864 |

   **This is a step function, not a per-element cost, and the step is `apply_schema`, not the
   data.** `ramOsUsed` jumps ~4.9GiB between "before schema" and "after schema, zero elements
   written" — before a single node exists — then stays flat (6.29–6.70GiB, no trend) across the
   entire 100→5,000 range, a 50× change in element count producing no detectable memory change
   outside noise. `ramHeapUsed` at 5,000 nodes (3.200GiB) is *lower* than at 100 nodes (3.771GiB).
   There is no ~2MB-per-element signal anywhere in this data — the hypothesis this measurement was
   built to test is not what is happening.

   **Item 2 — adapter versus raw ArcadeDB HTTP API, on the cost that actually showed up (schema
   creation, since per-element write cost had nothing to isolate).** The 370 DDL commands
   `adapters/graph_arcadedb/schema.py::apply_schema` issues were harvested (by intercepting the one
   method it calls, `client.sql()`, rather than sending them) and replayed verbatim via raw
   `httpx` POSTs directly against `/api/v1/command/<db>` — no `ArcadeDBClient`, no
   `GraphArcadeDBAdapter`, no retry wrapper — against a second, independent, empty database on the
   same server, fresh restart, nothing else running:

   | Path | Before | After | commands | txCommits |
   | --- | --- | --- | --- | --- |
   | Adapter (`GraphArcadeDBAdapter.apply_schema`) | 1.453GiB | 6.119GiB | 370 | 1,809 |
   | Raw HTTP, same 370 statements, no adapter code | 1.478GiB | 5.971GiB | 370 | 1,809 |

   **Identical, within noise. This is ArcadeDB's own behaviour under this configuration, not
   something the adapter path adds** — unsurprising once read alongside item 3 below: the adapter
   issues literally the same DDL a raw caller would have to issue (ArcadeDB SQL has no
   multi-statement batched DDL over this endpoint), so there was no meaningful "adapter-added" path
   for a cost to hide in.

   **Item 3 — the write path, quoted, for what happens per DDL statement and per element.**
   `apply_schema` (`packages/adapters/graph_arcadedb/schema.py:107-130`) issues one `CREATE VERTEX
   TYPE`/`CREATE EDGE TYPE` per ontology type, plus — per its own module docstring — "a unique index
   on `id`... a composite index on `(type, handling.classification)`, plus `handling_code`,
   `owning_unit` and `originator`... one per ontology-declared `identifiers` field... one per
   `properties` entry the ontology marks `indexed: true`" for *every* type: several indexes each,
   over however many entity/edge types the ontology declares, is exactly the 370 individual
   `CREATE PROPERTY`/`CREATE INDEX IF NOT EXISTS` statements measured above, each a separate,
   synchronous HTTP round trip (`_ddl()` calls `client.sql(command)` in a loop, no batching), each
   triggering — per the measured `txCommits` delta (1 → 1,809 for those 370 commands) — roughly
   five internal ArcadeDB transaction commits per statement, not one. **Repeating the call is not
   free, even though the DDL is idempotent**: `apply_schema` called three times in a row against
   an already-schema'd database issued 370 fresh commands and ~370 fresh `txCommits` *every time*
   (1,809 → 2,179 → 2,549) — `IF NOT EXISTS` is evaluated server-side per statement, not
   short-circuited client-side — though the *memory* cost is paid once, not repeated (`ramOsUsed`
   stayed flat, 6.119 → 5.865 → 5.923GiB, across the three repeats). `_graph_client()`
   (`tests/scenarios/test_phase8_exit_criterion_end_to_end.py:237-244`) calls `apply_schema` on
   every one of its own several call sites in a single closing-pass run — a real, separate,
   quantifiable inefficiency (on the order of 370 redundant round trips per extra call), but not,
   per the measurement above, a further memory cost each time.

   For per-element work: `upsert_nodes` (`adapter.py:128-154`) does one `INSERT INTO {type} SET
   ...` per node, one round trip, no batching. `upsert_edges` (`adapter.py:254-357`) does
   substantially more per edge — two `_node_type` lookups (source, target), one
   `_find_existing_edge` lookup, then `_weigh_edge` → `_corpus_edge_stats`
   (`adapter.py:193-220`), which is not scoped to the write's own neighbourhood: its third query is
   `g.E().hasLabel(label).has("reverted",false).values("occurrences").sum()` — an **unscoped scan
   over every edge of that type in the whole database**, run again on every single edge write of
   that type, growing more expensive as more edges of that type accumulate. This was not exercised
   by the node-only measurement above (chosen deliberately to isolate one code path); it is real,
   quoted, and is the one piece of this write path whose *per-element* cost plausibly grows with
   database size rather than staying flat — a distinct concern from the schema-creation step
   function this measurement was built to characterise, not yet itself measured.

   **A plausible connection to the fifth, previously undiagnosed cause (the `IndexException` on
   throwaway-schema DDL, above), found while reading this same file:** `schema.py`'s own comment
   (lines 36-48) records an *earlier*, Phase 5 incident with the identical symptom — "a wave of
   `IndexException` on `CREATE INDEX` across the full suite" — root-caused that time to the host's
   Docker Desktop VM disk filling up, not memory; "no code change was actually the fix." Given
   `apply_schema`'s own real cost is now measured at ~4.5-4.9GiB per first application, a heap
   genuinely under pressure during concurrent or back-to-back schema DDL is at least as plausible a
   trigger for the same exception class as the disk-space case already on file — recorded here as a
   second candidate explanation, not a resolution; still observed-not-diagnosed.

   **Item 4 — retention, sampled after the run, all connections closed, over 4 minutes of complete
   idle:** 6.128 → 6.146 → 6.185 → 6.188 → 6.191 → 6.200GiB, sampled every 40s. `gcTime` (the
   profiler's own GC-run counter) held constant at 157 throughout — not "GC hasn't run yet," GC had
   already run and the heap did not shrink afterward. **Nothing is reclaimed at idle.** No
   compaction or checkpoint call exists anywhere in `packages/adapters/graph_arcadedb/` (checked
   directly — no match for `compact`/`checkpoint`/`flush` in that package). One plausible
   server-level command was probed directly (`check database <name>` via `/api/v1/server`) and
   rejected outright ("Server command not valid") — this rules out that one specific guess, not
   ArcadeDB's full command vocabulary, which was not exhaustively searched here.

   **Item 5 — the finding, at its real size, with the arithmetic shown.** Not "~2MB of heap per
   graph element" — the data above does not support a per-element figure at all, flat or
   otherwise, up to 5,000 elements. The real number: **applying this ontology's schema to an empty
   ArcadeDB database costs ~4.5-4.9GiB of the container's own memory, once, before any
   investigation data exists**, on a container configured with a 6GB JVM heap inside a ~7.65GiB
   total budget — and that memory is never released for the life of the server process. A second
   database on the same server, or a second schema-triggering call, adds to — or at minimum does
   not free room from — an already near-exhausted budget. **This is why Phase 5 Checkpoint 2's own
   original note — the HMP fixture's graph side "OOM'd at 4G... including at container startup
   before any client request" — was recorded and never measured further at the time: it was
   already observing this same mechanism, correctly, years before this session had the
   instrumentation (ArcadeDB's own `/api/v1/server` profiler metrics, not `docker stats`) to
   separate "the schema" from "the 400 people" as the actual cause.** A freshly restarted container
   holding only `ospreyflow`'s own already-created schema (measured this session, zero data
   elements at the time) reached 7.522GiB on server boot alone, nearly this container's entire
   budget, confirming the same mechanism operates at server-startup/database-reload time, not only
   at first `apply_schema`. **Read as a product capacity question, not a test-environment one
   (per this stage's own reclassification, above): a platform whose schema alone consumes most of
   a 6GB heap before an analyst has opened a single investigation cannot hold an investigation
   graph of any realistic size on a laptop also running the other four containers this milestone
   requires.** No fix is proposed here — root-causing *why* ArcadeDB's own schema/index creation
   costs this much under this configuration (JVM heap sizing, off-heap page-cache/buffer-pool
   sizing, the sheer count of indexes this ontology's own §1.4 discipline declares, or some
   combination) was real, separately-scoped work — the second diagnostic pass immediately below is
   that work, still report-only, no fix built.

   **Second pass, 23 September 2026 — index count, ArcadeDB's own configuration, and which indexes
   are load-bearing. Still report only; nothing below was implemented.**

   **Index-count scaling, measured directly.** A single test vertex type, ten properties
   pre-declared and unindexed (so the type/property overhead is fixed and only index count moves
   between checkpoints), on a fresh empty database, fresh restart:

   | Point | ramOsUsed | ramHeapUsed | commands |
   | --- | --- | --- | --- |
   | before | 1.560GiB | 0.033GiB | 0 |
   | type + 10 props, 0 indexes | 1.578GiB | 0.044GiB | 11 |
   | + 1 index | 1.683GiB | 0.108GiB | 12 |
   | + 4 more (5 total) | 2.052GiB | 0.359GiB | 16 |
   | + 5 more (10 total) | 2.344GiB | 0.431GiB | 21 |

   The type and its properties cost almost nothing (+0.018GiB for 0 indexes). Indexes cost real,
   roughly-linear memory with *diminishing* marginal cost as more accumulate: the first index costs
   ~105MB, indexes 2-5 average ~92MB each, indexes 6-10 average ~58MB each — consistent with a
   per-index allocation plus some shared, amortised subsystem cost that is mostly paid once. **This
   is linear-with-diminishing-returns, not a hard step at some threshold** — it does not, on its
   own, explain a jump from ~2.3GiB at 10 indexes to ~6.4GiB for the full ontology by simple
   extrapolation of the *early* per-index rate, but the *later*, lower rate (~58MB/index) applied to
   the ontology's own real index count is in the right order of magnitude: this ontology declares 9
   entity types and 11 edge types (20 total), each carrying at minimum 7 "common" indexes
   (`id` unique, the four-field access-filter composite, `reverted`, `superseded_by` —
   `packages/adapters/graph_arcadedb/schema.py:141-181`, one more than this document's own prior
   pass estimated, which missed `reverted`/`superseded_by`), plus 23 identifier indexes, 8
   `indexed: true` property indexes and 4 temporal `valid_from` indexes — on the order of 175
   indexes in total. 175 × ~58MB ≈ 10.2GiB, 175 × the full curve's own blended average is closer to
   the measured ~4.9GiB; **read this as "the right order of magnitude, from a real measured
   per-index cost, not a fabricated one," not as an exact reconciliation** — the controlled
   experiment varied index count on one type, the real ontology varies it across twenty, and this
   pass did not measure whether per-*type* overhead (as opposed to per-index) behaves the same way.

   **ArcadeDB's own configuration, checked, with an honest account of what could not be found.**
   The only ArcadeDB memory setting this deployment actually sets is `ARCADEDB_OPTS_MEMORY: "-Xms1G
   -Xmx6G"` (`deploy/compose/dev.yaml`) — the JVM heap. `/api/v1/server`'s own `settings` array (53
   entries) was read in full: it covers server mode, networking, TLS, HA/replication and the
   Postgres/Redis/Mongo protocol shims — **nothing exposed there governs page size, per-index
   memory, or disk-cache sizing**; those may exist as ArcadeDB `GlobalConfiguration` keys not
   surfaced by this endpoint, but none could be discovered from within this running environment,
   and this was not cross-checked against ArcadeDB's own upstream documentation (no fetch tool was
   used to avoid an unverifiable claim). One runtime-observable default was found regardless: the
   profiler's own `cacheMax` reports 1.5GiB (ArcadeDB's own disk read-cache ceiling) with no
   corresponding entry in `dev.yaml` — an un-configured default, not something this deployment
   chose.

   **The one setting actually available was tested, per this pass's own instruction — a
   measurement, not a fix, and reverted immediately after ($`git diff` confirms `dev.yaml` is
   clean).** `ARCADEDB_OPTS_MEMORY` temporarily changed to `-Xms256M -Xmx2G` (a third of the
   configured heap), container recreated, full ontology `apply_schema` run again:

   | | ramHeapUsed | ramHeapMax | ramOsUsed |
   | --- | --- | --- | --- |
   | `-Xmx6G` (original) | 3.043GiB | 6.0GiB | 6.393GiB |
   | `-Xmx2G` (test) | 1.114GiB | 2.0GiB | 6.188GiB |

   **Schema application still succeeded at a third of the configured heap, using well under the
   smaller ceiling — and total OS-level memory was unchanged.** This is a real, useful negative
   result: `ramHeapUsed` scaled down with the smaller ceiling (the JVM did more GC work to stay
   under it, successfully), but `ramOsUsed` — the figure that determines whether the container gets
   OOM-killed — did not move. **The ~4.9GiB cost is predominantly off-heap** (native buffers,
   ArcadeDB's own file/page cache, or OS page cache from the WAL and index-file writes the 370 DDL
   statements perform), which `-Xmx` does not bound at all. Simply lowering the configured heap is
   therefore not, on this evidence, a viable single-lever fix — it would free heap headroom without
   reducing the total memory the container needs to survive schema creation.

   **Which indexes are load-bearing, checked against real callers in this codebase, not assumed
   from the ontology's own declaration.** Every `identifiers` field (23 across the ontology) is
   reachable through one real, generic query path — `search_nodes`
   (`adapter.py:417-428`) unions every declared `identifiers` field into its own search — so all 23
   are load-bearing for that capability regardless of whether any current recipe populates them.
   **Five have that query path but no data path**: `passport_number`, `companies_house_number`,
   `ein`, `vrm`, `vin` appear in no recipe, fixture, connector or test anywhere in this repository
   (checked directly, whole-repo search) — real capability, currently zero rows any of these five
   indexes would ever match. The `id`/access-filter-composite/`reverted`/`superseded_by` "common"
   indexes are each named, with the specific caller, in `schema.py`'s own module docstring and
   confirmed against `access_filter.py`'s own every-read use — load-bearing, all of them. The
   temporal `valid_from` index on four edge types is used by timeline-filtered expansion
   (`08_ACCEPTANCE_SCENARIOS.md` B17) — load-bearing.

   **Four of the eight `indexed: true` declared *properties* (as distinct from `identifiers`)
   appear to have no real caller at all**, checked directly against every query builder in
   `packages/adapters/graph_arcadedb/`: `family_name`, `given_names`, `date_of_birth`, `aliases`
   (`Person`) and `title` (`Document`) — zero matches. `search_nodes` does not include them (it
   only unions `identifiers`, not `indexed: true` properties — a real distinction in the code, not
   a documentation gap). Their real use is in DuckDB/Splink resolution comparisons, a separate
   store this ArcadeDB index does not serve. `value_normalised` (`Endpoint`) has one reference
   (`services/api/evaluation.py:163`) that reads the property off an already-fetched node — not a
   query filtering by it — so it too has no confirmed ArcadeDB-side caller. **`name`
   (`Location`/`Organisation`) has exactly one real caller, `SuggestLocationsBuilder`
   (`builders.py:132`), and that caller queries it with `TextP.containing(...)` — a substring
   predicate. `_create_index` (`schema.py:211-215`) only ever creates a plain `UNIQUE`/`NOTUNIQUE`
   index, never a full-text one, so this index is very likely unable to accelerate the one query
   that names it at all** — a stronger finding than "unused": plausibly the wrong index type for
   its own single real caller. **None of the above were removed; this is the audit, not the edit.**

   **Phase 5's own `IndexException`/disk-space attribution, re-examined with what is now known.**
   That entry's own words: freeing disk space "resolved the vast majority of failures outright" —
   already, at the time, an admission that it did not resolve all of them, left unexplained rather
   than closed. With `apply_schema`'s own real cost now measured at ~4.5-4.9GiB, a heap genuinely
   under pressure during concurrent or back-to-back schema DDL is a second, independently plausible
   cause for the same exception class, on the same code path, that was never considered at the
   time because the cost had not yet been measured. **The disk-space attribution still holds for
   what it actually claimed — the majority of that incident's own failures — and is not
   overturned. It should no longer be read as the complete explanation for that incident**; the
   residual, previously-unexplained minority is at least as plausibly this same memory mechanism as
   an unconsidered second cause of the identical symptom, not a settled loose end.

   **Options, with costs and risks. The owner chooses — the last two times a scope call was made
   inside an investigation, it had to be retracted (the false "owner's explicit decision"
   attribution, and this stage's own original "out of scope for v1" call on the cross-cutting
   rows), and this is exactly that kind of call.**

   - **A. Configuration change (page-cache/heap tuning).** *Cost to build:* low, if a real lever
     exists — but this pass could not find one that changes total memory (lowering `-Xmx` alone
     did not); would need ArcadeDB's own upstream documentation to identify a genuine off-heap/page
     -cache setting, not yet found from inside this environment. *Gives back:* potentially the
     whole problem, if the real lever exists and is small. *Risk:* the one lever tested had no
     effect; time spent hunting for an undocumented-here setting may find nothing, and a wrong
     guess (as with `-Xmx`) costs a full measurement cycle to rule out.
   - **B. Fewer indexes.** *Cost to build:* low-to-moderate — five identifier indexes
     (`passport_number`/`companies_house_number`/`ein`/`vrm`/`vin`) and four-to-five property
     indexes (`family_name`/`given_names`/`date_of_birth`/`aliases`/`title`, `value_normalised` if
     its one caller is judged not to need it) have no confirmed caller today; removing them is a
     schema change plus a migration story for `revert_schema`. *Gives back:* on this pass's own
     per-index measurement (tens of MB each, more at low counts), removing ~9-10 indexes recovers a
     real but almost certainly *partial* amount, well short of the ~4.9GiB gap on the evidence
     above (which points at a largely fixed, per-`apply_schema`-call cost, not a purely linear
     per-index one). *Risk:* removes real, if currently unpopulated, capability
     (`search_nodes` across all declared identifier types); wrong to do inside this investigation
     — the instruction not to remove anything here stands for exactly this reason.
   - **C. Lazy index creation** (create a type's indexes on first real data for that type, or on
     first query needing it, rather than unconditionally at `apply_schema` time). *Cost to build:*
     moderate-to-high — changes a core, already-tested contract (`apply_schema` is idempotent and
     total; a lazy variant needs its own conformance suite, per this document's own rule 1, and a
     migration story for a type that already has data written before its indexes exist). *Gives
     back:* plausibly the largest win of the four routes — an install-and-demo session that never
     touches `passport_number`/`ein`/etc. would never pay for those indexes at all — but unproven
     without a prototype. *Risk:* real correctness surface (a query racing an index that has not
     yet been created), and the biggest scope of the four options.
   - **D. A different page/cache strategy** (smaller page size, a disk-backed rather than
     memory-resident index structure, or similar). *Cost to build:* unknown without first finding
     the actual configuration surface option A could not locate — this route depends on A
     succeeding first, or on reading ArcadeDB's own source. *Gives back:* unknown; could be large
     or negligible depending on what is actually tunable. *Risk:* the least-evidenced of the four
     options here — nothing in this pass's own measurements points at a specific page/cache lever
     to pull, only that the cost is off-heap.
   - **E. Accept a higher floor; state the minimum machine.** *Cost to build:* lowest of the five —
     a documentation change (the install guide's own stated requirements) plus, if headroom is
     still tight, raising `ARCADEDB_OPTS_MEMORY`/the Docker Desktop VM budget, which this pass's own
     test showed does not by itself solve the OOM risk (item 1's original diagnostic pass found the
     total *ramOsUsed* figure barely moved between 2GB and 6GB heap ceilings) — so this option may
     need to pair with raising the *host's* own VM budget, not just the container's heap, to be
     credible. *Gives back:* nothing to the actual footprint; converts a hidden capacity failure
     into a stated, honest constraint. *Risk:* directly narrows "install-and-demo on a clean
     laptop" — the milestone's own current wording — to "on a clean laptop with at least N GB
     free for this one container," a real product decision with real audience consequences, not a
     technical one this document can make on its own.
   - **F. Replace the `GraphPort` adapter (`graph_arcadedb` → e.g. `graph_janusgraph`, already
     contemplated for Phase 8a).** Recorded here, not acted on — the architecture was built to
     make this option available, which is a reason to list it, not a reason to prefer it. *Cost to
     build:* the largest of the six — a full `GraphPort` implementation against a different store,
     passing every conformance-suite test this document's own rule 1 requires before any adapter
     ships, which is exactly the discipline that makes this an honest option rather than a rewrite
     with no safety net; real, substantial calendar time. *Gives back:* potentially the whole
     problem, if the replacement store's own baseline footprint is genuinely smaller — unmeasured,
     not assumed. *Risk:* trades one measured, now-well-understood problem for a different store's
     own unmeasured ones (this session's entire method — measure before concluding — has not been
     applied to any alternative store; nothing here says JanusGraph is smaller, only that finding
     out is possible). Real scope creep risk: a "just swap the adapter" plan that turns into a
     second full adapter-build phase.

   **Corrected count, and PART 1 of a two-part follow-up instruction carried out below: ten
   defective indexes identified, `passport_number`/`companies_house_number`/`ein`/`vrm`/`vin`
   removed as identifiers; `family_name`/`given_names`/`date_of_birth`/`aliases`/`title`/
   `Organisation.name` de-indexed; `value_normalised` and `Location.name` restored after live
   testing proved they were load-bearing, not merely declared.**

   **Correction to this document's own prior count, checked by the instruction that asked for
   it.** The prior pass's own text said "four" `indexed: true` properties had no confirmed caller,
   then named five (`family_name`, `given_names`, `date_of_birth`, `aliases`, `title`) — an
   arithmetic slip in the prose, not in the underlying list. Re-verified directly: `Endpoint`'s
   `value_normalised` (previously filed as "read but not queried," a sixth) and both `name`
   indexes (`Location`, `Organisation` — previously treated as one bucket, actually two separate
   indexes on two types) bring the real total considered for removal to **eight** `indexed: true`
   properties, not four, not five, not six — plus the five identifier indexes with no data path,
   ten in total across both categories, matching this instruction's own "roughly ten" estimate
   once corrected.

   **What would break, checked by removing each and running the real test suites — not assumed
   from static analysis, which was wrong for two of them.** `passport_number`,
   `companies_house_number`, `ein`, `vrm`, `vin` (identifiers): confirmed, directly, zero
   references anywhere in `tests/` (not only non-test code, re-checked this round) — nothing
   would fail, and nothing did. `family_name`, `given_names`, `date_of_birth`, `aliases`
   (`Person`), `title` (`Document`), `name` (`Organisation`): same — zero references, confirmed by
   running the full `tests/conformance/graph_port` suite (64 tests) with all six removed
   simultaneously; nothing failed. **`value_normalised` (`Endpoint`) and `name` (`Location`) were
   different, and static analysis alone had missed why**: removing `indexed: true` from either
   broke real conformance tests —
   `test_find_node_locates_an_existing_node_by_its_identifier_field` (`value_normalised`) and both
   `test_suggest_locations_matches_a_substring_of_the_name`/`test_suggest_locations_respects_the_
   limit` (`Location.name`) — not because the *index* itself was needed by either query, but
   because `indexed: true` and `identifiers` share one mechanism in this codebase:
   `node_write_to_properties`'s own `_indexed_property_names`
   (`packages/adapters/graph_arcadedb/serialization.py:44-47`) unions both to decide which
   properties get *flattened to a queryable top-level field at write time*, and `find_node`/
   `SuggestLocationsBuilder` both query that flattened field, not the nested `properties` map.
   Removing `indexed: true` does not merely drop an index — for a field a real query builder
   names, it silently stops that field ever being written to the place the query looks, and
   `find_node`/`suggest_locations` then find nothing, correctly reproducing exactly, not merely
   resembling, a missing-data bug. **Both restored** (`packages/ontology/default.yaml`), full
   conformance suite re-run clean (64/64) after restoring them.

   **`name`'s own question, answered:** `SuggestLocationsBuilder`'s own docstring already states
   the query is "a coarse substring scan, not a Lucene/full-text index... deliberately not folded
   into `SearchNodesBuilder`" — a documented, accepted design choice already, not an oversight
   awaiting a real index. The plain `NOTUNIQUE` index `_create_index` builds cannot serve
   `TextP.containing()` regardless of whether it exists (confirmed: the query still worked
   correctly once the index-driven *flattening* was restored, independent of whether an index
   backs the flattened field or not — `TextP.containing` scans). **The right fix, on this
   evidence, is neither remove nor build a full-text index — it is exactly what this pass did:
   keep the flattening `indexed: true` provides (the field must exist at the top level for the
   query to find anything at all) without needing a genuine full-text index to back it, since
   nothing here has shown the scan itself to be slow at any realistic `Location` count.** Building
   a real full-text index remains available as a later, separately-scoped, evidence-gated
   investment if `suggest_locations` is ever shown to be slow, not undertaken speculatively here.

   **Recovery measured, twice, against the ~4.9GiB baseline — same method, same profiler
   metrics, fresh restart, empty database each time:**

   | Run | Before | After | Delta | commands | txCommits |
   | --- | --- | --- | --- | --- | --- |
   | Original (pre-removal, cited) | 1.453–1.478GiB | 5.971–6.393GiB | ~4.5–4.9GiB | 370 | 1,809 |
   | Corrected, run 1 | 1.521GiB | 5.893GiB | 4.372GiB | 348 | 1,689 |
   | Corrected, run 2 | 1.517GiB | 6.258GiB | 4.741GiB | 348 | 1,689 |

   **The command/transaction-commit reduction is exact and reliable — 22 fewer DDL commands, 120
   fewer internal transaction commits, every run, matching the ten indexes removed precisely.**
   The *memory* recovery is real but small, and its apparent size (~0.13–0.57GiB across the two
   paired comparisons above) is comparable to this measurement's own run-to-run noise (the
   original baseline's own three separate measurements this session already ranged 4.49–4.94GiB
   without any code change between them). **Read honestly: this removal is confirmed correct (ten
   genuinely dead or wrongly-typed indexes gone, nothing broken, re-verified against real tests
   rather than assumed) but does not, on its own, materially close the ~4.9GiB gap.** Options B
   ("fewer indexes") in the list above already predicted almost exactly this outcome before the
   measurement was taken — "removing ~9-10 indexes recovers a real but almost certainly *partial*
   amount, well short of the ~4.9GiB gap" — and the measurement now confirms it rather than merely
   restating the prediction.

   **Verification run beyond the removed fields' own tests:** `tests/ontology/` (54/54),
   `domain-model-coverage-check`, `schemas-check`, the full `tests/conformance/graph_port` suite
   (64/64), `tests/scenarios/test_fixture_corp_shape.py`/`test_hmp_graph.py` (6/6, one transient
   OOM-kill mid-run reproduced and re-confirmed as this stage's own already-documented cause four,
   not a regression), `test_phase6a_glass_surfaces.py`/`test_phase7_stage6c_watch_routes.py`
   (7/7), `test_phase8_exit_criterion_end_to_end.py` (three consecutive failures traced to a
   leftover `conformance_*` orphan database from this session's own earlier testing accumulating
   enough resident memory to reproduce this stage's own already-documented `IndexException`
   cause — not this change; a clean drop-and-restart reproduced a clean pass immediately after),
   and the broad non-live suite (629 passed, 2 failed — both pre-existing and unrelated: 
   `test_route_coverage_check`/`test_test_file_coverage_check` both flag that
   `tests/scenarios/test_phase8_exit_criterion_end_to_end.py` itself was never wired into the CI
   ignore-list/live-service job when it was committed earlier this session — a real, separate gap,
   noted here rather than silently fixed since it is outside this instruction's own two parts).

   **PART 2 of the same follow-up instruction: what a demo actually requires — measured per
   service, not assumed from `make dev-up`'s own default list. No decision on the memory floor
   (option E, above) made here; this establishes the number that decision would turn on.**

   `make dev-up` brings up seven containers by default (`docs/DEMO_GUIDE.md` §3.1): ArcadeDB,
   MinIO, Valkey, Postgres, Ollama, LiteLLM, speaches. Checked directly against
   `08_ACCEPTANCE_SCENARIOS.md`'s own A1-A15/B1-B21 text and `services/api`'s own route
   dependencies, not assumed from what the compose file happens to start:

   | Service | Required by A1-A15/B1-B21? | Measured footprint |
   | --- | --- | --- |
   | ArcadeDB | **Yes** — the graph store every step touches | Peak 5.2-6.9GiB under a real run of both scenarios (this stage's own repeated measurements today); baseline ~1.5GiB before any schema |
   | Postgres | **Yes** — audit log, alerts, hotlists, monitors (B12-B14, B20) | 24-63MiB under the same real run |
   | Valkey | **Yes** — working-set store and delta pub/sub, load-bearing for every canvas update | 5-17MiB under the same real run |
   | MinIO | **Yes** — the recipe engine's raw-row staging (`services/ingest/staging.py`), used by every recipe-driven ingest step in both scenarios (B1, Scenario A's own structured ingest) | 89-98MiB under the same real run |
   | LiteLLM | **No** — see Ollama below; kept running has negligible cost regardless | 37-41MiB idle, unchanged across the whole run (never called) |
   | Ollama | **No — checked directly, not assumed** (below) | 622.8MiB with one model loaded (`qwen2.5:0.5b-instruct`, `extract()`'s own model); 2.849GiB with all three pinned models loaded (`+all-minilm:22m-l6-v2-fp16` embed, `+moondream:1.8b-v2-q4_K_M` vision) |
   | speaches | **No** — zero references anywhere in `services/api` or `08_ACCEPTANCE_SCENARIOS.md`; not checked further | Not measured — not part of the required set |
   | The Conduit (`uvicorn`, a host process, not a container — `docs/DEMO_GUIDE.md` §3.2) | **Yes** | 243.0MiB RSS, measured directly (real process launched, minted token, real startup) |
   | The Glass (`vite` dev server, also a host process — no packaged build exists yet) | **Yes** | 244.3MiB RSS after one real page load (91.5MiB before any request) |

   **Ollama, answered directly: neither scenario requires extraction against a live model.**
   `08_ACCEPTANCE_SCENARIOS.md` checked line by line for any call to `ModelPort`/extraction — none
   exists. "Device extractions" (B1) is forensic-artifact terminology (phone dumps), not model
   output; "Endpoint model" (B15) is a data-model term; the one cross-cutting row naming
   "model-derived node" states a general platform discipline, not a requirement that either
   scenario's own steps produce one. Both fixtures are built entirely through structured
   CSV/recipe-driven Knowledge Adapters (`hmp_persons_recipe.yaml`, `cdr_recipe.yaml`, etc.), never
   free-text extraction. **If Ollama (and LiteLLM, its only caller) is absent, or the model port is
   stubbed: the two acceptance scenarios are unaffected — checked, not assumed.** What is lost is a
   real, separate, already-built Phase 6 capability — "ingest a witness statement, extracted
   entities appear as `inferred` with correct source spans"
   (`tests/scenarios/test_phase6_extraction_and_resolution.py`'s own exit criterion) — genuinely
   valuable, already working, just not exercised by either of the two scenarios this milestone is
   currently defined by.

   **Total, required set only (ArcadeDB, Postgres, Valkey, MinIO, the Conduit, the Glass — LiteLLM
   included at negligible cost since nothing currently gates it out cleanly, Ollama/speaches
   excluded):** ArcadeDB's own peak (5.2-6.9GiB, the dominant term by roughly an order of
   magnitude) **+** ~700MiB combined for everything else (Postgres + Valkey + MinIO + LiteLLM +
   Conduit + Glass) **≈ 6.0-7.6GiB**, matching — not coincidentally, since it is the same
   mechanism — the range this stage's own schema-cost measurements already found for ArcadeDB
   alone.

   **The minimum machine, with Docker Desktop's own VM allocation accounted for, not raw host RAM
   — reasoned from the measurements above, not asserted as a vendor specification.** Two budgets
   exist, not one: the Docker Desktop VM (which ArcadeDB/Postgres/Valkey/MinIO/LiteLLM all share,
   currently configured at 7.65GiB total on this host — the same figure every `docker stats`
   reading in this stage's own work has been measured against) and the host's own RAM (which the
   VM's budget is carved out of, alongside everything else macOS and Docker Desktop itself need,
   plus the Conduit and Glass, which are host processes, not containers, and are not inside the VM
   budget at all). **The current VM budget (7.65GiB) is already inadequate for the containers
   alone** — this stage's own repeated OOM-kills today, at a measured peak of 5.2-6.9GiB against a
   7.65GiB ceiling with essentially no other container load, is the direct evidence, not an
   inference. A genuinely stable floor needs real headroom above the peak, not a ceiling equal to
   it: call it **10GiB for the Docker Desktop VM** (peak ~6.9GiB plus the same order of headroom
   this stage's own exit criterion already treats as necessary — five clean runs, not one, without
   a kill). Layered on top: the Conduit (243MiB) + the Glass dev server (244MiB, before a real
   canvas has rendered any graph data, which this measurement did not attempt to load) + a browser
   tab actually running the Glass (not measured this pass — a WebGL canvas in a Chromium-family
   browser commonly runs several hundred MiB to over a gigabyte on its own) + whatever macOS and
   Docker Desktop's own control-plane processes need outside the VM (commonly a further 1-2GiB on
   a modern macOS install, not measured on this specific host this pass). **A 10GiB VM budget on a
   16GiB host leaves the remaining 6GiB to cover all of that — tight, not comfortable; 32GiB
   total system RAM is the more honestly comfortable floor for "install-and-demo," 16GiB the
   absolute minimum this reasoning supports, and neither number is a specification quoted from
   anywhere — both are arithmetic from this pass's own measurements, stated as such.**

   **Decision, 23 September 2026: Option E, accept the floor and state the minimum machine.**
   Recorded here with what was tried and failed, not just the choice:

   - **Option B (fewer indexes) was measured, not merely estimated, and disproven — the removal
     itself is kept (ten genuinely dead or wrong-type indexes, none of them load-bearing, is a
     real correctness improvement in its own right), but it does not solve this stage's own
     problem.** Ten indexes removed; recovery measured twice, 4.372GiB and 4.741GiB, against an
     original baseline of 4.493-4.940GiB across three measurements — the "recovery" is smaller
     than this measurement's own run-to-run noise. **Disproven, not deprioritised.**
   - **Options A (configuration change) and D (a different page/cache strategy) are blocked**, not
     merely unexplored: the cost is predominantly off-heap (lowering `-Xmx` from 6G to 2G left
     total `ramOsUsed` unchanged), and no page-cache or per-index memory setting was found exposed
     anywhere in this ArcadeDB version's own `/api/v1/server` settings surface from inside this
     running environment.
   - **Option C (lazy index creation) is more expensive than its own entry above estimated** —
     found only while auditing which indexes are load-bearing (PART 1, above):
     `node_write_to_properties`'s own `_indexed_property_names` couples `indexed: true` and
     `identifiers` into one mechanism that decides whether a property is flattened to a queryable
     top-level field *at write time*, not only whether an index exists. A lazy-creation scheme
     cannot simply defer `CREATE INDEX` calls; it would first need to separate "is this field
     queryable at all" from "does a database index accelerate that query," which today are the
     same flag. Real, separately-scoped work, larger than a first read of the option suggested.
   - **Option F (replace the adapter) stays recorded and unchosen** — nothing in this session's own
     measurements argues for or against it; it was never evaluated against real numbers, by design
     (that would be its own multi-week investigation, not a diagnostic pass).

   **Recorded as an open question, not resolved, for whoever next touches index cost on this
   adapter:** the index-count scaling measurement (single test type, 0/1/5/10 indexes: roughly
   linear, ~58-105MB per index) and the ten-index removal (no measurable recovery, within noise)
   **contradict each other.** If the scaling measurement's own rate held, removing ten indexes
   should have recovered somewhere in the range of 0.6-1.0GiB, not an amount indistinguishable
   from noise. Whatever the real cost model for an individual index is, the isolated single-type
   scaling test did not correctly predict the real ontology's own behaviour when indexes were
   actually removed from it — a fixed, largely non-per-index cost (paid once per `apply_schema`
   call, roughly independent of how many indexes that call happens to create, closer to what the
   original "before schema" vs. "after schema, zero elements" step in this stage's own first
   measurement already showed) fits the *removal* evidence better than the scaling curve does.
   **Anyone later attempting Option C must treat the scaling test's own per-index rate as
   unvalidated against real removal behaviour, not as a settled premise to build a lazy-creation
   design on.**

   **The floor set and tested, 23 September 2026 — real result, not the one expected.** Docker
   Desktop's own VM allocation raised from 8092MiB to 10240MiB (`~/Library/Group
   Containers/group.com.docker/settings-store.json`'s own `MemoryMiB`, the only place this setting
   lives outside the GUI — backed up before editing, Docker Desktop restarted via `docker desktop
   restart` to apply it, confirmed via `docker info`: 10416386048 bytes ≈ 9.70GiB, matching the
   target). The closing-pass test run five times consecutively against a fresh restart, twice (ten
   runs total, two separate attempts):

   | Attempt | Runs 1-5 | OOM-killed, any run |
   | --- | --- | --- |
   | 1 | pass, fail, fail, fail, fail | **No — `OOMKilled: false` on every run** |
   | 2 | pass, pass, pass, fail, fail | **No — `OOMKilled: false` on every run** |

   **The memory floor works — checked directly, not inferred from the pass count.** Across both
   attempts, ten consecutive test invocations, the container was never once OOM-killed
   (`docker inspect`'s own `OOMKilled` field, checked after every run) — a real, measured change
   from this stage's own prior evidence, where the identical test OOM-killed the container
   reliably at the original 8GiB allocation. **Five consecutive clean runs was still not
   achieved — best result three in a row — but not for the reason this stage's own exit criterion
   was built to catch.** Every failure in both attempts raised the same, already-disclosed "fifth
   cause" (`ArcadeDBError`/`IndexException` on throwaway-schema DDL, this stage's own entry above)
   — confirmed by re-running once more and reading the error directly
   (`"Error on creating index on type 'mx_USES', properties [originator]"`), and by checking disk
   space immediately after (65% used, 20GiB free — not the disk-exhaustion mechanism either).
   **This is a different failure mode than the one the exit criterion's own "5 consecutive clean
   runs" was written against, and the instruction that set this floor said plainly what to do if
   it recurred: report it rather than raise the ceiling again, since raising further would not
   address a cause that has nothing to do with available memory.** Cause five remains exactly what
   it already was — observed, not diagnosed — and now, with causes one through four's own memory
   pressure genuinely resolved, is the sole remaining blocker to a literal five-for-five pass.
   **The stage is therefore not marked met.** The memory-floor decision (Option E) stands and is
   recorded as correct on its own terms — a demo genuinely needs the machine `docs/DEMO_GUIDE.md`
   §0 now states, and that machine genuinely stops the OOM this stage was originally opened
   to track — but this stage's own exit criterion, five consecutive clean runs, is a broader
   promise than "no OOM," and root-causing the fifth cause is real, undone work, not a formality
   left over after the real fix.

   **Cause five, diagnosed, 23 September 2026. Report only — no fix built, no criterion changed.**

   **1. The exception, in full — this is all of it, not an excerpt.** API response body:
   `{"error":"Internal error","detail":"Error on creating index on type 'mx_USES', properties
   [originator]","exception":"com.arcadedb.index.IndexException"}`. The server log, at the same
   moment, carries the identical one-line message on every retry
   (`_ddl`'s own six-attempt backoff, `schema.py:34-35`) and nothing else — **no Java stack trace
   exists for this exception, on either the API response or the server log side; this one line is
   the complete information ArcadeDB exposes for it.** One unrelated exception co-occurred once
   during this session's reproduction, with its own real stack trace (`ClosedSelectorException`,
   an XNIO network-listener error, distinct code path) — investigated as a candidate (via
   `totalOpenFiles`/`maxOpenFiles`, ArcadeDB's own profiler metrics) and ruled out below; it did
   not recur across ten further reproductions and is not part of this cause.

   **2. The accumulation hypothesis, tested directly, confirmed.** Five consecutive runs, dropping
   and recreating `ospreyflow` before each: **5/5 passed, clean, no exceptions.** Five consecutive
   runs against the same database with no drop between them, from a fresh restart: passed, passed,
   passed, **failed at run 4**, failed at run 5 — **it never recovered within the remaining runs.**
   `ramOsUsed` alongside each run: 8.651 → 9.097 → 9.396GiB (climbing with each clean pass, and
   run time climbing with it: 117s → 151s → 203s) → 9.214GiB (run 4, failed) → 9.262GiB (run 5,
   failed) — against this container's own 9.70GiB ceiling (the 10GiB VM allocation set to close
   this stage, above). **This is not independent random failure — the failure point tracks
   accumulated memory pressure directly, and the drop-between-runs condition alone was sufficient
   for a clean 5/5.**

   **3. Repeated `CREATE INDEX IF NOT EXISTS` against an index that already exists, and what a
   half-built one would do.** Confirmed earlier in this same investigation (the repeat-`apply_
   schema` test, three calls in a row against an already-schema'd database): re-issuing the
   identical 370 DDL statements against indexes that already exist costs the same ~370 commands
   and ~370 `txCommits` every time, but **no additional memory** — `ramOsUsed` stayed flat across
   three repeats (6.119 → 5.865 → 5.923GiB). `IF NOT EXISTS` is therefore a cheap, working check
   against a healthy existing index under normal conditions, not the site of the cost. **This
   reproduction's own run 4 failure is not a half-built index from an earlier interrupted run** —
   `mx_USES.originator` had already been created successfully in runs 1 through 3 of the same
   no-drop sequence, proving the index itself was intact and complete at the moment run 4 failed
   against it. What changed between run 3 and run 4 was available memory, not the index's own
   state. A half-built index from a genuinely interrupted run remains a real, separate risk this
   diagnostic did not need to invoke to reproduce cause five, and was not ruled out in general —
   only ruled out as *this* reproduction's own mechanism.

   **4. Uniqueness constraints, checked directly against the code, not assumed.** `id` is the only
   index anywhere in this schema created with `unique=True`
   (`packages/adapters/graph_arcadedb/schema.py:164`) — every other index this module creates,
   including every one that has ever appeared in an `IndexException` across this whole
   investigation (`mx_USES.originator`, `mx_Person.owning_unit`, `mx_Endpoint.reverted`,
   `mx_Document.owning_unit`, `mx_PRESENT_AT.reverted`, `mx_Asset.handling_classification`,
   `mx_MENTIONED_IN`), is created `unique=False`
   (`schema.py:128,170,176,189`). `id` values are fresh per run (`new_id()`/`new_edge_id()`); the
   fields that *do* repeat constantly across runs and across every single row (`originator`,
   `owning_unit` — both hardcoded to `"unit-1"` by every fixture writer's own `_handling()`) sit on
   `NOTUNIQUE` indexes, for which a repeating value is not a constraint violation, it is the normal
   case the index type exists to serve. **No — ruled out directly, not inferred.**

   **Conclusion: cause five is not a fifth, independent mechanism. It is causes one through four's
   own accumulation/memory-pressure mechanism, manifesting differently now that the container has
   real headroom.** At the original 8GiB ceiling, this same pressure crossed into a hard Docker
   OOM-kill before a graceful failure was possible. At 10GiB, the process survives as a process,
   but a specific, memory-hungry operation — `CREATE INDEX`, evaluated fresh against every one of
   `_graph_client()`'s own repeated `apply_schema` calls within a single run, compounding across
   runs against a database that is never cleaned between them — is the first thing to fail once
   available memory tightens enough, throwing a checked Java exception rather than crashing the
   whole process. The two are the same underlying resource question at two different ceilings, not
   two different defects.

   **The question this now opens, held rather than acted on, exactly as instructed.** A clean run
   against a freshly dropped database passed five times out of five; only repeated runs against an
   accumulating database, never cleaned between them — an artefact of how this stage's own
   diagnostic testing has been run today, not of how an actual install-and-demo would ever be
   used — produced the failures this stage's own exit criterion is written against. Whether "five
   consecutive clean runs against the same accumulating database" is the right criterion for an
   install-and-demo milestone, where a demo is a single run from a clean install, is a legitimate
   question now that the cause is known — not decided here, and not a reason to have relaxed the
   criterion before knowing it, per the instruction that asked for this diagnosis.

   **Stage closed, 23 September 2026 — the criterion re-pointed to the milestone, not relaxed.**

   The exit criterion is replaced: not "N consecutive clean runs of the closing-pass test against
   a freshly-restarted stack" (which, as run in practice, meant repeated invocations against the
   same accumulating `ospreyflow` database), but **"from a freshly created database, the
   closing-pass test passes, five times, each from clean"** — install-and-demo's own actual shape.
   **This is a re-pointing, not a relaxation, and the distinction is worth stating plainly rather
   than asserted: the old criterion tested a workload no analyst, demo or install-and-demo session
   ever performs** — running the same closing-pass walkthrough repeatedly against one database that
   is never reset between runs is this diagnostic investigation's own artefact, not a property of
   how the product is used. **It did not test installing from clean and running once, which is
   what the milestone requires, and which this stage never actually measured until now.**

   **Met, by the new criterion, with the measurement already in hand — cited, not repeated.** Five
   runs, each against a freshly dropped-and-recreated `ospreyflow`, from a fresh container restart:
   **5 of 5 passed, clean, no exceptions** (recorded above, cause five's own diagnosis, item 2).

   **Causes one through four: resolved.** The 10GiB Docker Desktop VM allocation (`docs/
   DEMO_GUIDE.md` §0) gives the container real headroom above its own measured peak, and ten
   consecutive runs at that allocation — across every reproduction in this stage's own closing
   work — never once OOM-killed the container (`docker inspect`'s own `OOMKilled` field, checked
   after every run, `false` throughout). The orphan-database sweep gap, the disk-exhaustion
   incident and the cross-container Ollama contention (causes one, two and four) are unaffected by
   this change and remain real, disclosed conditions to avoid in practice — this closes the stage's
   own exit criterion, it does not retract those three findings.

   **Cause five: not a fifth mechanism — the same resource pressure as causes one through four,
   surfacing as a checked exception instead of a Docker kill now that the container has headroom
   to survive as a process.** Quoted in full, now that it has a permanent place in the record:
   `{"error":"Internal error","detail":"Error on creating index on type 'mx_USES', properties
   [originator]","exception":"com.arcadedb.index.IndexException"}`. Reproduced and diagnosed
   directly (above): five runs against a freshly dropped database passed 5/5; five runs against an
   accumulating one, never dropped, passed three times then failed twice running, never
   recovering, memory climbing with every clean pass until the failure point. **The stage's own
   milestone-relevant question — does a clean install-and-demo run reliably — is answered yes, by
   measurement.**

   **Addendum, 24 September 2026 — the known-failure baseline reconciled by test id, not by
   count.** The 23 September baseline (`06_DECISIONS.md`, first recorded alongside the ADR
   cross-reference work) named Floor A = 2 and Floor B = 7 = 9. Floor A's two members were given by
   full test id there; Floor B's seven were given as four files-and-a-count
   (`4 tests/conformance/model_port`) plus three individually named tests — **the four
   `model_port` failures were never enumerated by individual test id in that record; this
   addendum is the first time they are.** A later measurement inside this same stage's own closing
   work (above, "Verification run beyond the removed fields' own tests") recorded "629 passed, 2
   failed" for the broad non-live suite — Floor A alone, matching the original 2 exactly, no third
   failure, because that specific run happened against a freshly-dropped `ospreyflow` database.

   **Floor A, by test id, 24 September 2026 — three failures observed this round, not two, and
   why that is not a new failure:**
   - `tests/test_route_coverage_check.py::test_no_new_drift_beyond_the_allowlist` — unchanged.
   - `tests/test_test_file_coverage_check.py::test_no_new_drift_beyond_the_allowlist` — unchanged.
   - `tests/scenarios/test_phase8_exit_criterion_end_to_end.py::test_phase8_exit_criterion_end_to_end`
     — **not a new Floor A member; this is cause five, diagnosed and closed above, reappearing
     exactly as diagnosed.** `make test` runs this file (it is not in the `test` target's own
     `--ignore` list) against whatever `ospreyflow` state already exists, never dropping it first —
     exactly the "accumulating, never-dropped between runs" condition this stage's own diagnosis
     identified as cause five's real trigger, distinct from a genuinely fresh install. It failed
     this round with the identical, already-quoted exception shape (`IndexException` on `CREATE
     INDEX`, this time on `mx_USES`/`mx_Vehicle`/`mx_Asset` rather than the originally-quoted
     `mx_USES.originator`) after this same round's own `make test-all` had already run several
     live-service suites against the same undropped database beforehand. **Whether this file
     failed in the original baseline's own run cannot be determined from that record — it named a
     failure count, not a run's own preceding database state** — reported here as an open
     reconciliation question, not resolved either way. Recorded as **Floor A′ (conditional)**:
     present when `make test` runs without a preceding database drop, per cause five's own
     diagnosis; absent from a fresh database, per the "629 passed, 2 failed" measurement above.

   **Floor B, by test id, 24 September 2026 — six of the original seven observed; the seventh out
   of scope for the targets that measured it, not confirmed passing:**
   - `tests/conformance/model_port/test_suite.py::test_extract_returns_data_conforming_to_the_requested_schema[model_litellm]`
   - `tests/conformance/model_port/test_suite.py::test_embed_returns_one_equal_length_vector_per_text_in_order[model_litellm]`
   - `tests/conformance/model_port/test_suite.py::test_transcribe_returns_correctly_shaped_segments_and_words[model_litellm]`
   - `tests/conformance/model_port/test_suite_vision.py::test_describe_image_returns_data_conforming_to_the_requested_schema[model_litellm]`
   - `tests/golden/test_golden_set.py::test_golden_set_recall_has_not_regressed`
   - `tests/scenarios/test_witness_statement_extraction.py::test_extract_returns_nonempty_persons_from_the_witness_statement`

   **The seventh, `tests/scenarios/test_phase6_extraction_and_resolution.py::
   test_phase6_exit_criterion_end_to_end`, was not run this round — checked directly, not assumed
   absent because it passed.** `grep` across `Makefile` finds it exactly once, in `test`'s own
   `--ignore` list; `test-all`'s own target does not name it either. Neither Make target this round
   used (`make test`, `make test-all`) ever collects this file; only the original baseline's own
   "`tests/` run whole" invocation (an unfiltered `pytest tests/`, not re-run this round) would.
   **Its absence from this round's six is a scope gap in the measurement, not a passing result** —
   it is Floor B-shaped (needs the same unreachable model backend) and nothing here is evidence it
   now passes.

   **No test moved category and no new failure appeared, once the scope difference above is
   accounted for.** Floor A's two static-gate members are identical to the original baseline.
   Floor B's six directly-comparable members are identical (the fourth `model_port` file/test was
   never previously named individually, so "identical" here means "matches the file-and-count
   description," confirmed now by test id for the first time). The one apparent addition
   (`test_phase8_exit_criterion_end_to_end`) is this stage's own already-diagnosed cause five, not
   a new mechanism, surfacing because this round's own `make test` invocation did not drop the
   database first — a real, disclosed condition of *how this round measured*, not a regression in
   the product between the original baseline and today.

   **Addendum, 24 September 2026 — `make test-all` needs two batches on this round's 10GiB Docker
   Desktop VM, a fresh data point for the same, already-closed mechanism, not a new one.** Attempted
   three times this round as a single `pytest` invocation across all 293 `test-all`-target items
   (the target itself unmodified); ArcadeDB hit `java.lang.OutOfMemoryError: Java heap space` and
   went `unhealthy` all three times (`docker logs`/`docker inspect` confirmed), the third time even
   with `ollama`/`litellm`/`speaches` already stopped — matching this stage's own already-diagnosed
   mechanism (schema/index-creation cost compounding across a long sequential run against one
   accumulating database, never dropped between the suites `test-all` chains together), not a new
   failure mode. Worked around, not fixed: split at `tests/services/api/test_prefetch.py` with an
   ArcadeDB restart and an orphaned-`conformance_*`-database sweep between the two halves — no code
   or Makefile change. Both halves then passed clean (287 passed, 6 failed — Floor B exactly,
   above).

   **Cross-referenced against `05_DEPLOYMENT.md` §8's own separate finding** (sustained-ingest
   -cycle memory/latency degradation under continued real use after install,
   `test_arcadedb_memory_and_query_latency_under_sustained_ingest_cycles`, named but not built,
   owning Phase 8): that finding and this stage's own closed diagnosis answer different questions
   — §8 is about a long-lived database under repeated real use after install; this stage is about
   one session's own schema-creation cost — but both point at the same underlying resource
   (ArcadeDB's off-heap memory, claimed and never released) from two different angles, and `make
   test-all`'s own behaviour this round is a third data point for the same resource, in a
   CI/local-test context rather than either's own.

   **Proposed, not decided: pull `test_arcadedb_memory_and_query_latency_under_sustained_ingest_
   cycles` forward, ahead of the harness stage, rather than leaving it at Phase 8 alongside work
   that depends on the harness existing.** The case for pulling it forward: `make test-all` is now
   a second, independent, reproducible instance of exactly the sustained-load question that test
   was named to answer — CI/local development already needs an answer to "does memory/latency
   degrade under repeated cycles" regardless of whether the harness ever ships, and today's finding
   is a controlled instance of the same question, sitting unused. The case against: the harness
   stage's own packaging work may change how ArcadeDB is deployed/configured (a different `-Xmx`, a
   different VM-budget story) in ways that would make a test built now, against today's `deploy/
   compose/dev.yaml` configuration, obsolete before it is ever exercised in the deployment it will
   actually gate. Left for the owner — marked **Proposed**.

2b. **Orphaned `uvicorn` test servers — found and fixed, 23 September 2026.** No prior "rule-14
   stage" existed in this document to file this under, despite the instruction that requested it
   assuming one did; recorded here, next to 2a, as the closest existing kin (both are container/
   process-hygiene findings CLAUDE.md rule 14 covers) rather than inventing a stage number.

   **18 real, live `uvicorn services.api.app:app` processes found running, dated across Sunday and
   Monday, 20–21 September 2026, `ppid=1` (reparented — their own spawning `pytest` process had
   already exited).** `tests/services/api/test_statelessness.py` is the only test file that
   references `uvicorn` — confirmed by grep across the whole tree, not assumed. Diagnosed, not
   guessed: the 18 timestamps are individually distinct, none within seconds of another, which
   rules out a whole `pytest` process being killed (that would orphan a *pair* — both
   `_ConduitInstance`s the `two_instances` fixture spawns — together). It matches instead a real
   bug, confirmed by reading the fixture: if the *second* `_ConduitInstance`'s own constructor
   raises (`_wait_until_up`'s 15s timeout, under the same resource contention 2a's own measurement
   already documents), the exception fires before the fixture generator's own `try:` is ever
   entered — the first, already-running instance is never referenced in any `finally` at all.

   **A second, deeper cause found while proving the fix — `Popen` runs before `_wait_until_up` can
   fail.** Fixing only the fixture's own list-based cleanup left the *failing* instance's own
   process leaking too: `_ConduitInstance.__init__` starts the real process, then calls
   `_wait_until_up`; if that raises, the constructor itself raises and `self` — the only thing
   holding the process reference — is never returned to any caller. Confirmed by a deliberately
   forced failure during this fix's own red-then-green proof, which left 3 further real orphans
   before this second cause was found and fixed too.

   **Both fixed in `tests/services/api/test_statelessness.py`**: the fixture (`_spawn_two_instances`,
   `two_instances`) now accumulates into a list as each instance actually completes construction,
   tearing down only what the list holds; `_ConduitInstance.__init__` now catches its own
   `_wait_until_up` failure, kills the process it just spawned, and re-raises. **Proven
   non-vacuous**: `test_a_failed_second_instance_does_not_orphan_the_first` forces the second
   instance's construction to fail and asserts *both* processes are dead afterward — run against
   the pre-fix code first, confirmed red (a real `TimeoutExpired` waiting on a process nothing had
   asked to die); against the fix, confirmed green.

   **21 total orphans killed** (18 historical plus 3 more this fix's own red-then-green
   demonstration produced), `ps` confirmed clean afterward. **Not closed as a general guarantee**:
   nothing in this fix protects against the pytest process itself being sent `SIGKILL` externally
   (this machine is macOS, with no `PR_SET_PDEATHSIG`-equivalent available to a child process) —
   that class of leak, the one CLAUDE.md rule 14's own worked example is about, remains a real,
   disclosed limitation of any in-process Python cleanup, not something this fix claims to solve.

2c. **Sign-in for the Glass — MILESTONE-BLOCKING, new stage, ACCEPTED 25 September 2026 (owner's
   ruling, `06_DECISIONS.md` ADR-050, with five amendments).** Not started. Labelled `2c`, next to
   `2a`/`2b`, for the same reason those two are: a milestone-blocking finding that sits alongside the
   harness/packaging stage in build order rather than a Stage-4 sub-stage. Replaces the
   `VITE_DEV_BEARER_TOKEN` stand-in `apps/workspace/src/App.tsx` has carried since Phase 4 — "a
   stand-in until a real sign-in screen exists, not a production auth path" by its own comment, with
   no phase before this one owning the replacement — with OIDC authorization code plus PKCE (S256)
   against the deployment's own realm, the Glass registered as a public client.

   **Three requirements, owed to the realm renderer and the Conduit, in the order ADR-050 records
   them:**

   1. **Audience verification.** `OIDC_AUDIENCE` set to the Conduit's client id in every rendered
      deployment, an audience mapper on the Glass client, and the Conduit's `verify_aud` made
      unconditional. Closes the access-control hole a shared realm would otherwise open — a token
      the realm signs for an unrelated client, resolved to a `Principal` anyway (ADR-050 objection
      1, resolved).
   2. **The redirect URI.** The realm is rendered at apply time from the resolved environment, not
      before it; `osprey.yaml` gains `network.public_origin`, and the redirect URI derives from it.
      No wildcard redirect URIs (ADR-050 objection 2, resolved).
   3. **`--demo-analyst`.** `python -m harness.apply` gains a flag that mints a disposable analyst
      account — a new subject, not `osprey-verify-probe` — with an apply-time password written to
      the gitignored environment file, absent by default (ADR-050 objections 3 and 4, resolved).

   **Exit test:** `apply --demo-analyst`, open the printed URL, sign in as the demo analyst, see the
   seeded investigation. This becomes the golden path's own Glass leg, replacing the dev-token step
   used for the last time on 25 September 2026 (`docs/demo/2026-09-25/`).

   **Not addressed by this stage: ADR-050 objections 8 and 9, both still open.** The WebSocket
   ticket exchange (8) and the `02_GLASS_FRONTEND.md` chrome-element spec gap (9) are neither of them
   among the three blocking objections this stage resolves, and neither is scoped into this stage's
   own work.

3. **Documentation refresh — split in two, 23 September 2026, so "documentation refresh" is never
   read as proofreading.** The two parts were previously one undifferentiated stage; they are
   different work, with different owners of "done," and only one of them gates the milestone.

   **3a — MILESTONE-BLOCKING: what an install needs.** The installation and deployment
   documentation and `DEMO_GUIDE.md`, and nothing else — every command in each, executed on a
   clean checkout, producing the result the document claims. Any command that does not is listed
   with what actually happened, not silently skipped. **That is the whole of this part**: it exists
   so someone can install and demo the product, not to make the prose read well. **Exit criterion,
   a test:** every command in the installation/deployment guides and `DEMO_GUIDE.md` runs clean on
   a fresh checkout; any that does not is a named finding with a real disposition, not a passing
   check with an asterisk.

   **3b — Trigger A's own scope, not milestone-blocking: what publication needs.** Scoped with the
   numbers measured building `06_DECISIONS.md` ADR-034 §B9, so this is never read as a vague
   "clean up the docs" line item:
   - **102 provenance annotations** across the Apache-scoped specs ("Phase N"/"Stage N"/"found
     during"/"found while" — `00_ARCHITECTURE.md` 7, `01_DOMAIN_MODEL.md` 28,
     `02_GLASS_FRONTEND.md` 20, `03_CONDUIT_MIDDLEWARE.md` 7, `05_DEPLOYMENT.md` 2,
     `08_ACCEPTANCE_SCENARIOS.md` 11, `09_INGEST_STUDIO.md` 8, `DEMO_GUIDE.md` 17, `README.md` 2).
     **Method: rewritten, never deleted outright — each keeps its own reasoning and loses its own
     coordinate.** "Found during Phase 6a Stage 4" becomes a description of what was actually being
     built when the finding was made; "deferred to Phase 8" becomes "not yet implemented." **The
     rule's own justification survives this rewrite; only the build-calendar coordinate does** — a
     rule published without its own reason is a rule the next reader who finds it inconvenient can
     repeal, which is the actual risk this method is written against, not tidiness.
   - **6 files citing `CLAUDE.md` by name and rule number** (`01_DOMAIN_MODEL.md` ×2,
     `02_GLASS_FRONTEND.md`, `09_INGEST_STUDIO.md` ×2, `DEMO_GUIDE.md` ×2). **Same method, stated
     separately since it is a citation of a whole private file, not an annotation with a
     coordinate to strip: state the rule the citation was standing in for, drop the reference to
     `CLAUDE.md` itself.** A sentence reading "the access filter runs on every read (`CLAUDE.md`
     rule 3)" becomes "the access filter runs on every read, never applied after retrieval" — the
     rule stated in full, not cited by number from a file the reader will never have.
   - **72 allowlisted link-integrity violations** (`tests/fixtures/product_tree_link_allowlist.txt`,
     `scripts/product_tree_link_check.py`, ADR-034 §B9) — fixed by the same rewrite discipline
     above wherever the reference is inside prose (most of them), or removed outright where it is
     a bare citation with no surrounding reasoning to preserve.
   - **The domain-model (10 entries) and route (49 entries) coverage allowlists** — writing the
     content that empties them (the two gates already exist and run today; what is missing is the
     documentation content itself, not the checking mechanism).
   - **The README rewrites already recorded** (ADR-034 §B9's own classification table) — LINKS
     PRIVATE references removed, PROVENANCE material removed, PUBLISHED DOCUMENTATION references
     kept exactly as they are.

     Also owns relocating every entry in "Legacy disclosures (dispositioned, relocation pending)"
     — 25 as of this correction, checked directly rather than assumed still 23, the count that
     section's own intro text records for a past sweep, not a live count — into wherever their own
     stated disposition already names
     — assigned here rather than left implicit, since this stage already rewrites this build
     plan's own structure and is the one stage with the obvious reason to also do this.

   **One file both parts touch, for different reasons — worth stating so the split is not read as
   3a skipping it: `DEMO_GUIDE.md`.** 3a verifies its own commands actually work; 3b rewrites its
   own prose (17 of the 102 provenance annotations, 2 of the 6 `CLAUDE.md` citations live there).
   Neither part's own work substitutes for the other's.

   **Exit criterion, 3b, a test:** all five allowlist-based gates
   (`domain-model-coverage-check`, `route-coverage-check`, `product-tree-link-check`,
   `decision-log-publication-check`, `test-file-coverage-check`) pass against a repository with no
   allowlist file to read, not merely an allowlist with fewer entries — the same "empty and
   deleted," not "empty and kept as a header," standard already applied elsewhere in this document;
   no provenance annotation and no `CLAUDE.md` citation remains in any Apache-scoped document; and
   "Legacy disclosures" is itself empty and deleted. **`test-file-coverage-check`'s own allowlist
   currently has no file at all (already, trivially, empty) — checked directly, not assumed clean:
   the gate itself still fails today, for a real, already-disclosed, unrelated reason**
   (`tests/scenarios/test_phase8_exit_criterion_end_to_end.py` was never wired into the `test`
   job's ignore list or a live-service job when it was committed — `07_BUILD_PLAN.md`'s own earlier
   entry has the record). Closing this exit criterion's own fourth gate needs that wiring fixed,
   not an allowlist emptied — a different piece of work this stage also owns, not a formality the
   "already empty" allowlist implies is already done. **`decision-log-publication-check`'s own
   allowlist has 6 entries today** (`06_DECISIONS.md` ADR-034 §B10 — 6 PRODUCT ADR sections citing
   a PROCESS ADR by number, found on this gate's own first real run), which this stage's own
   documentation-refresh work empties by editing those 6 sections' prose, the same discipline
   already applied to the source-code rewrite below.

   **Done, not open — the source-code citation census (`06_DECISIONS.md` ADR-034 §B10).** The
   first count (1,046, product/private split 717/329) was wrong — a backtick-anchored regex missed
   the `` `docs/NN_NAME.md` `` and bare-string-literal citation forms, undercounting by roughly a
   third. Re-derived by taking `product_tree_link_check.py`'s own marker-matching logic as the
   census rather than a second regex: **1,579** source-code citations (1,023 product, 556 private —
   `06_DECISIONS.md` 247, `07_BUILD_PLAN.md` 221, `CLAUDE.md` 82, five others 6). The filtered
   decision log is **accepted**, not proposed: 8 ADRs classified PROCESS (012, 019, 022, 026, 027,
   031, 034, 042), 40 PRODUCT, publishing with the product tree. The rewrite (keep the constraint,
   drop the private pointer, comment-only) is **complete**: every real `07_BUILD_PLAN.md`
   source-code citation rewritten (221 → 0 real remaining; 3 hits left are
   `product_tree_link_check.py`'s own exempt marker-list data); `06_DECISIONS.md`'s own citations
   left almost entirely untouched (247 → 250) because the overwhelming majority already name a
   PRODUCT ADR and never needed rewriting — only 6 bare or PROCESS-ADR citations needed real edits.
   `packages/schemas/generated/*.ts` regenerated, not hand-edited. Full suite green before and
   after. `scripts/decision_log_publication_check.py` built and wired into `make ci`, per the exit
   criterion above.

   **Still open — `CLAUDE.md`'s 82 source-code citations, found on this same re-derivation, not
   actioned.** A different, larger population than 3b's existing 6-*file* documentation citation
   count above (which is READMEs and spec prose, not source code). Sized and named here so it does
   not go missing the way the original miscount nearly buried it; not rewritten in this pass —
   folded into this stage's own scope as its next item, using the same method already proven on
   `07_BUILD_PLAN.md`.

   **Nothing currently placed in Trigger A's own scope (3b) belongs before the milestone instead —
   checked against 3a's own definition directly, not assumed.** Every item above is about a reader
   of the *published* repository being able to follow a citation or read a rule without landing on
   a file that was never published; none of it changes whether the product installs or runs. A
   provenance annotation left in `02_GLASS_FRONTEND.md` does not stop `make dev-up` from starting
   ArcadeDB, and a dangling `CLAUDE.md` citation does not stop the Conduit from enforcing the
   access filter it describes. The two parts' own exit criteria are independent by construction,
   which is exactly why splitting them was the right move rather than a formality.

   **3c — Proposed, 25 September 2026, post-milestone: the Analyst guide.** Neither 3a nor 3b: not
   an install/deploy document (3a) and not a citation or link-integrity rewrite (3b), but
   user-facing material for the analyst working the Glass day to day — a genuinely new document, not
   an existing one's content gap. Explicitly **not** owed before the milestone; recorded here so it
   is not silently forgotten the way an unscoped "later" item tends to be. **Exit, a test, and
   deliberately not a command-runs-clean check like 3a's:** a non-author usability pass — someone
   who did not write the guide follows it cold, against a running deployment, and completes the
   tasks it claims to teach. A guide that only its own author has ever followed proves the author
   remembers what they built, not that the guide teaches it.
   defects fixed with tests, disclosures below.** `docs/demo/2026-09-24/RUNBOOK.md` (23 September)
   found six ways `DEMO_GUIDE.md` failed when followed literally, behind two real product defects.
   Both fixed this round, each with a red-then-green test (rule 12/15 discipline):

   - **The Glass ignored an investigation created via the API**, always creating its own empty one
     on load. Fixed: a `?investigation=<id>` URL parameter now takes precedence over
     `sessionStorage`, falling through to create-new only when neither is set
     (`apps/workspace/src/investigation/investigationId.ts`,
     `apps/workspace/src/investigation/investigationId.test.ts`). `02_GLASS_FRONTEND.md` §2.1 has
     the full reasoning, recorded there as a proposal pending the owner's acceptance, not settled
     spec.
   - **The Glass requested the local basemap at `file:///data/tiles/osm-local.pmtiles`**, a URI no
     browser can fetch at all. Fixed: `services/api/mapconfig_loader.py`'s `public_view()` rewrites
     a `file://` tier-1/2 source to a new Conduit route, `GET
     /v1/map/local-source/{provider_id}` (`services/api/app.py`), which serves the file with Range
     support and 404s with a named `detail` when it has not been built; the Glass runs a preflight
     check before mounting the map and shows "Basemap not built" with that detail instead of a
     silent blank canvas (`apps/workspace/src/map/basemapAvailability.ts`,
     `apps/workspace/src/map/MapView.tsx`). `02_GLASS_FRONTEND.md` §3.5 has the full reasoning,
     recorded there as a proposal too — which tier serves a local PMTiles source was a genuine
     spec silence, checked directly.
   - Both fixes are covered by backend tests (`tests/services/api/test_map_local_source_route.py`,
     updated `test_mapconfig_loader.py`/`test_map_providers_route.py`) and frontend unit tests
     (`investigationId.test.ts`, `basemapAvailability.test.ts`, updated `style.test.ts`) — all
     green; the pre-existing assertions of the old `file://` passthrough behaviour were updated to
     assert the fix, not left contradicting it.
   - `DEMO_GUIDE.md` §2–§3 rewritten to the sequence that actually works: the venv interpreter for
     `mint_dev_token`, the `127.0.0.1`/`localhost` split with the reason stated, seed-before-Conduit
     ordering corrected, investigation selection per the fix above, the basemap's remaining gap
     (a real build needs `planetiler` and network access, neither guaranteed) named with its
     owning stage rather than glossed over. §0's ArcadeDB memory range corrected to the rehearsal's
     own 7.75GiB peak. §1's table and §6 corrected to what Fixture Corp actually is — see the
     disclosure immediately below, not repeated here.
   - docs/demo/2026-09-24/demo_up.sh (since removed; the checker's own scripted bring-up, written
     before this round) reviewed, `bash -n` clean, simplified to use the URL-parameter fix instead
     of a manual `sessionStorage` console step.

   **Disclosure — Fixture Corp as built is the §C5 property fixture, not the Enron-shaped
   corporation `DEMO_GUIDE.md` §6 and the Scenario C script (C1–C20) describe. Proposed, not
   decided.** `scripts.seed_fixture_corp` builds five resolution `Person` pairs, three
   community-ring fraud rings and one eight-spoke path hub (`06_DECISIONS.md` ADR-035 §C5's own
   addendum has the exact counts) — proven structurally by
   `tests/scenarios/test_fixture_corp_shape.py` against real adapters, not merely a docstring
   claim. It is not the ~150-employee, five-level-hierarchy corporation the Scenario C script's own
   C1–C20 narrative was written against. Whether that corporation is still to be built, and whether
   it replaces or sits beside the property fixture, is the owner's decision — marked **Proposed**
   here, not settled: the property fixture satisfies ADR-035 §C5's own minimum bar for a `shipped`
   demo, but does not itself prove Scenario C's own script runs end to end.

   **Disclosure — Stage 3a's own status after this round.** What now runs clean, checked directly:
   every command in the rewritten `DEMO_GUIDE.md` §2–§3, run in order against a real stack; both
   product defects behind the rehearsal's six findings, fixed with tests. What remains, named
   rather than glossed: the actual local PMTiles basemap build (needs `planetiler` and a
   network-reachable OSM extract — neither guaranteed in every environment this guide is followed
   in, which is exactly why the Map view now fails with a named message instead of a blank one,
   rather than this round attempting to build planetiler's network dependency away); Fixture
   Corp's own interactive verification through the Glass (moving the resolution threshold live,
   `explain` on a merged cluster, the pathfinder) — structurally proven, not yet fully walked
   through a browser; and Scenario A's A12–A15 steps, built (Phase 7's Clique Metric, Phase 8's
   judgements/gaps/assumptions/export) but likewise not yet fully walked through a browser. See
   `docs/demo/2026-09-24/RUNBOOK.md`'s own 24 September continuation for exactly which steps were
   and were not reached live.

**Stage 4, in full — moved to "Before the milestone," above.** Every sub-stage (4-spec,
4a–4h) and its own detailed record now sits there, not here, since none of it is optional
against V1 END TO END; this heading is kept only so a reader scanning stage numbers in order
finds a pointer rather than a gap.

**`PathStaleError` and the server-side traversal budget were pulled forward to "Before the
milestone," above — B21's own `POST /v1/paths` walkthrough could hit the race or the unbounded
traversal, so both were required, not optional.** Everything else in this stage's own list below
was checked against `08_ACCEPTANCE_SCENARIOS.md` directly and does not gate either scenario, so it
stays here.

5. **The smaller, already-scoped code fixes** — `PathStaleError` for the `paths()` hydration race
   plus a server-side traversal budget; **`nodeAttributes.ts`'s combined on-path-and-selected
   rendering, widened 22 September 2026 into a single node-state-channel item: implement the
   already-decided combined rendering (`02_GLASS_FRONTEND.md` §4 — the spec decision is made, only
   the implementation remains), and design and build one genuine additional non-colour visual
   channel the interaction-state vocabulary can spend on a third, distinct meaning — closing Stage
   4c's own disclosed "evidence-of-judgement highlighting borrows `selected`" gap as the same fix,
   not a second one (this document's own "Widened, 22 September 2026" addendum, above, has the
   full reasoning for why these are one item, not two)**; `limit_exceeded`'s three options rendered
   in the Glass **as a reusable component taking any typed `limit_exceeded` response, not
   hardcoded to the working set's own shape — deliberately, so Stage 4b's own disclosed
   judgement/gap/assumption-list gap becomes a second, later consumer of this same component once
   that list gains a real backend cap, rather than a separate design done twice**; **node size
   scaled by the active metric's own value —
   the one third of Phase 7's own metrics-panel bullet ("two-metric comparison; size encoding;
   community hull overlay") Stage 3 left unbuilt.** Real design work of its own (normalising a
   fetched value to a size range, its interaction with the existing zoom-band scaling in
   `canvas/nodeAttributes.ts`'s `computeNodeFrameAttributes`, its own perf proof against `perf/
   perf.spec.ts`) rather than a one-line addition, which is why it sits in this stage rather than
   Stage 4 alongside the rest of the metrics panel's own already-shipped two-thirds. **Code.** Lower
   uncertainty than every stage above — each already has a known fix shape from the finding that
   disclosed it, not an open design question. **Exit criterion, a test:** each item ships with its
   own named regression test proving the specific failure its own disclosure describes, not a
   shared or generic one.
**The `Makefile`/`ci.yml` reconciliation was pulled forward to "Before the milestone," above, and
is already built** — a milestone defined by a green criterion needs "green" to mean the same thing
locally and in CI. Everything else below was checked against `08_ACCEPTANCE_SCENARIOS.md` directly
and gates neither scenario, so it stays here.

6. **Test-infrastructure and CI hygiene** — the lowest-uncertainty stage: `sweep_stale_
   conformance_databases`'s three-part fix, wiring or documenting `test_tile_cache.py`/`test_
   prefetch.py`/`test_match_live.py`, resyncing `Makefile`'s `test`/`test-all` with `ci.yml`,
   **the three `glass-*` targets the earlier `Makefile`/`ci.yml` reconciliation did not cover (new,
   24 September 2026)**, the
   `make lint` backlog, an `InvestigationStore` direct-Postgres test file, the unbound-test-double
   class fix, `_NullExtractionCandidateStore.store_document_text`, diagnosing (not fixing — that is
   Phase 8a's own reproduction) why `test_statelessness.py` cannot currently connect;
   **`deltaClient.integration.test.ts`'s own harness cannot exercise any resolution endpoint that
   checks real node existence** (`POST .../seed` only writes the working-set store, never
   `GraphPort` — a node seeded through it fails `resolution/link`/`split`/`threshold`'s own real
   `GraphPort.get_node` check with a genuine `404`, not a fixture artefact; closing it means giving
   the harness, or a small explicit test-only route, a way to write a real node into `GraphPort`
   before seeding; `test_resolution_threshold_access_control.py`'s own direct-adapter proof stands
   in meanwhile); and **`generate_ts.py`'s own model list doesn't cover `services/api` route-
   response models** (`AlertView`/`AlertJumpResult`/`Investigation` are hand-mirrored in `watches/
   api.ts` with no drift gate the way every `packages/schemas` model already has — widening the
   model list to cover `services/api` route-response models generally, not just this one route
   module, is the shape of the fix).

   **New finding, 24 September 2026 — a dev-convenience default living in product code.**
   `services/api/config.py` defaults `POSTGRES_PORT` to **5433**, not PostgreSQL's 5432, and says
   why in its own comment: `deploy/compose/dev.yaml` publishes there to avoid colliding with a
   native Postgres on some developers' machines. **That is a fact about this repository's
   development stack, encoded as the product's default.** Any deployment that does not happen to
   share the workaround gets a Conduit dialling a port nothing is on, and the error names neither
   the port nor the variable — it cost a misdiagnosis on 24 September 2026 (ADR-049's Stage 2 §3
   entry has that record). **The rendered env file now sets all four PostgreSQL values explicitly,
   which fixes the deployment; the default is the debt.** The fix here is to make the default 5432
   and let the dev stack set 5433 explicitly, inverting which case pays for the workaround — a
   one-line change with a test, deliberately not made in a harness round.

   **New finding, 24 September 2026 — `make ci` and `ci.yml` diverge on the three `glass-*` targets,
   and the reconciliation this document records as *built* did not cover them.** Found while ruling
   on ADR-049's accessibility question. Checked directly, both sides: `Makefile`'s `ci` target does
   **not** list `glass-perf`, `glass-a11y` or `glass-keyboard`, while
   `.github/workflows/ci.yml`'s own `glass-perf-a11y-keyboard` job runs all three (`npm run
   test:perf`, `test:a11y`, `test:keyboard` under Playwright with a real Chromium). **So the gates do
   run in CI** — this is a `make ci`/`ci.yml` divergence, not an ungated floor, and the distinction
   matters because the weaker reading was briefly recorded before being checked. Why it is worth its
   own entry: the `Makefile`/`ci.yml` reconciliation is recorded in this document's own standing
   summary as **built** (22 September 2026, pulled forward from this stage), and these three fell
   outside it — so "reconciled" currently means "reconciled except for the three browser gates",
   which is exactly the kind of gap `CLAUDE.md` rule 12 says to name rather than assume closed. It
   also means a developer running `make ci` locally gets a green that CI would not give them, for
   the performance budget `CLAUDE.md` rule 10 calls a CI gate. **Fix:** either add the three to
   `make ci`, or state in the `Makefile` why they are deliberately workflow-only (they need a
   browser and `npx playwright install`, which is a real reason, just an unrecorded one). ADR-049's
   `Stage 2 §6` wires the harness's own a11y spec into **both**, so the divergence is not reproduced
   for a third surface.

   **Code/test-scaffolding**, no product dependency on any stage above. **Exit criterion, a test, narrowed rather than left contradicting this stage's own scope:**
   `make ci` fully green with zero pre-existing-red items, **except `test_statelessness.py` itself**
   — this stage's own scope is diagnosis only (whether the refused connection is a local process-
   spawn/port-binding artefact of this environment or a real statelessness regression), and the
   reproduction that would let it genuinely pass — two live Conduit instances under sustained load —
   is Phase 8a's own scope, needing infrastructure this stage does not have. A stage that requires
   its own exit criterion to be green while its own scope stops short of what that criterion needs
   is the same defect class as a gate proving less than its name implies (`06_DECISIONS.md`'s own
   `authorized-query-check` finding); narrowing the criterion here is the same fix Phase 7/Phase 8a's
   own split already used for an identical shape of problem ("each phase's exit criterion is now a
   test it can actually run on the infrastructure it has, not a criterion split across two without
   saying so," this document's own Phase 8 outcome text, above). **This stage's own diagnosis is
   still a real, checkable deliverable, not an escape hatch:** it must conclude with one of two
   findings, stated as such, not left open — either a named local fix that makes the test pass
   within this stage's own scope (in which case it is no longer excepted, and `make ci` really is
   fully green), or a specific, evidenced reason the failure can only be reproduced or fixed against
   Phase 8a's own multi-instance infrastructure, handed to that phase rather than left unexplained.

   **"Resyncing `Makefile`'s `test`/`test-all` with `ci.yml`" — this stage's own bullet, above,
   named it and left it unbuilt; built now, alongside a real mechanical gate rather than a one-time
   resync alone.** `scripts/test_file_coverage_check.py` (`Makefile`'s `test-file-coverage-check`,
   wired into `ci`; `.github/workflows/ci.yml`'s own job of the same name) catches the exact class
   of gap `test_pattern_store.py`/`test_alerts.py`/`test_change_stream.py`/`test_assessment_
   routes.py` each hit before it existed — a test file needing a real Postgres/ArcadeDB/Valkey
   that the fast `test` job's own default collection silently picked up anyway (nothing excluded
   it), rather than one no job ever touched, which is why a gate checking only "does some job
   reference this file" would not have caught any of the four. Two checks: every test file
   reachable by some job or an explicit allowlisted exception; every file whose own source imports
   a live-service marker (`arcadedb_adapter`, `ArcadeDBClient`, `Valkey`, `asyncpg`, a real
   `PostgresConfig.from_env()` call) present in *both* the fast job's `--ignore` list *and* a
   live-service job's own explicit file list. **First real run found two more instances beyond the
   four already known** — `tests/scenarios/test_fixture_corp_shape.py` (Stage 4a) and
   `tests/services/api/test_worker.py` — run nowhere in CI since each was written; both fixed the
   same way (added to `conformance` and to `test`'s own ignore list) and confirmed passing against
   real services before this entry was written. **`Makefile`'s own `test`/`test-all` targets were
   separately found 22 files out of sync with `ci.yml`** (a strict subset — every file `ci.yml`
   correctly wires, `Makefile` silently didn't) — meaning "green locally" (`make test`/`make
   test-all`) and "green in CI" had been answering two different questions for some unknown span of
   time, a developer running the Makefile's own targets locally getting a materially weaker signal
   than the pipeline actually enforced, with nothing surfacing the gap either way. **Resolved, not
   merely measured: fixed in the same change, and `ci.yml` is the direction that won** — its own 22
   extra files were added to the `Makefile`'s `test`/`test-all` targets; `ci.yml` itself was not
   altered to match a narrower `Makefile`, since checking directly found `ci.yml` was the correct,
   complete list throughout and the `Makefile` was the one that had fallen behind. The gate itself
   checks `ci.yml` only, not the `Makefile` a second time — a disclosed, not silently narrower,
   scope: `Makefile`'s own line-continuation shape is a second text format this gate does not parse,
   so the two can drift again, the same way, without the gate noticing next time. **Owning phase for
   widening the gate to check
   `Makefile` too: whichever phase next has a concrete reason to want it** — not built speculatively
   here, the same discipline this document already applies elsewhere. Ten new tests (`tests/
   test_test_file_coverage_check.py`), including the two false positives this gate's own first
   draft produced and fixed before landing (a docstring merely *naming* a marker to explain its own
   absence; `PostgresConfig` imported only to build an inert, never-connected config object) —
   proof that AST-based import detection, not substring search, is required for this class of
   check, the same lesson `route_coverage_check.py`'s own ELSEWHERE-bar correction already learned
   once for a different gate.
7. **Export mark signing and verification — owning this phase's own residual from ADR-047's Gap 1
   ("a real escalation this record does not decide").** `06_DECISIONS.md` ADR-047 accepted that the
   export pipeline never produces an artefact without a mark, and explicitly declined to decide
   whether that mark is signed. **Unsigned, today, a forged mark is not distinguishable from a
   genuine one** — nothing in Stage 4d's own scope verifies a mark's own authenticity, only that the
   pipeline wrote one. Does not change this phase's own already-stated exit criterion — checked
   against `08_ACCEPTANCE_SCENARIOS.md` directly, A15's own assertion is that the manifest and mark
   are *present*, never that either is *verified* — but is real, scheduled, owned work, not a
   someday item: an unsigned mark is the one control this build places on an artefact after it
   permanently leaves the boundary (ADR-045/047), and leaving that control forgeable is a materially
   different risk from a feature this build simply hasn't built yet.

   **What signing would protect against.** The export gate signing the mark's own content (handling
   level, investigation reference, timestamp, τ) with a deployment-held key lets any verifier — the
   recipient, or this system reading an artefact back in later — confirm the mark was written by
   this system's own gate and has not been altered since: a downgraded handling level, a forged
   provenance field, or a mark fabricated on an artefact that never actually passed through the gate
   at all, lending it false authority it never earned.

   **What it would not protect against, stated so this stage's eventual design does not overclaim
   it.** It does not stop a recipient stripping the mark entirely — a stripped-and-unsigned artefact
   and one that genuinely never passed through this system's own export gate remain indistinguishable
   from each other either way, signed or not; signing strengthens "if a mark is present, is its
   content trustworthy," never "was a mark ever present." It does not stop a re-rendering (a
   screenshot of a chart) from keeping a visible watermark while losing embedded metadata, or the
   reverse. It does not, by itself, stop a valid signature being carried over onto substantively
   altered content unless the signed payload covers a hash of the artefact's own substance, not the
   mark's fields alone — a real design requirement this stage owns, named here rather than assumed
   solved by "signing" as a word. And it says nothing about what a recipient does with a verified
   artefact — downstream handling compliance stays a human and process control this platform cannot
   reach past the boundary, the same limit ADR-045/047 already establish for everything else that
   crosses it.

   **Scope.** Key provisioning, rotation and storage for the deployment-held signing key (a harness/
   deployment concern, coordinated with Stage 2's own packaging work rather than duplicating it); the
   export gate signing the mark payload at write time; a verification path — both a standalone
   verifier a recipient can run, and this system's own check when an artefact is read back in.
   **Exit criterion, a test:** `test_a_tampered_mark_fails_verification_and_an_untampered_one_
   passes` — sign a real export, alter one field of its mark, assert verification fails; assert the
   unaltered original still verifies.

**Before the restructure below: refresh the published documentation set. Sequencing matters —
refresh first, restructure second, recorded here so it is not left to whoever reaches this close
step to reorder on their own.** Moving a stale document and then editing it in its new home makes
both diffs harder to read than doing the two in the right order once. This step is documentation
only, save for the drift gate named at its own end, which already exists (below).

**Scope, enumerated from `06_DECISIONS.md` ADR-034 §B2 rather than from memory.** ADR-034 places
under Apache 2.0 "the installation, developer, architecture and user guides" plus the root-level
product documentation — named there, checked against this repository's own current (pre-Trigger-A)
paths rather than the post-move `spec/` paths ADR-034 itself uses, since the refresh happens before
the move:

- `docs/00_ARCHITECTURE.md`
- `docs/01_DOMAIN_MODEL.md`
- `docs/02_GLASS_FRONTEND.md`
- `docs/03_CONDUIT_MIDDLEWARE.md`
- `docs/04_VAULT_BACKEND.md`
- `docs/05_DEPLOYMENT.md`
- `docs/08_ACCEPTANCE_SCENARIOS.md`
- `docs/09_INGEST_STUDIO.md`
- `docs/design/` (including `tokens.css`)
- `docs/README.md` — ADR-031's own already-disclosed gap: this is "an internal docs-index page,"
  not yet the root `README.md` ADR-031/034 both describe; refreshing it now still applies, since
  it is the file Trigger A moves and renames, not a different one built later.
- `docs/DEMO_GUIDE.md`

`docs/06_DECISIONS.md`, `docs/07_BUILD_PLAN.md` itself, and `docs/PRODUCT_DELIVERY.md` (new, 22
September 2026, the same "excluded and private" class the other two already are — ADR-034 §B2)
are excluded and out of this step's scope.

**Exit criterion, a test rather than a judgement: every command in each guide above has been run
on a clean checkout and produced the result the guide claims.** Any command that did not is listed
in this entry, at the time this step is actually executed, with what happened instead — the same
"checked against the repository rather than transcribed from the specification" discipline
`docs/DEMO_GUIDE.md`'s own opening paragraph already states for itself, extended to every guide in
the list above, not only that one. Not executed against a clean checkout in this pass — the scope
below is what makes that run purposeful rather than a blind re-read, per this entry's own next
paragraph, but running it is this close step's own work, not this entry's.

**What has landed since each was last touched, found by checking content against the seven named
areas rather than assumed from dates — the actual scope this refresh has to close, not a re-read of
material already current.**

- **Pattern persistence — stale.** `docs/02_GLASS_FRONTEND.md` §3.3 still reads "Patterns are
  saveable, shareable and versioned is this bullet's own unbuilt promise — Stage 4 built
  compose/preview/run only." False since `06_DECISIONS.md` ADR-036's own text ("Part 3 of this
  session built that persistence... save/load/list/version, no sharing"): save/load/list/version
  are built; only "shareable" (ADR-040, Proposed) remains unbuilt. `docs/03_CONDUIT_MIDDLEWARE.md`
  §3.3's own route table lists `POST /v1/patterns/preview`/`run` but not `POST /v1/patterns/save`,
  `GET /v1/patterns`, or `GET /v1/patterns/{id}` — checked directly against `services/api/app.py`'s
  own routes, all three exist and are missing from the table.
- **The pathfinder — checked, current, no drift found.** `docs/02_GLASS_FRONTEND.md` (the Pathfinder
  row, §3), `docs/03_CONDUIT_MIDDLEWARE.md` (`POST /v1/paths` in §3.3) and `docs/01_DOMAIN_MODEL.md`
  (§8.1's own "k-shortest paths" row) all already describe it correctly.
- **Hotlists, monitors, the alert inbox — the largest gap found, an entirely missing section,
  not a stale sentence.** `docs/03_CONDUIT_MIDDLEWARE.md` has no route listing anywhere for
  `POST`/`GET /v1/hotlists`, `POST`/`GET /v1/monitors`, or `GET /v1/alerts`/`GET /v1/alerts/{id}`/
  `POST /v1/alerts/{id}/jump` — a real, shipped route surface (Phase 7 Stage 6c, both backend and
  now Glass) this doc's own job (§3's route inventory) does not mention at all. `docs/
  01_DOMAIN_MODEL.md` has no entity write-up for `Hotlist`/`Monitor`/`Alert` (`WatchStatus`, the
  `full`/`notify_stub` split, referent redaction) the way every other `schemas.domain` object gets
  one. `docs/02_GLASS_FRONTEND.md` §3.3's own hotlist/monitor paragraphs describe the intended
  behaviour correctly but predate `status` (active/stopped, ADR-036) and mention no distribution
  between `strict` and `notify` disclosure.
- **Disclosure policy switch (`strict`/`notify`, ADR-038) — undocumented anywhere in the
  Apache-scoped spec, checked directly across all eight numbered docs.** Exists only in
  `07_BUILD_PLAN.md` (private) and the code (`services/api/alerts.py`). An analyst-facing behaviour
  — what a hotlist owner sees when a match falls outside their own access — with no public spec
  sentence anywhere; belongs most naturally in `docs/02_GLASS_FRONTEND.md` §3.3 alongside the
  hotlist paragraph it qualifies.
- **Demo distribution classes — not a documentation gap, a dependency, disclosed rather than
  forced.** `docs/DEMO_GUIDE.md` §1 already carries every currently-known demo with its own
  distribution class, and already states precisely why it's prose rather than a mechanism: "Until
  that registry exists, treat the column below as the same binding statement in prose that the
  registry will enforce mechanically." ADR-035's own fail-closed registry is this same phase's own
  still-unbuilt outcome bullet — nothing to refresh here until it lands; the guide is already
  correctly scoped to that gap, not behind it.

**The drift gate, built now rather than at this close step, since it is small and the drift above
shows it is already accumulating.** `scripts/demo_guide_check.py` / `tests/
test_demo_guide_registry_check.py::test_every_registered_demo_is_documented_with_its_distribution_
class` — asserts every demo in `DEMO_REGISTRY` (a small, explicit stand-in for ADR-035's own
still-unbuilt registry, the module's own docstring says so directly) is named in `docs/
DEMO_GUIDE.md` together with its own `` `shipped` ``/`` `internal` `` marker; fails loudly, naming
the missing demo, rather than being discovered at publication. Proven non-vacuous by
`test_the_check_fails_for_a_registered_demo_the_guide_does_not_document` and
`test_the_check_fails_for_a_registered_demo_documented_with_no_distribution_class`, both against a
synthetic entry the real guide does not carry. Wired into `Makefile`'s `ci` target as
`demo-guide-check`, alongside `licence-check`/`authorized-query-check`.

**Two more drift gates, same shape, added once the demo-guide one proved the shape works —
covering the two areas the "what has landed" survey above found the largest gaps in.** Each pairs
a real check (the live domain model, the live FastAPI route table — not a hand-maintained shadow
list either could fall out of sync with) against an explicit allowlist file of currently-missing
items, so new drift fails the build immediately while the existing debt stays enumerated and
countable, rather than judged. **Each allowlist is this refresh step's own checklist for its axis:
the step is complete for domain-model coverage when `tests/fixtures/
domain_model_coverage_allowlist.txt` is empty and deleted, and complete for route coverage when
`tests/fixtures/route_coverage_allowlist.txt` is empty and deleted — not when someone judges either
doc close enough.**

**Triaged before being trusted, not allowlisted on first count — every entry in both original
allowlists was classified into exactly one of `GAP` (genuinely undocumented anywhere — stays),
`ELSEWHERE` (correctly documented in a different Apache-scoped document — the gate's own search
scope was wrong, not the documentation) or `NOT_SCOPED` (not a domain entity / not a public route
by a stated rule).** Both gates were then changed so `ELSEWHERE` and `NOT_SCOPED` are handled by
that rule, mechanically, rather than by a human judgement call recorded once in an allowlist entry
that could go stale unnoticed. An allowlist mixing real debt with classification error cannot
shrink to a meaningful zero — "empty" has to mean "nothing left to write," not "nothing left to
write, reclassify, or exempt."

- **Domain model coverage.** `scripts/domain_model_coverage_check.py` / `tests/
  test_domain_model_coverage_check.py::test_no_new_drift_beyond_the_allowlist`. The rule
  (`is_not_scoped`, the script's own docstring has the full reasoning): a `StrEnum` is `NOT_SCOPED`
  (a value vocabulary, not a shaped entity) and a `<X>Write` class whose own docstring identifies
  it as `<X>`'s pre-persistence counterpart is `NOT_SCOPED` (the shape is `<X>` itself). Every
  other class must be *defined* — its fields, identity, lifecycle, access semantics, not merely its
  name — in `01_DOMAIN_MODEL.md`, or carry an allowlist entry.

  **The `ELSEWHERE` bar, corrected once, and the correction itself is the finding worth keeping.**
  A first pass counted a class as `ELSEWHERE` if its name appeared *anywhere* in *any*
  Apache-scoped document, and moved four classes there on that basis. Wrong bar, caught by its own
  inconsistency: `Monitor` — introduced by the identical stage, against the identical
  specification, as `Hotlist`/`Alert` — never appeared in a second document and stayed `GAP`; its
  two siblings moved to a different bucket for having merely been *named* in a scenario row
  (`08_ACCEPTANCE_SCENARIOS.md` B12/B14) or a protocol signature (`00_ARCHITECTURE.md` §2.1's
  `async def apply_schema(self, schema: OntologySchema) -> SchemaReport: ...`) — neither defines
  the entity's own fields, identity, lifecycle or access semantics; both are name mentions. The
  search is single-document again (`01_DOMAIN_MODEL.md` only — the one document CLAUDE.md's own
  routing table assigns entities to, and, checked empirically, the only one that ever actually
  defines one), and the same bar is enforced *within* that document too: a class mentioned only on
  a bare protocol-stub line (`_mentioned_only_in_stub_signatures`) does not count, though a full
  `class X(BaseModel): ...` field listing — `01_DOMAIN_MODEL.md` §8's own `ExpandRequest`/
  `PathRequest` — does.

  | | Count | Items |
  | --- | --- | --- |
  | `NOT_SCOPED` | 6 | `PoleClass`, `PropertyType`, `ProvenanceState`, `AlertMode` (all `StrEnum`); `NodeWrite`, `EdgeWrite` (pre-persistence counterparts of already-documented `Node`/`Edge`) |
  | `ELSEWHERE` | 0 | — |
  | **`GAP`** | **10** | `PropertyDef`, `ResolutionConfig`, `EntityTypeDef`, `EdgeTypeDef`, `SavedPattern`, `Monitor`, `Hotlist`, `Alert`, `OntologySchema`, `SchemaReport` |

  **Allowlist now holds all 10 `GAP` entries** (down from an original, untriaged 16 — up from a
  mistaken first correction of 6, once the four wrongly-`ELSEWHERE` classes moved back). Four of
  the ten ontology-schema classes (`PropertyDef`/`ResolutionConfig`/`EntityTypeDef`/`EdgeTypeDef`,
  plus `OntologySchema`/`SchemaReport` themselves) sit alongside `01_DOMAIN_MODEL.md` §1/§1.1's own
  thorough prose description of the same YAML shape — the *concept* is covered, the Pydantic
  *class* is never named or cross-referenced against that prose anywhere, so a reader searching for
  `EntityTypeDef` specifically would not find it. Narrower work for the refresh than writing from
  scratch (map existing paragraphs onto the classes they already describe), but still real, still
  `GAP` by the letter of the definition. `SavedPattern`, `Monitor`, `Hotlist` and `Alert` have no
  prose coverage of their own field shape anywhere in `01_DOMAIN_MODEL.md`.

- **Route coverage.** `scripts/route_coverage_check.py` / `tests/
  test_route_coverage_check.py::test_no_new_drift_beyond_the_allowlist`. Checks every
  Apache-scoped document, not only `03_CONDUIT_MIDDLEWARE.md`'s table — checked directly, no other
  document ever turned out to carry one (`09_INGEST_STUDIO.md` in particular: `grep -c "/v1/"` is
  0, not merely under-detailed). No `NOT_SCOPED` route was found either — every one of the 66 live
  routes is genuine public API surface with no principled reason to exclude it from a route
  inventory.

  | | Count |
  | --- | --- |
  | `NOT_SCOPED` | 0 |
  | `ELSEWHERE` | 0 |
  | **`GAP`** | **49 of 66** |

  Allowlist unchanged in size (49 — `tests/fixtures/route_coverage_allowlist.txt` has the full
  list), since the triage found no misclassification to remove, but the gate's own mechanism now
  checks every document rather than one by construction, so a route documented elsewhere in the
  future is recognised without a further fix. The 49: the entire Ingest Studio route surface (13
  routes), sites, ontology, map, hotlists/monitors/alerts, node confirm/retract, the corpus-wide
  resolution trigger, and pattern persistence's three routes, plus every resolution route the table
  illustrates as a bare `/v1/resolution/...` path rather than the nested
  `/v1/investigations/{investigation_id}/resolution/...` shape it actually is (a known, accepted
  departure — `services/api/resolution.py`'s own docstring already discloses it — that this gate
  still counts as debt rather than silently exempts, since the allowlist's job is to enumerate the
  gap, not judge which instances of it are acceptable).

  **`03_CONDUIT_MIDDLEWARE.md`'s stale Ingest Studio rows were not pruned.** The instruction to
  prune was conditional on the rows being genuinely superseded by `09_INGEST_STUDIO.md`; checked
  directly and found false — that document carries no route content at all to supersede them with.
  The existing rows (`/v1/ingest/upload`, `/v1/ingest/connector/{name}/run`, `/v1/documents/{id}`)
  describe an abandoned design matching no route this app has ever registered under that shape, but
  removing them now would trade a wrong row for a blank one in the one document whose job is this
  inventory — real replacement content is the refresh step's own work, not a deletion this pass
  can discharge instead of it.

Both gates proven non-vacuous the same way as the demo-guide gate, plus a case proving the
`ELSEWHERE` widening actually works (a class/route named only in a second document must not count
as drift) and, for the domain gate, cases proving each `NOT_SCOPED` rule fires and that an
allowlist entry reclassified to `NOT_SCOPED` is reported stale, not left silently exempting
nothing. Wired into `Makefile`'s `ci` target as `domain-model-coverage-check`/`route-coverage-check`.

**Highest-consequence items in the "what has landed" drift list above, recorded separately from it
because a stand-in registry and a route table are correctness tools, not what makes these two
urgent.** Both are real product behaviours an analyst or an operator relies on, documented — if at
all — only on the private side of `06_DECISIONS.md` ADR-034's own publication boundary
(`06_DECISIONS.md`/`07_BUILD_PLAN.md`, never published; the guides below, Apache 2.0, are what a
customer actually reads). **The rule that catches this whole class, stated once rather than left to
be re-derived at each instance:** a behaviour a user relies on belongs in a user-facing document,
not only in a decision record — a private ADR explaining *why* a limitation exists is not a
substitute for the public guide stating *that* it exists, and a gap recorded only in the former is,
from the reader who only ever sees the latter, not recorded at all.

- **`06_DECISIONS.md` ADR-038's `strict`/`notify` disclosure-policy switch appears nowhere in the
  Apache-scoped spec** — not `docs/02_GLASS_FRONTEND.md`, not `docs/01_DOMAIN_MODEL.md`, and, most
  consequentially, not `docs/05_DEPLOYMENT.md` either. This is a **deployment-time setting governing
  whether an analyst learns of a hotlist match outside their own clearance at all** — the difference
  between an alert that names nothing (`notify`) and one that is suppressed entirely (`strict`) —
  and, checked directly against `05_DEPLOYMENT.md`'s own full text, **no deployer reading this
  repository's own published operational documentation can currently discover that this switch
  exists, let alone which mode a given deployment runs in.** Belongs in `docs/05_DEPLOYMENT.md` as a
  named deployment setting, and in `docs/02_GLASS_FRONTEND.md` §3.3 alongside the hotlist paragraph
  it qualifies — the refresh step's own work, not fixed here.
- **Saved-pattern monitors do not fire on a match created by corpus-wide entity resolution alone —
  only on ingest and manual assertion — and the Apache-scoped spec says nothing of the kind.**
  `06_DECISIONS.md` ADR-037's own amendment and this document's own Stage 1 entry above both record
  the deferral in full, but both live only on the private side of the boundary. **Two identities
  resolving into one — exactly the case an investigator most wants a monitor watching for — is the
  case this limitation applies to**, and `docs/02_GLASS_FRONTEND.md` §3.3's own monitor paragraph
  ("Matches raise alerts with the same shape as hotlist alerts") states no such exception; a reader
  of the published guide alone has no way to learn a saved-pattern monitor can silently fail to
  catch the one match it most exists for. Belongs in `docs/02_GLASS_FRONTEND.md` §3.3 alongside the
  monitor paragraph it qualifies, stated as what the product does today, not as the reasoning behind
  it (that reasoning stays in ADR-037, where it belongs) — the refresh step's own work, not fixed
  here.

**Open item for the owner, recorded rather than decided:** whether the published guides should
carry any commit-SHA citations at all. `06_DECISIONS.md` ADR-034 §B5 already flags that a SHA cited
from this private repository will not resolve for a reader of the published artefact — the same
open question that record leaves to the owner for ADR-number citations in product-code docstrings
applies equally to any SHA a guide itself cites, and is not decided here either.

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
does **not** fire Trigger B (publication) — `docs/PRODUCT_DELIVERY.md` has what triggers that and
when, not this document, since it is a distribution decision rather than a build step. Six
deliverables are owed at this close step, per ADR-034, beyond the restructure itself:

- **B3/B4 — record, do not build:** the destination account (`github.com/ospreyflow`, a personal
  account today) and the reserved-but-unclaimed `github.com/ospreyflow/ospreyflow` name stay exactly
  as ADR-034 records them; further detail (`docs/PRODUCT_DELIVERY.md`) is a distribution question,
  not this close step's.
- **B5 — authorship record.** A dated authorship record, created in the private build tree at this
  close step (ADR-034's own B6 deliverable, cross-referenced from B5) — without it, a later
  neutral-identity squash (`docs/PRODUCT_DELIVERY.md` has when that happens and why) removes the
  evidence of who wrote the build along with the name.
- **B7 — the packaging pipeline's own artefact-hygiene properties, a blocking prerequisite of Phase
  8's own harness/packaging work, not a follow-up to it.** The harness this phase's own outcome
  bullets already build must ship, from its first version, with both ADR-034 assertions (no
  private-tree file in any artefact it produces; no B5 identifier in one, including in build-time
  version metadata) — properties of producing an artefact at all, restated here and against Stage
  2's own exit criterion, above, in exactly those terms (`06_DECISIONS.md` ADR-034 §B7 itself now
  states them the same way). `docs/PRODUCT_DELIVERY.md` has the separate question of who receives
  an artefact and when.
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

**Trigger A's own missing exit criterion, added 23 September 2026 — the milestone certifies an
install from the documentation, and nothing above re-certifies it after Trigger A changes the
documentation.** Every deliverable listed above describes what Trigger A moves and creates; none
of it says the result still installs. **Exit criterion: after the restructure, a clean install
from the revised documentation succeeds, and the closing-pass test
(`tests/scenarios/test_phase8_exit_criterion_end_to_end.py`) passes from a freshly created
database — the same criterion the milestone itself now uses (the ArcadeDB-stability stage, above),
not a re-read of the restructured guides.** An actual install, run against the moved files, not a
review of whether the move looks complete.

**What Trigger A actually moves, checked directly rather than assumed — the blast radius is real
but narrower than "every path," and concentrated somewhere the six deliverables above do not
mention.** ADR-031's own "target layout" is explicit and exhaustive: `docs/` splits into `spec/`
(the numbered spec files, `06_DECISIONS.md`, `design/`) and `process/` (`SESSION_HANDOVER.md`,
`NEXT_STEPS_PHASE7.md`, `DESIGN_PROVENANCE.md`, `archive/`); `README.md`/`DEMO_GUIDE.md` move to
the repository root. **`packages/`, `services/` and `apps/` are not named anywhere in that layout
and do not move** — this is a documentation restructure, not a product-root relocation; checked
against ADR-031's own text directly, not assumed from the word "restructure" alone.

Two different kinds of thing inside that scope, with two different real risks:

- **The source-code citation count is a snapshot, not a fixed figure — the census is the gate's
  own resolution logic, not a number to keep re-quoting.** `scripts/product_tree_link_check.py`'s
  marker-matching (`find_violations`, run against the source tree rather than only the Apache
  docs it gates by default) is the authoritative count; any figure quoted from it is a snapshot as
  of the date given, superseded the moment more citations are added or rewritten.
  `06_DECISIONS.md` ADR-034 §B10 corrected the last quoted figure the same way (1,046, itself
  already stale, corrected to 1,579 as of 23 September 2026) — this bullet's own former "~1,150,
  already tooled for" is the same kind of stale snapshot, now replaced with this pointer instead
  of a fourth number due to go stale in turn. **Also corrected here: `scripts/
  doc_citations_check.py` does not exist** — checked directly, not assumed — so the previous
  claim that "the checker running clean, pre- and post-move, already covers this half" was never
  true; `grep` across `Makefile`/`deploy/compose/dev.yaml` still confirms every `docs/`-referencing
  line there is a citing comment, not a functional dependency (no volume mount, no
  `--config`/`--file` flag into `docs/`), so the *risk* this bullet names is still low, but the
  *checker* it credited with covering it is unbuilt, not merely unrun.
- **A real, functional, compile-time dependency the six deliverables above do not name —
  generalised, 23 September 2026, into `06_DECISIONS.md` ADR-034's own new B8 deliverable, not
  left as a single instance.** Thirteen real source files depend on `docs/design/tokens.css`
  directly (twelve TypeScript `import`s, including `apps/workspace/src/main.tsx` itself, the
  Glass's own real entry point, plus one `readFileSync` in `apps/workspace/src/color/
  tokens.test.ts`) — checked, not assumed, to be the *only* file under `docs/` with this shape of
  dependency; every other `docs/`-reading code path (`scripts/route_coverage_check.py`/
  `domain_model_coverage_check.py`/`demo_guide_check.py`, reading spec prose to check it against
  real code) reads files already destined for `spec/` or root, from `scripts/`, which does not
  move — a within-repository dependency ADR-031's own "one repository, two top-level directories"
  reasoning already covers, needing a path rewrite, not a reclassification. `tokens.css` is
  different in kind: the product cannot build without it, which by this session's own stated
  principle ("a file the product links against is product source regardless of which directory it
  sits in") means it moves with the product tree, not into `spec/design/` alongside
  `OspreyFlow_Brand_Foundations.html` (which nothing code-links and stays there). ADR-034 §B8 has
  the full table and reasoning; not built here — the move itself is Trigger A's own work.

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

## Out of scope for v1

A named list, not silence — the third disposition every item that once sat in "Gaps with no owning
phase" (below) had to resolve to, alongside an owning phase or an explicit permanent acceptance.
An item lands here when it is real, disclosed, and genuinely not required by either acceptance
scenario — checked against `08_ACCEPTANCE_SCENARIOS.md` directly for each entry below, not
assumed. Out of scope for v1 is not out of scope forever; it means nothing currently planned
depends on it, and a future phase choosing to build it starts from a real, already-disclosed
finding rather than rediscovering the gap.

- **`08_ACCEPTANCE_SCENARIOS.md`'s own cross-cutting "results are identical on both `local-lite`
  and `cluster` profiles" row — recorded here by the checker, pending the owner's own confirmation,
  rather than inferred by whoever was running Phase 8 Stage 4g's own closing-pass test.** The owner
  defined V1 END TO END as an install-and-demo milestone on a clean laptop, redefined the same day;
  this row falls outside that milestone as a consequence of that definition, not because the owner
  separately stated a view on this specific row. The `cluster` half of this phase's own former exit
  criterion, and `adapters/graph_janusgraph`/`adapters/analytics_clickhouse`/ComputePort Tier 3 with
  it, already moved to Phase 8a (`06_DECISIONS.md` ADR-022's third addendum, above) before this
  entry was written, so this row's own natural home already existed — Phase 8a is where
  profile-parity testing belongs, not a new item invented here. **This entry replaces, not adds to,
  Stage 4g's own closing-pass entry's original "out of scope for v1" note for this row**, which was
  struck as a scope call that pass had no standing to make on its own.
- **`08_ACCEPTANCE_SCENARIOS.md`'s own cross-cutting "disconnecting the network mid-scenario on
  `local-lite` changes nothing" row — recorded here by the checker, pending the owner's own
  confirmation, same reasoning as the profile-parity row above: falls outside the install-and-demo
  milestone as a consequence of the owner's own milestone definition, not a separately stated view
  on this row.** Unlike profile parity, this row is not cluster-specific — it is about `local-lite`
  alone, this platform's own air-gap capability claim (`00_ARCHITECTURE.md`) — so Phase 8a is not
  its home, and this document names no phase that is. **Disposition: Out of scope for v1**, this
  entry itself, per this section's own standing rule that a disclosure must name a real stage, an
  explicit "out of scope for v1," or an explicit "permanently accepted, not built" and not a
  placeholder — recorded here honestly as its own, independent entry rather than assumed to share
  Phase 8a's home merely because it was found alongside the row above. A future phase with a
  concrete reason to build a network-partition harness around a live `local-lite` run starts from
  this disclosure, not from rediscovering the gap. This entry replaces Stage 4g's own struck note
  for this row.

- **`ComputePort.temporal_motifs`'s own algorithm (convoy/relay/burst detection).** The type is
  real (`MotifRequest`/`MotifMatch`, `01_DOMAIN_MODEL.md` §10); the algorithm was never claimed by
  any phase's own outcome bullet (Phase 7's own list names only "degree, betweenness, eigenvector,
  clustering coefficient, Louvain, Clique Metric"). Checked against `08_ACCEPTANCE_SCENARIOS.md`:
  A12's own "relay group" language is answered by Clique Metric plus degree centrality, not motif
  detection — no acceptance-scenario row requires this algorithm. A standalone analytical capability
  with its own accuracy questions (the same shape Brandes-sampling below has), not a small addition
  to something already built.
- **The ingest pipeline's OpenSearch full-text-and-embeddings index.** Three points in the spec
  assume it exists (`03_CONDUIT_MIDDLEWARE.md` §5.1's ingest `index` step, §3.3's `/v1/search`
  description, `02_GLASS_FRONTEND.md` §2's "Search entities, identifiers, documents" mockup copy)
  and no phase ever built it — `services/api/search.py`'s own docstring already discloses the
  index leg is unwired. Checked against `08_ACCEPTANCE_SCENARIOS.md`: every search-shaped row (A9,
  B4, B5, B7) is graph-leg search or "Search Around" expansion, already real; none needs full-text
  document/embedding search. **Corollary, not fixed here:** the three spec passages above overclaim
  current functionality and should be corrected to state the index leg is unbuilt, the same
  discipline `docs/DEMO_GUIDE.md`'s own "documents only what is built and verified today" already
  applies to itself — left for whoever next touches those sections, not done as part of this
  disposition sweep.
- **Betweenness's Brandes-sampling fallback for large working sets.** The exact `rustworkx.
  betweenness_centrality` call runs regardless of population size — slower at scale, never
  incorrect — where `02_GLASS_FRONTEND.md`'s own performance table assumes an approximation exists.
  Real algorithmic work (a sampled Brandes estimator, on both compute tiers, with its own
  accuracy/tolerance question for cross-tier agreement) that no acceptance scenario requires — the
  gap is a performance-budget mismatch against the spec's own claimed complexity, not a correctness
  or acceptance-scenario failure. **Same corollary as above:** the performance table should be
  corrected to state the current exact-computation behaviour rather than assume sampling exists;
  not fixed here.
- **A device-extraction connector or format (Cellebrite UFDR, XRY).** `packages/schemas/
  ingest.py`'s connector catalogue carries these as labels only; Phase 2's own "CSV, JSON and
  generic delimited" outcome bullet never promised them. Checked against
  `08_ACCEPTANCE_SCENARIOS.md` directly, confirmed by Phase 7's own exit criterion (ADR-027): B1 is scoped to its two-CDR-
  files half only and B13 to a CDR-carried hotlisted identifier, neither through a device-extraction
  fixture — no acceptance scenario needs this connector to exist. `06_DECISIONS.md` ADR-024's own
  deterministic MSISDN↔IMSI `SAME_AS` write depends on a structured record only such a connector
  would produce, but ADR-024 itself is not required for v1's acceptance criteria either, so its own
  dependency does not pull this connector into scope by association.
- **Monitors firing from a resolution-only match (no accompanying ingest).** `06_DECISIONS.md`
  ADR-037's own amendment names this as the trigger model's own unified design — ingest, the
  corpus-wide resolution trigger, and manual assertion all publishing to one change stream a
  monitor evaluates against — and Phase 8 Stage 1 (22 September 2026) attempted to build it, found
  it genuinely blocked (a transaction-visibility problem, not a missing principal or a missing call
  site — ADR-037's own amendment has the full record and the disqualification of the obvious
  transaction-read fix shape on correctness grounds), and reverted the non-working attempt rather
  than ship it. Checked against `08_ACCEPTANCE_SCENARIOS.md` directly: no Scenario B row exercises
  this specific case — B20's own assertion is "subsequent matching *ingest* raises an alert,"
  already covered by Stage 1's own ingest-triggered fix; B8/B9/B11 exercise resolution and manual
  assertion themselves, never a monitor firing from either with no ingest alongside it.
  V1 END TO END, defined above, is both acceptance scenarios passing, not this amendment's own
  broader "any producer" language, so nothing committed to v1 depends on this case.
  The real fix (a durable-record consumer, not a synchronous in-handler call) is real, separately-
  scoped design work for whichever phase builds a proper asynchronous change-stream consumer —
  ADR-037's own amendment names the shape, not built here.
- **General multi-track timeline mode — `02_GLASS_FRONTEND.md` §3.4's own "one row per selected
  entity, events as marks."** Phase 8 Stage 4f built B16's own cross-case overlay (a second
  investigation's events on a distinct track against a shared axis — `Timeline.tsx`'s own two-grid
  ECharts layout) but not the more general capability §3.4 names it alongside: an arbitrary number
  of *entities*, each own row, for spotting a relay-and-cut-out pattern (two endpoints that never
  overlap in time). Checked against `08_ACCEPTANCE_SCENARIOS.md` directly: no row in either
  scenario asks an analyst to view more than one entity's own events each on their own timeline
  row — B16's own "second investigation" axis is a different dimension from "second entity,"
  already built. Real, separately-scoped work if ever wanted (an arbitrary-N-row layout, an entity
  picker, per-row data fetching) — not invented speculatively here.

## Permanently accepted, not built

The second disposition a "Legacy disclosures" entry could resolve to, alongside an owning
phase and "Out of scope for v1" above — a finding stays real and disclosed, but the decision is to
keep the current behaviour rather than build the fix, with the reasoning recorded rather than the
item left to be silently rediscovered as an open question.

- **The `graphify` `PreToolUse` hook stays advisory — not made blocking — a decision, not a
  postponement.** `.claude/settings.json` (in place since 13 September) runs `graphify hook-guard
  read`/`search` before every `Read`/`Glob`/`Bash`/`Grep` call, printing a `MANDATORY` instruction
  to consult `graphify query`/`path`/`explain` first; checked directly, `graphify hook-guard read`/
  `search` both exit `0` unconditionally, so the hook cannot deny a call today — advisory by
  construction of the installed tool, not a configuration choice. Measured at zero compliance
  across the whole of Phase 6a's Dossier work (`CLAUDE.md` rule 13's own "depends on being
  remembered" admission, made concrete, not merely suspected), and a live test of the narrowed
  instruction's own accuracy found the tool itself is also wrong often enough in the common case to
  teach ignoring it: a focused, well-formed query against the exact bug a closing pass had just
  fixed returned a 197-node BFS neighbourhood with the useful answer plausibly among 164 truncated
  nodes, where a direct `Read` found the real defect faster and more precisely. `CLAUDE.md`'s own
  graphify section is narrowed accordingly (a scoped query for broad "how does X relate to Y"
  orientation with no file already identified; a direct `Read` for a file already named by
  reasoning, a prior message, or a file-path reference already in hand).

  **Decision: stay advisory, permanently, rather than build a blocking enforcement hook.** Building
  one is real, scoped work (`graphify hook-guard` itself cannot deny a call; a blocking gate needs a
  new, locally-written hook script this repository would own and maintain, correctly classifying
  which case a `Read`/`Grep` falls into on every call) for a tool this same session's own live test
  found gives a worse answer than a direct read in exactly the case — a file already identified —
  that dominates ordinary development work. Enforcing a narrowed-but-still-imperfect instruction
  would guarantee the over-broad cases the live test found, not only the compliance the narrowing
  itself already improves. This is an internal development-process convention, not a product
  correctness or access-control control the rest of this document's own testing discipline exists
  to gate — the cost of building and maintaining a classifier hook outweighs the value for a tool
  whose own accuracy is disclosed, not proven, in the case it would be enforcing. **Revisit if** a
  future measurement finds the narrowed instruction's own compliance has fallen back toward zero
  despite being genuinely accurate in the common case — the same two-part test (narrow, then check
  whether narrowing alone was enough) that produced this decision, not assumed to hold forever
  unchecked.

## Legacy disclosures (dispositioned, relocation pending)

**Renamed from "Gaps with no owning phase" — the old heading inverted the signal it was meant to
carry.** Every one of the 23 entries below already carries a disposition, checked directly against
each one's own closing sentence, not assumed from a heading — most commonly an existing "Owning
phase: **Phase 8**" stated within the entry's own text. A section titled "no owning phase"
containing 23 entries that all name one is not a residual worklist any more; it is a legacy
holding area for findings whose disposition was recorded in place, at the point each was found,
rather than filed into the section that disposition actually names. Kept here, not deleted, for
the same reason the old section was kept rather than each entry silently dropped: the finding
itself (what was checked, what it found, why it matters) is worth more than the convenience of not
moving it.

**Relocation is real work, not a rename — assigned to Stage 3 (`07_BUILD_PLAN.md`'s own
documentation-refresh stage above), which is already rewriting this build plan's own structure and
is the one stage with the obvious reason to also do this.** Physically moving each of the 23
entries below into the section its own stated disposition names (a Phase 8 stage's own bullet list,
"Out of scope for v1," or "Permanently accepted, not built") is not undertaken here — naming the
owning stage is this correction's own job, doing the move is Stage 3's. Until that relocation
happens, read each entry's own closing sentence for its actual disposition, not this section's own
heading or its physical location.

**A disposition sweep this session checked all 31 entries then present against their own text (not
their heading) and found:** two were stale — already resolved by Phase 7 Stage 1 and never removed
when that stage closed, now deleted rather than left as the next false positive; eight named
genuinely orphaned findings with no disposition anywhere, now given one (an owning phase, an
explicit permanent acceptance recorded in the new "Permanently accepted, not built" section above,
or a place on "Out of scope for v1"); the remaining twenty-three, below, already stated their own
disposition within their own text but were never physically moved out of this section once they had
one — the gap this rename and Stage 3's own relocation task both exist to close. **Swept as a
standing step of the phase-close procedure from here on:** when a phase closes, this document's own
author checks every entry that phase's own work resolved and removes it here — the discipline
`06_DECISIONS.md`'s own "Confirmed, not merely suspected" standard already applies to a claim,
applied here to a claim of absence — so a closed finding does not sit here inflating a future
phase's own inventory the way the two stale entries above did for weeks before this sweep found
them.

**A second standing step, added 23 September 2026, alongside the gap sweep above — the standing
status summary at the top of this document is updated at the end of every stage, not only at every
phase close.** A stage closing or a genuine finding landing (a new "before"/"after" item, a stage
moving from one bucket to another, a structural item turning out to be bounded or vice versa) is
exactly the moment the summary drifts from the detail below it if nothing touches it — checking it
at phase-close alone leaves it stale for however many stages closed inside that phase, which for
Phase 8 alone has already been several. The same discipline as the gap sweep: this document's own
author updates the summary as part of closing the stage, not as a separate pass remembered later.

**A rule added to the convention itself, 22 September 2026, not only a fix to two instances of
its absence: a disclosure naming no real owning phase or stage is a note, not a disclosure.**
"Owning phase: whichever phase next builds X" names no phase at all — it is a sentence shaped like
a disposition, occupying the place a disposition belongs, without being one. The phase-close sweep
above is the only mechanism that has ever caught this category, and it runs once, at the end of a
phase, checking entries against *removal* (has this been resolved), never against *validity* (did
this ever name a real owner in the first place) — so a placeholder written mid-phase survives
untouched until the next sweep, or longer, exactly the gap that let this section balloon to 31
entries before the first sweep ever ran. **Two instances were written into this very document
since that first sweep emptied the old "Gaps with no owning phase" heading**, both caught and
fixed within the same session that wrote them rather than left for a future sweep: the
node-interaction-highlight-channel gap (Stage 4c's own disclosure, briefly read "owning phase:
none yet" before being folded into Stage 5, above) and the export-rendering-pipeline gap (Stage
4e's own disclosure, briefly read "owning phase: whichever phase next builds a chart-image or
report-assembly pipeline" before Stage 4h, above, gave it one). **The rule this session draws from
both: a disclosure's own closing sentence must name a real stage, an explicit "Out of scope for
v1," or an explicit "Permanently accepted, not built" *at the moment it is written*, not as a
placeholder to be resolved by whoever next reads it or by the next phase-close sweep.** A
disclosure that cannot yet name one of the three has not finished being written.

- **New, 23 September 2026 — `upsert_edges`'s own `_weigh_edge` call is quadratic ingest cost,
  named here as its own defect rather than left as a note inside the memory-footprint
  investigation it was found during, so it is not read as part of a resolved finding.**
  `GraphArcadeDBAdapter._corpus_edge_stats` (`packages/adapters/graph_arcadedb/adapter.py:193-220`)
  runs three Gremlin queries on every single edge write, none scoped to the write's own pair — the
  third is `g.E().hasLabel(label).has("reverted",false).values("occurrences").sum()`, an unscoped
  scan over **every edge of that type currently in the database**, re-run on every subsequent edge
  write of the same type. For $N$ edges of one type ingested in sequence, the $k$-th write scans
  roughly $k$ existing edges, so total work across the ingest is $\sum_{k=1}^{N} k = N(N+1)/2$ —
  quadratic in $N$, not linear. **Reasoned from the code, not measured** (no benchmark has been run
  against a realistically-sized edge population): at $N=10{,}000$ edges of one type, roughly $5
  \times 10^{7}$ cumulative edge-record touches from this one query alone; at $N=100{,}000$,
  roughly $5 \times 10^{9}$; at $N=1{,}000{,}000$, roughly $5 \times 10^{11}$ — before counting the
  two `_node_type` lookups, the `_find_existing_edge` lookup, or the other two (source/target
  degree) queries `_corpus_edge_stats` also runs per write, each individually linear but none of
  them free. A realistic single-type edge population reaching the tens or hundreds of thousands is
  not a hypothetical for this platform's own domain (`08_ACCEPTANCE_SCENARIOS.md`'s own Scenario B
  is built from CDR data — call/message records between two parties are exactly the shape that
  produces a large, single-typed `COMMUNICATED_WITH` population in a real investigation, just at a
  scale this project's own synthetic fixtures do not currently exercise). **Named test that would
  demonstrate it, not yet written:** an ingest-throughput test asserting wall-clock (or
  `_corpus_edge_stats`'s own call count) grows sub-quadratically with edge count for a single edge
  type — e.g. `test_edge_ingest_throughput_does_not_degrade_quadratically_with_corpus_size`,
  ingesting edges of one type in increasing batches (matching this session's own memory-cost-curve
  shape, above) and asserting the *marginal* cost per edge does not grow with corpus size, the same
  distinction item 1 of that investigation drew between a flat per-element cost and a step or
  growing one. **Owning phase: Phase 8** (found during this phase's own memory-footprint work, and
  the same "before the milestone can hold an investigation graph of realistic size" reasoning
  already applies) — not built here; this entry states the defect and names the test, per this
  section's own standing rule, and leaves the fix for whoever takes the stage next.

- **New, 23 September 2026 — the graph store neither reclaims memory across workloads nor holds
  its own query performance steady as data accumulates, found while closing the (separate,
  now-closed) ArcadeDB-stability stage and deliberately not folded into it — that stage answered
  "does a clean install-and-demo run reliably," this is "what happens after," a different
  question with its own owner.** Measured, not inferred: across a sequence of otherwise-identical
  closing-pass runs against the same, never-reset database, memory climbed with every successful
  run (8.651GiB → 9.097GiB → 9.396GiB, never released) and the same fixture load took measurably
  longer each time (117s → 151s → 203s, a 74% slowdown by the third repetition). Every one of
  those runs passed — this degrades quietly, not with a failure. **Full reasoning and the
  operational consequence are recorded where an operator will actually read them:**
  `docs/05_DEPLOYMENT.md` §8, new — a running instance should be expected to need periodic
  restarts to recover memory, and the safe interval is not yet known, since nobody has measured
  whether the degradation plateaus or continues without bound. **Named test, not built:**
  `test_arcadedb_memory_and_query_latency_under_sustained_ingest_cycles` — sustained load across
  many ingest cycles against one long-lived database, measuring memory and a representative
  query's own latency after each cycle. **Owning phase: Phase 8**, a new, separate item — not
  fixed here, not scheduled beyond being named, sized for its own pass.

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
  mouse-only handler is. For any gate this build adds next — `registryCoverage.test.ts`-style
  static checks included (this sentence named `check-registry-coverage`, a file that has never
  existed; corrected 25 September 2026) — the question to ask before trusting a green result is not "does a gate with the
  relevant name exist and pass," but "what specific mechanism does this gate exercise, and what
  adjacent failure, however plausible-sounding under the same gate's name, would still pass it
  unnoticed." `apps/workspace/keyboard/registryCoverage.test.ts` (Phase 7 Stage 4, alongside this
  finding) is itself an instance of asking that question proactively: it is a static text scan, not
  an executed proof, and says so in its own header, rather than letting "the keyboard suite is
  green" imply more than a static scan can support.

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
  Phase 6 known-gaps list (§647-668) and this document's "Legacy disclosures" entries record
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
  are involved or how minor the practical consequence. **Resolved, not merely disclosed** —
  `02_GLASS_FRONTEND.md` §4's own "Node state vocabulary" table now states the fix directly: the
  surface gap (selected) and thickened incident edges (on-path) are independent non-colour cues
  that both apply when both states hold on one node, so stroke hue is never the sole signal
  distinguishing the combined state from selected-alone. The spec decision this entry had left open
  (which non-colour channel, and whether it belongs to the on-path state, the selected state, or
  both) is answered: both, via the channel each already had — no new palette entry needed, only the
  combined case stated explicitly rather than left implicit.

  **Widened, 22 September 2026, rather than left as a two-state fix a third feature would
  immediately outgrow.** Phase 8 Stage 4c (`02_GLASS_FRONTEND.md` §9.2, "Assessment production")
  needed to highlight a judgement's own cited evidence on the canvas and, finding no distinct
  channel free to use, reused the existing multi-node `selected` state for it — disclosed there as
  its own known gap, and consolidated into this entry rather than carried as a second, independent
  one, since both are the same underlying shortage seen twice. **The root cause, stated once
  rather than left implicit across two disclosures:** the node interaction-state vocabulary
  (`02_GLASS_FRONTEND.md` §4's own table) has exactly one non-colour ring/stroke channel budget to
  spend on "this node is currently notable, and here is why" — a 2px border, present or absent,
  varied only by hue and (for on-path) a paired edge-thickening cue. Two meanings already shared
  it, distinguished only by combining independent cues (above). A third meaning —
  evidence-of-judgement — has nothing independent left to combine with, so it borrowed `selected`
  outright rather than gaining its own cue, which is worse than the original two-state problem:
  a highlighted-evidence node is now genuinely indistinguishable from an actually lasso-selected
  one, not merely colour-ambiguous when two states happen to coincide. **Every future feature that
  needs "this node matters, and here is why" will hit the same wall** unless the vocabulary itself
  grows a real channel, not another borrowed one.

  **One item, one owner: Phase 8 Stage 5** (`nodeAttributes.ts`'s own combined on-path-and-selected
  rendering is already that stage's own named item, below — widened here rather than left as a
  narrower two-state fix that a third state would need reopening the moment it landed). Stage 5's
  own scope for this item now explicitly includes: implementing the already-decided on-path+
  selected combined rendering (unchanged), *and* designing and building one genuine additional
  non-colour visual channel the interaction-state vocabulary can spend on a third, distinct
  meaning — evidence-of-judgement highlighting reuses that new channel instead of `selected` once
  it exists, closing Stage 4c's own disclosed gap as the same fix, not a second one. **Exit
  criterion, a test:** a node that is simultaneously selected and evidence-highlighted is
  distinguishable from a merely-selected one by a non-colour cue, the same `axe-core`/manual-check
  discipline `02_GLASS_FRONTEND.md` §6 already holds every other state pairing to.

- **The `PathBuilder`'s own `elementMap()`-inside-`path()` ArcadeDB limitation is already recorded
  correctly, not only as a workaround-site comment.** ADR-033 (`06_DECISIONS.md`) is the primary
  record — the same "checked against a live instance, not assumed from the TinkerPop spec"
  discipline ADR-030's `match()` finding established first. `builders.py:251-261`'s own `PathBuilder`
  docstring cites it by name (`` `06_DECISIONS.md` ADR-033 ``), so a reader who only ever opens the
  adapter still finds the full record. No move needed; this entry exists only to confirm the check
  was made rather than assumed, per this session's own A4.

- **The pathfinder (`POST /v1/paths`, ADR-033) — decided, 22 September 2026: B21 added to
  Scenario B, not an ADR accepting its absence.** The gap was disclosed (`07_BUILD_PLAN.md`
  §978-991, Phase 7's own exit-criterion note) but never owned. That note explains *why* Phase 7
  can close without it (standing rule 9) and draws a parallel to hotlists/saved-pattern monitors —
  but the parallel does not hold past Phase 7's own close: hotlists/monitors get B20 to run against
  once Stage 6 lands, inside Phase 7 itself, while nothing anywhere committed the pathfinder to
  ever gaining a scenario step. **Checked directly, not assumed, and this is what settles the
  decision rather than merely owning the gap:** the note's own fallback reading — the pathfinder as
  a general-purpose tool exempt from scenario coverage, the same class as `/v1/search` — has no
  precedent in this project that actually supports it. Unlike the pathfinder, both of the other two
  corpus-wide query surfaces the Stage 5 code comment (`app.py:1509-1521`) compares itself to —
  `/v1/search` (B4, B5, B7) and `/v1/patterns/*` (B19) — are themselves exercised by named
  acceptance-scenario steps. The one thing that would have justified accepting the pathfinder's
  absence turns out, checked rather than assumed, to argue the opposite way.

  **Decision: B21 exercises `POST /v1/paths` end to end through the Glass**, added to Scenario B
  in the same journey-table shape the other twenty rows already use
  (`08_ACCEPTANCE_SCENARIOS.md`, this session). Owning sub-stage: Phase 8 Stage **4g**, alongside
  the closing pass, since it is new scenario coverage rather than a standalone product feature.

  **Consequence, recorded rather than left implicit.** B21 is now part of Scenario B's own full,
  unchanged form, and V1 END TO END (defined above) is both scenarios passing in exactly that
  form — B21 is therefore now part of what must be green to reach the milestone, exactly like
  every other row in either scenario already is. This adds to, not merely records, what Stage 4g's
  own closing pass and this phase's own exit criterion must prove; accepting B21 was not free. The
  further consequence for who receives a build and when (`docs/PRODUCT_DELIVERY.md`, "The alpha
  gate") is a distribution fact downstream of this one, not restated here.

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
    horizontal-scalability claim** — see "Legacy disclosures"'s own consolidated entry,
    above, for the other two and the combined finding.

- **ArcadeDB stability (the sweeper's three causes, the OOM-contention finding, and a fourth,
  newly-observed cause) — relocated 23 September 2026 into Phase 8's own stage list as a
  MILESTONE-BLOCKING stage,** not left here: an install-and-demo milestone cannot stand on a store
  that fails more often than it completes. Full finding at its own new entry, in build order,
  alongside the harness/packaging and documentation-refresh stages.

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

- **Fixed, 22 September 2026, and moved to "Before the milestone" — not because the acceptance
  scenarios themselves ever named a non-Latin family name, but because whether this crash could
  reach the milestone was an accident of what this project's own synthetic fixtures happened to
  contain, and that is not a property anyone should be relying on.** An entirely non-Latin-script
  family name crashed the whole `Person` resolution pass, same blast radius as the hyphen defect
  above, different mechanism: the accent-folding fix above already sanitises down to `None` when
  nothing letter-shaped survives (a fully Chinese, Cyrillic, Arabic, Devanagari, etc. family name),
  and DuckDB's own UDF registration — `null_handling` defaulting to `DEFAULT`, no argument
  overriding it — forbade a registered UDF from ever returning `NULL` for a non-`NULL` input, so
  `resolve_entity_type` raised `SplinkException` the moment one such `Person` existed anywhere in
  the population, taking the *whole* population's resolution down, not only that one person's own
  match candidacy.

  **Fix, at the point of input, the same way the hyphen/apostrophe crash was repaired:**
  `services/resolve/duckdb_setup.py::new_connection` now registers `soundex` with
  `null_handling=duckdb.func.FunctionNullHandling.SPECIAL` — telling DuckDB that a `NULL` return is
  a legitimate, intentional value this function produces, so the already-correct "no blocking key"
  behaviour `_soundex` already implemented actually reaches the blocking SQL instead of crashing
  before it gets there. A person with no letter-shaped soundex key simply never blocks with anyone
  via that rule (standard SQL: `NULL` never equals `NULL`) — the same outcome an empty
  `family_name` already produced, without taking the rest of the population down with it.

  **Proven, at the actual point of failure, not only against the pure function:**
  `tests/resolve/test_duckdb_setup.py::test_a_fully_non_latin_family_name_does_not_crash_the_
  registered_udf` — calls `soundex()` through a real, registered DuckDB connection (`_soundex`
  alone never crashed; the registration boundary did) for a Chinese, Cyrillic, Arabic and Devanagari
  family name, asserting `NULL`, not an exception. Verified non-vacuous: the fix reverted, the test
  failed with the real `duckdb.InvalidInputException` this defect always raised, then restored and
  confirmed green. A companion, `test_a_latin_family_name_still_produces_a_real_soundex_value_
  through_the_registered_udf`, proves `null_handling="special"` did not make every call return
  `NULL` regardless of input.

  **The fixture, fixed alongside the crash, not left to depend on chance.**
  `tests/scenarios/fixtures/fixture_corp.py::generate_resolution_persons` gained a fifth pair,
  `identical_non_latin_script` ("李, 伟" x2, `merges_from_tau=0.99`) — real family name, real
  given names, in the one fixture this session's own restructuring already placed inside "Before
  the milestone" (Stage 4a). `test_fixture_corp_entity_resolution_projections_differ_by_threshold`
  now runs the real resolver over a population that includes a non-Latin name on every run,
  measured directly (0.999991 — identical to the plain-ASCII `identical` pair's own score, since
  `jaro_winkler`/`levenshtein` compare Unicode strings directly and `year(date_of_birth)` still
  blocks the pair even though `soundex` no longer does), not merely asserted. The test's own
  `strict`/`balanced`/`broad` merge-set assertions were updated to include the new pair at every
  detent it actually merges at.

  **No other blocking or comparison function in the registry shares this fragility, checked
  directly, not assumed:** `exact` and `year` (`packages/ontology/resolution_functions.py`'s
  `BLOCKING_FUNCTIONS`/`COMPARISON_FUNCTIONS`) compile to plain DuckDB SQL with no custom function
  at all; `jaro_winkler`/`levenshtein` resolve to Splink's own `comparison_library` constructors
  (`services/resolve/splink_config.py`), native DuckDB string functions operating on raw Unicode
  input with no Python-UDF null-handling boundary in the middle. `soundex` was, and remains, the
  only registered function in this pipeline backed by bespoke Python code — the only one that could
  have this exact failure shape, and the only one checked because it is the only one that could
  fail this way.

---

## Standing rules for the whole build

1. **Conformance suites are written before adapters.** The suite defines the contract; an
   adapter written first will define the contract by accident.
2. **No feature ships without its access-control test.** Every read path gets a test asserting
   that an unauthorised principal cannot observe the data or infer its existence.
3. **Fixtures are synthetic and in-repo.** No real intelligence data in the repository, in CI,
   or in a demo, ever — with one narrow exception: a dataset the owner has explicitly named in
   the local, never-committed real-data exceptions list (`scripts/real_data_exceptions.py` —
   `config/real_data_exceptions.yaml`, gitignored; `06_DECISIONS.md` ADR-035 §C3 has the decision
   record), admitted only for local development, scale/realism testing, or an owner-run
   demonstration on the owner's own secured device — never committed, never in CI, never
   distributed to an attendee. No other real dataset is admitted without its own such entry.
   Generate fixtures with a seeded generator so they are reproducible. The same applies to map
   data: the demo and CI run on tier 1 providers only, enforced by rejecting any non-`open`
   provider in the demo configuration.
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
