# 06 — Architecture Decisions

Each record states the decision, why, what it costs, and what would make it wrong. Records
marked **override** contradict one of the input documents; those are the ones to review first.

## Status register

`Accepted` means signed off and safe to build against. `Proposed` means the reasoning stands but
the decision has not been confirmed — build against it only if a delay would block you, and
expect rework if it changes. Update the status here and in the record itself when a decision is
confirmed.

| ADR | Decision | Override | Status |
| --- | --- | --- | --- |
| 001 | Three tiers separated by four typed ports | | **Accepted** — 13 Sep 2026 |
| 002 | Sigma.js as the only renderer | ✓ | **Accepted** — 13 Sep 2026 |
| 003 | Gremlin is the wire protocol and never leaves the Vault | | **Accepted** — 13 Sep 2026, with GQL amendment |
| 004 | Valkey, not Redis; OpenSearch, not Elasticsearch | ✓ | **Accepted** — 13 Sep 2026 |
| 005 | No orchestration framework in the extraction core | ✓ | **Accepted** — 13 Sep 2026 |
| 006 | Entity resolution is a query-time projection, never a merge | ✓ | **Accepted** — 13 Sep 2026 |
| 007 | Working set is server-side, capped, and delta-streamed | | **Accepted** — 13 Sep 2026 |
| 008 | Columnar OLAP and graph compute are separate ports | | **Accepted** — 13 Sep 2026 |
| 009 | The design system governs colour, not the v2 spec | ✓ | **Accepted** — 13 Sep 2026 |
| 010 | Handling, provenance and assessment objects are first-class | | **Accepted** — 13 Sep 2026 |
| 011 | Three profiles, and the cluster profile is not Compose | ✓ | **Accepted** — 13 Sep 2026 |
| 012 | Vendor demo grounding dropped from the requirements baseline | | **Accepted** — 13 Sep 2026 |
| 013 | Batch ingestion only in v1 | | **Accepted** — 13 Sep 2026 |
| 014 | MapLibre GL JS, not Leaflet | ✓ | **Accepted** — 13 Sep 2026 |
| 015 | Map providers ship as tiers, OpenStreetMap the default | | **Accepted** — 13 Sep 2026 |
| 016 | Standards and profiles, not vendor integrations | | **Accepted** — 13 Sep 2026 |
| 017 | Target the UK and the US; reprojection becomes mandatory | | **Accepted** — 13 Sep 2026 |
| 018 | The Ingest Studio edits a declarative recipe, maps POLE-first | | **Accepted** — 13 Sep 2026, interface review pending |
| 019 | Scenario A's exit criterion is split across three phases | | **Accepted** — 16 Sep 2026 |
| 020 | `ModelPort` conformance is pinned to a small, digest-verified local model | | **Accepted** — 17 Sep 2026 |
| 021 | Splink is pinned to 3.9.9, not the 4.x/5.x line, over a transitive GPL dependency | | **Accepted** — 18 Sep 2026 |

All twenty-one records are accepted, including all seven overrides of the input documents.
`07_BUILD_PLAN.md` is unblocked end to end; nothing in the plan now waits on an open decision.

One record carries a stated review point. ADR-018 is accepted on the understanding that the
Ingest Studio's interface will be reviewed once it renders, and that the review may change it —
see the scope note in that record for what a UI review can change freely and what it cannot.

---

## ADR-001 — Three tiers separated by four typed ports

**Status.** Accepted, 13 September 2026.

**Decision.** The Glass / The Conduit / The Vault, with `GraphPort`, `AnalyticsPort`,
`ComputePort` and `ModelPort` as the only crossings. Each port has a conformance suite; an
adapter is supported only if the suite is green.

**Why.** "Swappable" is a claim until something enforces it. Ports plus conformance suites are
the enforcement. They also give the tiers genuinely independent scaling, which is what the
requirement asks for.

**Cost.** An adapter layer to write and maintain, and a small performance tax from not using an
engine's most specialised features.

**Revisit if.** A single engine is chosen permanently and the portability requirement is
dropped. Nothing else justifies removing the ports.

---

## ADR-002 — Sigma.js as the only renderer · **override**

**Status.** Accepted, 13 September 2026, conditional on zoom behaviour being unaffected —
addressed below and specified in `02_GLASS_FRONTEND.md` §1.1.

**Overrides.** The research brief nominates Cytoscape.js. The Gemini specification keeps
Cytoscape.js and adds a WebGL fallback that transitions to Sigma.js above 10,000 nodes.

**Decision.** Sigma.js v3 with graphology, as the sole renderer. Cytoscape.js is not a
dependency.

**Why.** Two renderers means every node state — nine channels, three provenance strokes, six
interaction states, oklab dimming — implemented twice and kept pixel-identical, or the picture
changes when the analyst crosses a threshold they cannot see. That is a permanent maintenance
cost charged against the maintainability requirement, with a subtle failure mode. Given one
renderer, choose the higher ceiling: Sigma renders hundreds of thousands of nodes via WebGL
where Cytoscape's canvas degrades around ten thousand, and the 50k working-set cap sits inside
one range and outside the other.

**Cost.** Custom node rendering means WebGL programs rather than CSS-like styling. Mitigated by
a deliberately small node vocabulary, the v3 plugin set (`node-border`, `edge-curve`,
`node-image`, `export-image`, `layer-maplibre`), and DOM overlays for labels and menus. Sigma v4
is in alpha and closes much of the customisation gap; track it, do not depend on it.

**On zoom, which was the condition of acceptance.** Moving between cluster overview and
individual link is not compromised, and on the axis that matters it improves. Zoom and pan is
where WebGL is strongest: the camera transform is a GPU uniform, so a 50,000-node set pans at
60 fps where a canvas renderer re-rasterises every element on the CPU. Semantic zoom — different
information at different levels — is not a built-in on either library; in Sigma it is
`nodeReducer` and `edgeReducer`, called per element per frame with the current camera ratio,
which is finer control than a stylesheet gives. The four zoom bands, from community hulls at
Overview down to per-edge labels at Link detail, are specified in `02_GLASS_FRONTEND.md` §1.1.

One honest caveat. Rich per-edge decoration at high zoom — multi-line edge labels, badges on
edges — is genuinely more awkward in WebGL than in a CSS-styled canvas. The mitigation is the
DOM overlay: hovering or selecting an edge opens an HTML panel anchored to Sigma's camera with
the edge's type, occurrence count, interval, provenance and contributing records. That applies to
the one or two edges under attention rather than to all 250,000, which is where HTML is cheap.
If per-edge decoration at rest across the whole graph turns out to be a requirement, this is the
part of the decision to reopen.

Zoom-dependent clustering — collapsing a community to a meta-node and back — is a graphology
operation producing a real change to the working set, not a rendering effect. It behaves
identically whichever renderer draws it and was never part of this decision.

**Revisit if.** The working-set cap drops below 10k nodes permanently, or a per-element styling
requirement emerges that cannot be expressed in a shader and cannot move to a DOM overlay.

---

## ADR-003 — Gremlin is the wire protocol and never leaves the Vault

**Status.** Accepted, 13 September 2026, with the GQL amendment below.

**Decision.** Gremlin as the query language, TinkerPop 3.8. The Conduit composes traversals from
a bounded set of builders; no free-form Gremlin from any caller. Transport is adapter-specific —
WebSocket with GraphBinary where an engine runs a Gremlin Server listener, an HTTP command
endpoint where it does not. The guarantee is the language and the boundary, not the socket.

**Why.** Gremlin gives the widest engine choice today. But the standards direction is SQL/PGQ
(SQL:2023) and openCypher, and ArcadeDB and HugeGraph already speak both. Keeping Gremlin behind
`GraphPort` means that shift is an adapter change. Independently: a hand-written traversal cannot
be reliably access-filtered, so free-form Gremlin would be a security hole regardless.

**Cost.** A builder layer, and some expressiveness given up.

### Amendment — GQL support

**Yes, and this decision is what makes it affordable.** The Conduit builds queries through a
bounded set of builders and `GraphPort` hides the result, so a second query language is a second
adapter backend, not a rewrite. Nothing above the port knows or cares which language reached the
store.

Two readings of the question, both worth answering.

**Can the Vault speak GQL?** Architecturally yes; practically, not yet, and it is worth being
precise about why rather than claiming support that does not exist. GQL is a real standard —
ISO/IEC 39075:2024, published April 2024, the first new ISO database language since SQL, from the
same committee. What it does not yet have is an open-source implementation in this pack's
candidate set. The on-ramp the industry is actually using is **openCypher**, whose stated purpose
since GQL published is to evolve its specification toward GQL conformance by absorbing GQL
features. ArcadeDB already speaks openCypher natively, and HugeGraph ships a Cypher engine, so
the realistic sequence is Gremlin now, openCypher when a builder backend is worth writing, GQL as
engines declare conformance.

**Can analysts write GQL?** That is a different question with a harder answer, addressed under
"the expert console" below.

**The cheap insurance to take now**, in Phase 1 rather than later:

- `GraphPort` adapters declare a `dialects` capability — `{gremlin}`, `{gremlin, opencypher}`,
  `{gql}`. The Conduit selects a builder backend from what the configured adapter advertises.
- The query builders stay dialect-agnostic. They already describe intent — expand, path, match,
  aggregate — rather than emitting traversal strings, so each gains a second `render()` per
  dialect and nothing else changes.
- The `GraphPort` conformance suite is parameterised by dialect, so an openCypher or GQL backend
  proves identical results on the same fixtures before it is supported.

That is a small amount of structure now against a large saving later, and it is the difference
between "we could support GQL" and "supporting GQL is a sprint."

**The expert console, and why it is not simply switched on.** An analyst writing raw GQL
collides with the rule in the main decision: a hand-written query cannot be reliably
access-filtered, so exposing one would bypass the handling model. If a deployment wants a
power-user query surface — and research teams reasonably do — it has to be built deliberately:
parse the query, reject constructs that cannot be filtered, inject the principal's filter into
the parsed form rather than the text, and audit both the submitted and the effective query. It is
a Phase 8-or-later capability with its own ADR, scoped to a named role, not a checkbox.

One useful piece of tooling for that: **GraphGlot** (open source, Python) validates a query
against the GQL standard, reports which of the optional features it uses, and transpiles between
GQL and Cypher — all without a database round trip. That is exactly the validation layer an
expert console needs, and it also makes a dialect-parity test possible in CI.

**Revisit if.** SQL/PGQ support matures across the candidate engines — then write a second
adapter and compare, rather than migrating. Revisit sooner if an open-source engine in the
candidate set declares GQL conformance, at which point the `dialects` capability above turns a
migration into a configuration change.

---

## ADR-004 — Valkey, not Redis; OpenSearch, not Elasticsearch · **override**

**Status.** Accepted, 13 September 2026.

**Overrides.** The Gemini specification names Redis for the cache and Elasticsearch as the
JanusGraph index.

**Decision.** Valkey (BSD-3, Linux Foundation) and OpenSearch (Apache-2.0).

**Why.** Redis moved to RSALv1/SSPLv1 in 2024 and Elasticsearch has been under SSPL/Elastic
Licence since 2021. Both fail the stated open-source constraint — the same constraint the Gemini
specification correctly applies when it rejects FalkorDB for SSPL. Valkey and OpenSearch are
drop-in forks with permissive licences and foundation governance.

**Cost.** None material. Valkey is protocol-compatible with Redis; OpenSearch diverges from
recent Elasticsearch features but supplies everything this platform uses.

**Revisit if.** Never, on licence grounds. Only if a required capability exists in neither fork.

---

## ADR-005 — No orchestration framework in the extraction core · **override**

**Status.** Accepted, 13 September 2026.

**Overrides.** The research brief nominates LlamaIndex or LangChain as the orchestration layer.

**Decision.** Extraction calls `ModelPort` directly with schema-constrained decoding. LlamaIndex
and LangChain are permitted as optional adapters behind `ModelPort`, never as core dependencies.

**Why.** The maintainability requirement is explicit about patching and upgrading on each
component's own cadence. These frameworks have large transitive dependency trees and a history
of breaking changes across minor versions; adopting one puts the extraction pipeline's upgrade
cadence under someone else's control. The actual requirement — send a document and a JSON
Schema, get conforming structured output — is a hundred lines of code, not a framework. What is
genuinely hard is prompt quality, schema design and evaluation, and no framework solves those.

**Cost.** Reimplementing chunking, retry and batching. Small, and all of it worth owning. If
`PropertyGraphIndex` specifically proves valuable, write it as an adapter.

**Revisit if.** A framework's graph-extraction quality measurably beats the direct path on the
golden set by a margin that justifies the dependency.

---

## ADR-006 — Entity resolution is a query-time projection, never a merge · **override**

**Status.** Accepted, 13 September 2026.

**Overrides.** The Gemini specification states that records are "probabilistically merged into
golden records before insertion into the graph database."

**Decision.** Ingest writes source-fidelity nodes. Splink writes scored `SAME_AS` edges. The
Conduit collapses components at the session threshold τ on read. Nothing is merged in storage.

**Why.** The same Gemini document requires an adjustable matching threshold in the UI — strict
for financial investigation, loose for a missing-person search. Hard-merging at ingest fixes
that threshold at ingest time and makes the requirement unsatisfiable. More seriously, a merge
cannot be undone: a wrong merge silently attributes one person's activity to another, with no
signal that it happened. In an intelligence system that is a false-attribution defect, not a
data-quality one.

**Cost.** Every read pays a projection. More nodes stored. Both are cheap relative to what they
buy, and the projection is a pure function over a bounded working set.

**Revisit if.** Never for person-like entities. For deterministically identified types —
endpoints keyed on normalised E.164 — the merge is already deterministic and the probabilistic
path is bypassed.

---

## ADR-007 — Working set is server-side, capped, and delta-streamed

**Status.** Accepted, 13 September 2026. The 50k / 250k figures are a starting point to be
confirmed by measurement in Phase 4, not a principle — see "Revisit if".

**Decision.** 50,000 nodes / 250,000 edges, held in Valkey, streamed to the browser as
sequenced deltas. Breaching the cap offers three explicit choices; it never truncates silently.

**Why.** An investigation must survive a tab crash. Branching must be atomic. Re-projection at a
new τ must run against the source-fidelity set, which the browser does not hold. And an
intelligence picture that has been silently truncated is a correctness failure, not a
performance trade-off.

**Cost.** A cache tier to operate and a delta protocol to get right, including the reconnect path.

**Revisit if.** Measurement shows a materially higher cap is safe on target hardware. Raise the
number; do not remove the cap.

---

## ADR-008 — Columnar OLAP and graph compute are separate ports

**Status.** Accepted, 13 September 2026.

**Decision.** `AnalyticsPort` (SQL over event rows) and `ComputePort` (graph algorithms) are
distinct.

**Why.** The input documents use "OLAP" for both. They have nothing in common operationally:
one is a columnar scan over billions of rows, the other is an iterative traversal over an
in-memory adjacency structure. Different engines, different scaling curves, different staleness
tolerance. Conflating them forces a single engine choice that is wrong for one of the two.

**Cost.** One more port. Trivial.

**Revisit if.** An engine genuinely does both well at the required scale. HugeGraph with Vermeer
comes closest and would be one component behind two ports — which the port design already allows.

---

## ADR-009 — The design system governs colour, not the v2 spec · **override**

**Status.** Accepted, 13 September 2026.

**Overrides.** The v2 feature specification defines orange for unstructured-text entities, red
for structured or confirmed-threat entities, and purple for peripheral or unconfirmed profiles.
The Gemini specification carries that scheme forward.

**Decision.** The OspreyFlow design system governs. Hue encodes entity type across nine
channels, each paired with a shape. Stroke encodes provenance: solid asserted, dashed inferred,
dotted unresolved. State is an oklab mix toward the panel surface: 32% dimmed, 12% filtered out.

**Why.** The v2 scheme puts two orthogonal dimensions on one channel. Red means both
"structured source" and "confirmed threat", so a structured-source node that is peripheral has
no valid colour and the scheme fails on the first real dataset. It also leaves entity type — the
thing an analyst most needs at a glance on a canvas of ten thousand nodes — unencoded. The
design system separates the dimensions cleanly, and its palette has been computationally checked
for protanopia and deuteranopia separation above ΔE 20, with shape pairing recorded as the
mitigation for tritanopia, where nine hues cannot be separated.

**Cost.** Anyone who has seen the vendor demos this scheme came from must relearn it. Worth it.

**Revisit if.** Never as stated. A deployment may reassign entity types to channels; it may not
reassign what the channels mean.

---

## ADR-010 — Handling markings, provenance and assessment objects are first-class

**Status.** Accepted, 13 September 2026.

**Decision.** Every node and edge carries a handling block and a provenance block from its first
write. Judgements, intelligence gaps and assumptions are stored objects linked to evidence.

**Why.** The HMP Hollywood report carries handling, action and sanitisation codes on its face,
states each judgement against a probability yardstick, and lists its gaps and assumptions
explicitly. That is what an intelligence product is. None of the other input documents model any
of it, and none of it can be retrofitted — handling has to be on the data from the first write,
and an assessment linked to evidence requires the provenance model to already exist.

**Cost.** Storage overhead per element, and an access filter on every read that must be indexed.

**Revisit if.** Never. This is the difference between an intelligence platform and a graph
viewer.

---

## ADR-011 — Three profiles, and the cluster profile is not Compose · **override**

**Status.** Accepted, 13 September 2026, including the harness-controlled switch below.

**Overrides.** The Gemini specification proposes running the enterprise cluster profile via
Docker Compose profiles.

**Decision.** Compose for `local-lite` and `small`; generated Kubernetes manifests for
`cluster`. Three profiles, not two. The harness generates readable artefacts rather than
templates.

**Why.** Compose profiles are the right mechanism for selecting a component set on one host, and
the right answer for the laptop case. They are not an orchestrator: no scheduling, no rolling
update, no pod disruption budget, no horizontal autoscaling. A national-scale deployment needs
all four. Separately, the gap between one laptop and ten machines is too wide to cross in one
step; the first real deployment is usually three machines in a room, and without a profile for
that case someone improvises one that nobody else can reproduce.

Generated manifests rather than Helm because the stated preference is plain-English deployment
instructions over infrastructure-as-code. A generated manifest is a file you read and apply; if
you outgrow the harness you keep the manifests and maintain them directly, losing nothing.

**The switch is harness-controlled.** The profile choice determines the orchestrator and the
harness invokes it; nobody types `docker compose up` or `kubectl apply`. Five guards close the
specific mistakes — target confirmation showing the resolved Docker context or Kubernetes
cluster, context and namespace; drift detection against `osprey.yaml` on open; a
create/change/destroy preview before every switch; enforced backup-before-switch ordering; and a
capacity check that runs a downgrade's preflight against the existing data volume rather than the
empty case. Specified in `05_DEPLOYMENT.md` §2.4.

Two asymmetries are deliberate. The destroy path is slower than the create path and names what is
not recoverable from backup. And Compose to Kubernetes is presented as what it is — a new
environment, a replay from staged Parquet and a cutover — rather than as a toggle, because
offering it as a single button would misrepresent an hours-to-days operation as a setting.

**Cost.** Regenerate rather than patch. Accept it — hand-edited generated artefacts are the
usual way a deployment becomes unreproducible.

**Revisit if.** The organisation already standardises on Helm or Kustomise. Then emit that
format from the same `osprey.yaml`; the harness is a generator either way.

---

## ADR-012 — Vendor demo grounding is dropped from the requirements baseline

**Status.** Accepted, 13 September 2026.

**Decision.** The capabilities described in the v2 specification are adopted and restated as
requirements. Its grounding — specific YouTube case-study videos, timestamp ranges, screenshot
placeholders, and the named individuals appearing in those vendor demonstrations — is removed.

**Why.** A requirements baseline has to be verifiable by someone who cannot watch a video, and
stable when the video is taken down. The named people in those demonstrations are also not
needed: what is required is "identify an insular clique that degree centrality would miss", not
"identify this particular person". Restating the capability makes it testable against the
synthetic fixtures in `tests/`.

**Cost.** The worked examples are lost. Replaced by the two acceptance scenarios in
`08_ACCEPTANCE_SCENARIOS.md`, which come from the supplied HMP and CoLP documents and are
reproducible in-repo.

---

## ADR-013 — Batch ingestion only in v1

**Status.** Accepted, 13 September 2026.

**Decision.** Batch and micro-batch. No streaming lane.

**Why.** Neither acceptance scenario needs it, and a streaming lane brings exactly-once
semantics, backpressure, ordering and replay — a large piece of work that would delay the
capabilities that make the platform useful at all.

**Cost.** Hotlist alerting runs at ingest-batch latency rather than in real time. State the
latency explicitly in the UI so nobody assumes otherwise.

**Revisit if.** An operational requirement for sub-minute alerting appears. The ingest service's
internal queue boundary is already the seam a streaming lane would attach to.

---

## ADR-014 — MapLibre GL JS, not Leaflet · **override**

**Status.** Accepted, 13 September 2026. All seven overrides of the input documents are now
settled.

**Overrides.** The research brief nominates "something like leaflet.js". The Gemini
specification specifies "integration of Leaflet.js mapped to node coordinate properties".

**Decision.** MapLibre GL JS (BSD-3) via `@sigma/layer-maplibre`. Leaflet is not a dependency.

**Why.** The binding constraint is that the graph canvas must draw *over* the map in the same
projection, not beside it — a `Location` node with coordinates has to sit where it belongs while
pan, zoom and rotate move the graph and the basemap together. `@sigma/layer-maplibre` gives that
camera synchronisation directly, because both are WebGL. With Leaflet you run a WebGL graph over
a DOM-and-canvas map and reconcile two camera models by hand, which is bug-prone in exactly the
interaction analysts use most.

Three secondary reasons: MapLibre is GPU-rendered and holds up with a heat layer, a cluster
layer, a snail trail and a graph overlay live at once; PMTiles support makes offline basemaps a
file rather than a tile server, which is what the air-gapped requirement needs; and rotation and
pitch are required for site geospatial, where an aerial photograph is rarely north-aligned.

**Cost.** Larger bundle and a smaller plugin ecosystem than Leaflet. Both acceptable. Note that
MapLibre is the maintained open fork of Mapbox GL JS v1 — Mapbox GL JS v2 and later are
proprietary and fail the licence constraint, so the fork is the only open path in that lineage.

**Revisit if.** A Leaflet-only plugin becomes genuinely necessary. `@sigma/layer-leaflet` exists
and the change is confined to `src/map/`, so this is recoverable rather than structural.

For point layers beyond roughly 500k features, deck.gl (MIT) composes with MapLibre as an
additional overlay. Not in v1 — server-side binning through `AnalyticsPort.geo_bins` covers the
acceptance scenarios, and shipping raw points to the client is what the binning prevents.

### Amendment — accepted risk: CVE-2026-85061 in the pinned `maplibre-gl` version

**Status.** Accepted, 16 September 2026, Phase 5 Checkpoint 1, with a stated revisit trigger.

`@sigma/layer-maplibre` (the binding this ADR requires for camera sync with Sigma v3) pins its
peer dependency to `maplibre-gl: ^4.5.0`; no release of that binding supports a `5.x`/`6.x`
`maplibre-gl`, and its own `4.0.0-alpha` line requires Sigma v4-alpha, which this build does not
run. `maplibre-gl@4.7.1` — the newest release satisfying both constraints — carries
CVE-2026-85061, a critical XSS sanitizer bypass in `DOM.sanitize()`, fixed upstream only in
`6.4.1`. That fix is therefore not adoptable without dropping this ADR's mechanism entirely.

**Threat model, stated precisely.** Exploiting this needs a compromised or malicious
`osprey.yaml`/provider profile reaching MapLibre's `AttributionControl` through its
HTML-sanitizing code path — not analyst input, not document content, and not anything this
platform's handling model treats as untrusted at the point it reaches the browser.

**Mitigation.** `apps/workspace/src/map/MapView.tsx` disables MapLibre's built-in
`AttributionControl` entirely and renders a provider's attribution itself as a plain, escaped
text node. The broken sanitizer is never in the code path for that string at all — "sanitize the
input first" is not the claim here, since the sanitizer itself is what is broken.

**Recorded in `.trivyignore`** (repo root) with the same reasoning, so `make trivy` passes with
the risk named rather than silently suppressed.

**Revisit if.** Either holds: `@sigma/layer-maplibre` ships a release compatible with
`maplibre-gl >=6.4.1`, or a `maplibre-gl` `4.x` patch release backports the fix. Check both at
the start of any later phase touching `apps/workspace`'s map dependencies, not only when
`.trivyignore` is next edited by hand.

---

## ADR-015 — Map providers ship as tiers, with OpenStreetMap as the shipped default

**Status.** Accepted, 13 September 2026.

**Decision.** Provider tiers, all driven from one registry in `osprey.yaml`. Tier 1 is
OpenStreetMap built to local PMTiles and is the shipped default. Tier 2 is OS OpenData under the
Open Government Licence. Tier 3 is OS Data Hub premium under PSGA or a commercial licence,
reached through a credentialed proxy in the Conduit. ADR-016 adds tier 4 for generic OGC
services. Moving between tiers is configuration.

**Why a default that needs no procurement.** A platform whose map is blank until someone obtains
an entitlement is a platform that cannot be demonstrated, evaluated or tested. Tier 1 needs no
account, no key and no network at runtime, so the demo, both acceptance scenarios and CI all run
on it. That also removes a whole class of CI flakiness — the test suite never depends on a
third party's availability or on a key that expires.

**Why the swap must be configuration.** Ordnance Survey is free at the point of use for UK public
sector bodies under PSGA, so a deployment that starts on OSM will frequently want to move to OS
once the entitlement is confirmed — often after the platform is already in use. That has to be a
config change and a restart, not a migration.

**What makes the swap safe.** Four invariants, checked by `osprey verify map`: a `Location` is
keyed on a ULID with UPRN, TOID and OSM id held as identifiers rather than as the key;
coordinates stored in WGS84 and projected only for display; attribution and licence travelling
with the layer onto exports; styles referencing design tokens rather than literal colours.
Invariant one is the load-bearing one — keying a location on UPRN would make a move away from OS
break every edge pointing at it.

**Cost.** A tile proxy to build and operate, a second and third set of styles to maintain, and
the parity check. All modest. The OSM basemap is less authoritative than OS for UK addressing,
which is precisely why tier 2 exists and why the harness makes moving up a single command.

**The tier 3 caution.** A hosted tile API learns where you are looking. High-zoom requests over
one secure site, from an identifiable network, are an intelligence leak in themselves —
independent of the tiles' content and of any handling marking, because the leak is the request
rather than the payload. Mitigations: prefer a local provider for sensitive areas of interest,
or `osprey map prefetch` the area of operations so live requests reveal nothing. The map shows a
hosted-provider indicator whenever a tier 3 layer is live.

**Revisit if.** An organisation standardises on a provider not in the registry. That is a new
registry entry, not a revisit — which is the point of the design.

---

## ADR-016 — Standards and profiles, not vendor integrations

**Status.** Accepted, 13 September 2026.

**Decision.** Add a fourth provider tier for generic OGC services (WMTS, WMS, WFS, OGC API –
Tiles/Features). Everything beyond the four tiers is a validated **profile** in `providers/`,
not code. Ship a set of profiles with verify fixtures and no support commitment. Add
`redistributable` and `client_scope` to every provider's licence block and enforce them in the
packaging and export paths.

**Why standards before vendors.** One correct OGC implementation covers ESRI ArcGIS Enterprise,
GeoServer, QGIS Server, most national mapping agencies and nearly every corporate GIS. In
government and enterprise deployments the commonest actual requirement is not a named commercial
provider but the WMTS service the client already runs behind their own firewall. Five vendor
integrations would answer five clients; tier 4 answers most of them at once, and it is the
cheaper thing to build.

**Why profiles rather than shipped providers.** Every provider carried as code is permanent: a
style maintained against the design tokens, a CI parity test, a licence review, and a support
call whenever the vendor moves an endpoint. A profile is one validated file, authorable by a
client's own GIS team, verifiable by `osprey verify map`, and able to be wrong without affecting
anyone else. The registry already renders anything matching the source kinds, so the long tail
never needed code.

**Why the licensing fields are enforced rather than documented.** With one deployment, data
licensing is a procurement matter. Across a client base it becomes a product constraint, and the
failure mode is easy to walk into — building a demo on OS tiles under a PSGA entitlement and
showing it to a commercial client is a breach, because PSGA covers the licensed body and not
your product. So `osprey bundle` refuses to package anything marked `redistributable: false`,
the export gate carries the licence note, and CI rejects any non-`open` provider in the demo
configuration. That last rule is the commercial reason for the tier 1 default: there is always a
version of the product that can be shown to anyone.

**Deliberate exclusions, recorded so they are not rediscovered.** Google Maps tiles may not be
used outside Google's own SDK, so no profile ships at any tier — MapLibre can render them and
you are not licensed to. Bing Maps for Enterprise has been on a retirement path with Azure Maps
as the successor; confirm the position before promising it, then write a profile.

**Satellite and aerial imagery is out of scope for v1 and is a separate axis.** Maxar, Planet,
Airbus and Vexcel are scene-based and dated, needing a capture-date picker, cloud-cover filtering
and two-date comparison. Modelling them as basemap entries produces a poor version of both. When
a client needs it, build a `providers/imagery/` group against STAC, which most providers expose —
making it a standards problem like tier 4 rather than four integrations. The acceptance scenarios
use the `image` source kind, which is sufficient for site analysis.

**Cost.** Tier 4 is real work: capabilities parsing, projection handling beyond Web Mercator, and
auth patterns. The profile schema and validator are small. The licensing enforcement is small and
pays for itself the first time it stops a mistake.

**Scope.** The shipped profile set is narrowed to the UK and the US (ADR-017). Other geographies
are a profile each when a client needs one, which is the point of the format.

**Revisit if.** A client needs a provider that fits none of the four service types. That is a new
service kind in the profile schema, not a revisit.


---

## ADR-017 — Target the UK and the US; reprojection becomes mandatory

**Status.** Accepted, 13 September 2026.

**Decision.** Ship provider profiles, gazetteer connectors and handling schemes for the UK and
the US only. Treat coordinate reference system handling as a required capability rather than an
edge case.

**Why reprojection stops being optional.** Neither country's authoritative data arrives in the
projection the tiles use. UK public-sector data is overwhelmingly OSGB36 British National Grid
(EPSG:27700); US county and state data is very often NAD83 State Plane, with the zone varying by
state and sometimes within one. Supporting either country alone might have let reprojection be
deferred; supporting both makes it a first-week requirement. The rules are in
`00_ARCHITECTURE.md` §1.2.2: transform once at ingest, record the source CRS beside the original
coordinates, and reject a file whose CRS cannot be determined rather than guessing. Guessing
between NAD83 and a State Plane zone puts points hundreds of miles out and the result looks like
ordinary data rather than an error, which is the worst class of defect this platform can produce.

**The structural difference between the two.** The UK has a single national address gazetteer;
the US does not. TIGER/Line gives address ranges rather than points, the National Address
Database is voluntary and unevenly covered, and authoritative address data sits with counties and
municipalities in whatever format they publish. A US deployment federates several sources across
its area of operations. This is why `Location` is keyed on a ULID with UPRN, GNIS feature id,
TIGER GEOID and parcel identifiers held as aliases — had the design keyed on an address
identifier, the US case would have required a different data model from the UK one, and that is a
fork nobody recovers from.

**The regulatory difference.** UK handling codes and US criminal intelligence controls are not
the same shape. `uk-le.yaml` and `us-criminal-intelligence.yaml` both ship. The US scheme models
what 28 CFR Part 23 requires of criminal intelligence systems: an entry standard, a periodic
review and purge cycle, and dissemination recording. The model already carries all three —
`legal_basis`, `review_date` and the audit stream — so the additions are a scheme file, a review
queue and a purge that supersedes rather than deletes. Confirm the specifics with the client's
compliance function; the scheme format exists so their answer is configuration. Raise it early:
a system that cannot evidence periodic review is hard to operate under Part 23, and retrofitting
review dates onto loaded data is painful.

**Cost.** Two gazetteer connector families instead of one, two handling schemes, and a
reprojection path with its own test fixtures. All modest, and all of it would have been needed
for the second country whenever it arrived.

**Revisit if.** A third country enters scope. Add profiles and a scheme file; the reprojection
work and the identifier-alias design already generalise, which is most of the benefit of having
done both countries at once rather than the UK first.


---

## ADR-018 — The Ingest Studio edits a declarative recipe, and maps POLE-first

**Status.** Accepted, 13 September 2026, provisional on review of the rendered interface.

**What the interface review can change, and what it cannot.** Accepting this record commits to
four things that are expensive to reverse because other work is built on them, and to nothing
about how the screens look. Seeing the studio render should be expected to change the second
list and may well change it substantially.

*Structural — reversing these means rework elsewhere:*

- The recipe is a versioned YAML file and the studio edits it. Every loaded element is stamped
  with the recipe version that produced it, which is what makes a month-six mapping error a
  query rather than an excavation.
- One record maps to a graph of elements, not to a flat set of fields. The row template exists
  because a CDR row is two endpoints, an event, an edge and two cell sites.
- Mapping starts at the POLE class and narrows to a concrete type.
- Transforms are Knowledge Adapters with golden tests. No expression language.

*Surface — change freely after seeing it:*

- The three-pane layout, the pane order, and what sits in the inspector.
- Whether the row template is drawn on a canvas, laid out as a tree, or something else entirely.
  A canvas is proposed because it matches what the mapping produces; if it reads as fussy in
  practice, the underlying model is unaffected.
- How binding works — drag, click-to-assign, keyboard, or all three.
- The stage sequence and how much of it is a wizard rather than a workspace.
- How the profiler presents its findings and its proposals.
- Everything in the verify and review-queue screens except the rules listed in
  `09_INGEST_STUDIO.md` §7, which are behavioural rather than visual.

**To make that review cheap, prototype the Map screen before Phase 5a rather than during it.**
The recipe engine lands headless in Phase 2, so a throwaway front end over a real recipe and a
real fixture can be put in front of an analyst months before the studio is built. Finding out
then that the row template should be a tree costs a week; finding out during Phase 5a costs the
phase.

**Decision.** Ingestion gets a visual harness in the Glass. It is an editor for a versioned YAML
**recipe**, not a UI holding hidden state. The mapping surface is a **row template** — a small
graph describing what one source record becomes — rather than a column-to-field form. Mapping
starts at the POLE class and narrows to a concrete entity type. Transforms are Knowledge
Adapters only; there is no scripting language.

**Why a recipe rather than application state.** A recipe can be reviewed in a pull request,
diffed, moved between deployments, hand-written when that is faster, and attributed to the
elements it produced. Ingest configuration that lives only in an application database cannot be
audited and cannot be moved, and when a mapping error surfaces months later the affected data
cannot be identified. Versioning the recipe and stamping every loaded element with the version
that made it turns that from an archaeology exercise into a query.

**Why a row template rather than a form.** One record rarely becomes one entity. A CDR row makes
two `Endpoint` nodes, an `Event`, a `COMMUNICATED_WITH` edge and usually two cell-site
`Location` nodes. A column-to-field mapper cannot express that, and this is precisely where
ingestion tooling in this domain fails. Drawing the template in the same canvas the analyst uses
elsewhere means the mapping looks like what it will produce, and a wrong mapping is visible in
the verify step at a glance rather than being discovered in analysis.

**Why POLE-first.** POLE is the vocabulary a UK policing analyst already has. Nine concrete
entity types are the right level to validate and index against but the wrong level to open a
mapping conversation in. Asking for the POLE class and then narrowing means the studio is usable
by someone who knows the data and not this schema. See `01_DOMAIN_MODEL.md` §1.1, including the
note that POLE is Person, Object, Location, Event — Organisation is a deliberate sixth class
here and that divergence should be stated to clients rather than discovered.

**Why no scripting.** It is the most-requested feature and the one most worth refusing. An
expression language creates an unreviewable, untestable transformation layer, and the predictable
outcome is the same normalisation implemented four slightly different ways across four recipes. A
missing transform becomes a new Knowledge Adapter with a golden test file, written once and
available everywhere. The cost is a slower path for genuinely unusual sources; the benefit is
that every transformation in the platform is testable.

**Cost.** The studio is a substantial piece of frontend work — a second major canvas surface, a
profiler, a dry-run renderer and a review queue. It is also the difference between a platform an
organisation can feed itself and one that needs the vendor present for every new source, which
is the difference between a product and a project.

**Related refusals.** No joins across sources at ingest (that is resolution's job, at query time,
where it can be undone — the same reasoning as ADR-006); no aggregation at ingest; no enrichment
from external services. Face matching and biometric identification are out of scope entirely and
are deliberately not an extraction-profile option: they carry a legal basis and governance regime
wholly different from text extraction and must not be inherited by default because a vision model
is present.

**Revisit if.** A client's source is genuinely unmappable within the template model. Investigate
before conceding — in most cases the answer is a conditional element or a new adapter, and
conceding an expression language once concedes it permanently.

---

## ADR-019 — Scenario A's exit criterion is split across three phases, not satisfied by one

**Status.** Accepted, 16 September 2026.

**The contradiction.** `07_BUILD_PLAN.md` Phase 5's exit criterion, as originally written, read
"Acceptance scenario A (`08_ACCEPTANCE_SCENARIOS.md`) passes end to end" — but Scenario A's own
steps are not all buildable by the end of Phase 5. A12 needs the Clique Metric, which needs
`ComputePort`, which is Phase 7's own outcome. A13–A15 need Assessment objects, export and the
handling gate, all Phase 8 outcomes. Phase 5 builds neither. The exit criterion, taken literally,
asked this phase to demonstrate capabilities two and three phases away from existing — not a
difficult target, an impossible one, found while planning Phase 5 rather than discovered as a
surprise at the phase's own review point.

**Decision.** Phase 5's exit criterion is corrected to name what it can actually demonstrate:
Scenario A, scoped to A1–A11, plus the exit text's own already-named specifics (the weekend and
time-of-day findings, the site-grid hotspot) and the tier-1-to-tier-2 provider swap. A12 is
re-proven against the same HMP fixture when Phase 7 lands, as part of its own exit criterion.
A13–A15, the full scenario end-to-end, and the retraction-propagates assertion after A15 are
exactly what Phase 8's existing exit criterion ("both acceptance scenarios pass unchanged")
already requires — nothing new is added there, the dependency was simply never spelled out.
`08_ACCEPTANCE_SCENARIOS.md` itself is unchanged: it is still the full definition of done for
Scenario A, in one place, regardless of which phase proves which step.

**Why a doc correction rather than a silent partial build.** The alternative to naming this
explicitly was building Phase 5 against the literal exit text, quietly stopping short of it, and
letting whoever reads the build plan next assume A12–A15 either don't matter or were somehow
proven anyway. `SESSION_HANDOVER.md`'s standing instruction is that a genuine spec gap gets fixed
in the spec, not answered once in conversation and left for the next session to rediscover — this
is that fix. It was also considered and rejected to reorder phases so `ComputePort`/Assessment
land before Phase 5 purely to satisfy this one criterion; that would solve a documentation problem
by restructuring real engineering sequencing around it, the wrong direction for the fix to come
from.

**Cost.** None to the platform's eventual scope — every step of Scenario A is still proven,
by the phase that actually builds what that step needs. The cost is entirely to this document:
Phase 5, Phase 7 and Phase 8's exit criteria each now carry a cross-reference to the others where
before Phase 5 carried a promise it could not keep alone.

**Revisit if.** A future reordering moves `ComputePort` or Assessment/export earlier than currently
planned — update the phase each deferred assertion is attributed to, not this ADR's reasoning,
which stays correct regardless of which phase number ends up doing the re-proving.

---

## ADR-020 — `ModelPort` conformance is pinned to a small, digest-verified local model

**Status.** Accepted, 17 September 2026.

**Decision.** The `ModelPort` conformance suite (`tests/conformance/model_port/test_suite.py`,
`docs/07_BUILD_PLAN.md` Phase 6 Stage 1) runs against Ollama's `qwen2.5:0.5b-instruct`
(manifest digest `sha256:a8b0c51577010a279d933d14c2a8ab4b268079d44c5c8830c0a93900f1827c67`), served
from the `ollama/ollama:0.18.2` container image, itself pinned by digest
(`sha256:5a5d014aa774f78ebe1340c0d4afc2e35afc12a2c3b34c84e71f78ea20af4ba3` — an ordinary image pin,
since Ollama's own digest-pull limitation below is specific to *model* references, not the engine
image), proxied through the LiteLLM service `deploy/compose/dev.yaml` and the `conformance-model`
CI job both bring up. The suite asserts the *contract* — a schema-conforming response comes back for
a valid JSON Schema, and a malformed schema is rejected before any model call
(`InvalidExtractionSchemaError`) — never exact generated text.

**Why a real model, not a fake, and why this specific one.** `GraphPort`/`AnalyticsPort`'s own
conformance suites already establish the precedent this build holds to: prove the port against the
real backing engine `local-lite` actually ships, not a mock that could drift from what the adapter
really does. A full extraction-grade model (7–14B, `03_CONDUIT_MIDDLEWARE.md` §5.2's own default)
is too slow and too large to pull on every PR, and its sampling behaviour is not deterministic
enough to gate a build on regardless of size. A small, pinned instruction-tuned model is the
smallest thing that can still genuinely exercise constrained decoding end to end — request a
document and a schema, get conforming JSON back — which is exactly the boundary ADR-005 draws
around what `ModelPort` promises. Extraction *quality* against real language is a different
question with a different, slower gate: the golden set (Stage 3), run less frequently, is what
that's for.

**The digest pin, and why it isn't literally a digest pull.** An Ollama tag can move upstream —
the publisher re-tags `0.5b-instruct` against different weights, and every subsequent `ollama pull`
silently starts running a different model, which is exactly the nondeterminism this ADR exists to
rule out. The natural fix — pull by content digest, the way an OCI image reference can — does not
work here: tested directly against Ollama 0.18.2, `ollama pull qwen2.5:0.5b-instruct@sha256:<digest>`
and `ollama pull qwen2.5@sha256:<digest>` both return `Error: 400 Bad Request: invalid model name`.
The pin is enforced the other way round instead: pull the tag, then check the resulting local
manifest's digest (Ollama's own `ollama list` "ID" column, which is exactly this digest's first 12
hex characters — confirmed directly, not assumed) against the digest recorded here, and fail loudly
on a mismatch rather than silently proceeding with whatever the tag now resolves to. Both
`deploy/compose/dev.yaml`'s `ollama` service entrypoint and the CI job that mirrors it run this
check before the container/job is allowed to report healthy.

**Cost.** A 397MB image layer and sub-second CPU inference for a schema this small — cheaper than
any of the four stores the existing conformance jobs already stand up. The only real cost is a
model this small being a poor extractor in absolute terms, which does not matter here: nothing in
this suite grades what it extracts, only that the shape it returns is honest.

### Addendum — `embed()` folded into Stage 1, pinned the same way

**Status.** Accepted, 18 September 2026.

**Decision.** `ModelPort.embed()` is real from Stage 1 too, not deferred or left unowned.
`ModelLiteLLMAdapter.embed()` calls `all-minilm:22m-l6-v2-fp16` (manifest digest
`sha256:1b226e2802dbb772b5fc32a58f103ca1804ef7501331012de126ab22f67475ef`) through the same
LiteLLM proxy, pinned and verified by the same pull-then-verify mechanism as the extraction model
above, in the same `ollama` service.

**Why this, and why not Stage 4.** `embed()` was originally recorded as owned by no stage —
found while scoping Stage 1's own close, not assumed either way beforehand. The candidate owner
was Stage 4 (`services/resolve`, Splink), on the theory that embedding-based comparisons might be
what Splink needs it for. Checked directly rather than assumed: Splink's comparison library does
support a cosine-similarity comparison level over pre-computed embedding vectors, but Splink does
not compute those vectors itself — a caller would have to supply them — and the ontology's own
shipped `resolution` block (`packages/ontology/default.yaml`, `Person`) declares only classical
comparisons (`soundex`, `jaro_winkler`, `levenshtein`, `exact`), none of which need a vector at
all. Stage 4's own closed function-registry (this document's Stage 4 scoping) was agreed against
exactly that classical set — extending it to an embedding-based comparison was never requested and
is not implied by anything currently in `01_DOMAIN_MODEL.md` §4. Stage 4 is therefore not a real
consumer today; assigning `embed()` to it would have been picking a home for appearance's sake,
not because Stage 4's own work needs it.

`embed()` is architecturally identical to `extract()` — a single text-in call through the same
proxy, no orchestration, the adapter and conformance-suite plumbing already exist — so implementing
it now, as Stage 1 infrastructure available to whichever future phase actually wants it (a Stage 4
comparison type if the closed registry is ever extended to one, or a future phase that wires
`03_CONDUIT_MIDDLEWARE.md` §5.1's still-unowned OpenSearch indexing step), is cheaper and more
honest than deferring a two-line method a second time.

**Why a different, smaller model from extraction.** Embedding and extraction are different tasks
regardless of both happening to run on Ollama locally — an embedding model has no chat template
and nothing to constrain-decode. `all-minilm` is smaller still than the extraction pin (45MB
against 397MB) since the conformance suite only proves "one vector per input, correct and
consistent dimensionality", never embedding quality.

**Conformance scope, same discipline as `extract()`.** `tests/conformance/model_port/test_suite.py`
asserts vector count, uniform non-zero dimensionality and float type — never exact vector values,
for the same reason `extract()`'s own tests never assert exact text: hardware-dependent float
drift is possible even on a pinned, digest-locked small model.

**Revisit if.** Ollama ships genuine digest-pull support for a library-namespaced model — replace
the pull-then-verify script with a direct digest pull, same digest, no behaviour change. Revisit
the model choice itself only if the golden set's own tooling (Stage 3) needs a materially different
small model as its own CI baseline — that is a separate question from what this ADR pins, and
should not silently piggyback on this one changing.

### Addendum — Stage 2: `transcribe()`/`describe_image()` pins, and the vision CI-cadence split

**Status.** Accepted, 18 September 2026.

**Decision.** Two more pinned, digest/commit-verified models, one new serving stack:

- `transcribe()` calls `Systran/faster-whisper-tiny.en` (Hugging Face commit sha
  `0d3d19a32d3338f10357c0889762bd8d64bbdeba`), served by `speaches`
  (`ghcr.io/speaches-ai/speaches@sha256:21e3df06d842fb7802ab470dd77c25f0e8c0d22950e8d8c6ae886e851af53ef8`,
  MIT) — an OpenAI-Whisper-API-compatible wrapper around faster-whisper itself, confirmed directly
  to be what `03_CONDUIT_MIDDLEWARE.md` §5.2's "Default local: faster-whisper" resolves to, since
  faster-whisper is a Python library, not a server. LiteLLM proxies the multipart
  `/audio/transcriptions` upload to it as a generic `openai/`-shaped backend, the same "one
  OpenAI-compatible base URL" invariant `extract()`/`embed()`/`describe_image()` already hold to —
  confirmed by running the actual upload through the proxy, not assumed from either project's docs.
- `describe_image()` calls `moondream:1.8b-v2-q4_K_M` (manifest digest
  `sha256:c865c80afc38a27c2b0eaea3f77e00c0b5a631e3d3e46070927c0063d8a1853b`) — Ollama-served, pinned
  and pull-then-verified the same way `extract()`'s and `embed()`'s models are. Confirmed directly
  that this model accepts the same OpenAI vision content-part shape
  (`{"type": "image_url", "image_url": {"url": "data:...;base64,..."}}`) and the same JSON-Schema
  `response_format` as the text model, so `describe_image()` reuses `extract()`'s exact
  schema-constrained-decoding code path in `client.py` rather than a second implementation.

**The Whisper pin isn't a digest either, for a different reason than the Ollama case above.**
`speaches`'s own model-download endpoint takes a bare Hugging Face repo id and no revision
parameter — checked directly against its OpenAPI schema, not assumed. The pin is instead the
model's Hugging Face commit sha: a downloaded snapshot lands in the server's Hugging Face cache at
a directory named exactly for that commit (confirmed by inspecting the container's own cache
layout after a real download), so verifying the expected directory exists is the equivalent check,
against a different cache convention from Ollama's manifest digest.

**Why `moondream` and not a larger vision model.** The same reasoning as the text/embedding pins:
this suite proves the contract (schema in, schema-conforming JSON out), never description or OCR
*quality*, so the smallest model that can genuinely exercise vision-language constrained decoding
is the right one. It is materially larger than the other three pins regardless (1.8GB against
45MB–397MB) — there is no smaller-still tier for a vision-language model the way `all-minilm` is
for text embeddings — which is exactly why its own CI job runs on a different cadence, below.

**The CI-cadence split.** `describe_image()`'s conformance case
(`tests/conformance/model_port/test_suite_vision.py`) runs in its own CI job
(`conformance-model-vision`), gated to `push` (merge to `main`) rather than every pull request —
the same `02_GLASS_FRONTEND.md` §5 precedent that keeps a full performance-budget run off every
commit rather than gating a fast PR loop on the heaviest possible check. `extract()`/`embed()`/
`transcribe()` stay on every PR (`conformance-model`), since none of their pins carries this
model's weight. The split is at the *test file* level, not only a CI job's `--ignore` flag, so a
contributor reading `test_suite.py` alone sees exactly what runs on every PR without
cross-referencing a workflow YAML.

**Diarisation is not implemented this stage.** `TranscribeRequest.diarize=True` raises
`NotImplementedError` (`ModelLiteLLMAdapter.transcribe`) rather than silently returning every
segment's `speaker` as `None` as if diarisation had run and found nothing. Neither faster-whisper
nor `speaches` do diarisation natively — checked directly against `speaches`'s own README, which
names no such feature — and a real diarisation pipeline (e.g. `pyannote.audio`) is enough
additional weight and dependency surface to be its own scoping decision, not a Stage 2 default.
Disclosed in `07_BUILD_PLAN.md`'s Phase 6 known-gaps list, not only in this adapter's docstring.

**Revisit if.** The same triggers as the addendum above, applied per model: Ollama digest-pull
support would let `moondream`'s pin drop the pull-then-verify script; a `speaches` revision
parameter would do the same for the Whisper pin. Revisit the vision CI cadence if a smaller
genuinely-capable vision-language model appears, at which point running it on every PR may cost
little more than the text model does today.

### Addendum — Stage 3: the golden set measures this pin's regressions, not deployment quality

**Status.** Accepted, 18 September 2026.

**What the golden set's numbers are, restated here because it is easy to misread them later.**
`tests/golden/baseline.json` (currently ~0.75 recall, ~0.53 precision for its one case) is a
**CI regression detector for the exact model this ADR pins** — `qwen2.5:0.5b-instruct` — not a
measurement of OspreyFlow's real extraction quality. `03_CONDUIT_MIDDLEWARE.md` §5.2 names the
production default as a 7–14B model, fourteen to twenty-eight times larger than the CI pin, whose
own precision/recall this harness has never measured and has no basis to estimate. The full
statement of this lives in `tests/golden/harness.py`'s own docstring, which a reader touching the
golden set will see directly; it is recorded here too because a baseline number travels — it can
get quoted in a PR description or a status update — and whoever reads it there may never open
`harness.py` at all.

**A matcher bug, found by checking a suspicious result rather than trusting it.** Building Stage
3's own regression tolerance meant measuring real run-to-run variance, and an initial pass
recorded batch means as low as 0.53 with individual runs hitting `recall=0.0`. Checked directly,
per the same discipline Stage 1's witness-statement flakiness and Stage 2's repeated-run checks
already established, rather than accepted as "small models are noisy": two of the zero/low-recall
runs turned out to be the harness's own matcher failing to recognise a correctly-identified entity
— `dana_mercer` (identifier-style formatting) and `MERCER Dana` (word order) both failed exact
match against `Dana MERCER` under the original `.strip().casefold()` comparison, despite the model
having found the right person both times. Fixed in `tests/golden/harness.py`'s `_normalise()`:
separator characters (`_`, `-`) collapse to spaces and tokens are sorted before comparison — still
exact-after-normalisation, not fuzzy, since it can only ever match two already-identical multisets
of words, never two different people. After the fix, a 20-run manual trial's per-run recall never
went below 0.67, materially tighter than the pre-fix measurement, and the committed baseline
reflects the fixed matcher, not the buggy one.

**What was deliberately not fixed.** A handful of the original low-recall runs extract a bare
surname with no forename (e.g. `'MERCER'` alone) — a genuine partial-extraction miss, not a
formatting variant of a correct answer. Matching that against `'Dana MERCER'` would mean
substring/partial matching, which is fuzzy in exactly the sense ADR-020's own "deliberately not
fuzzy" design choice rules out for this harness (that comparison is Stage 4's Splink job, at query
time, over resolved entities — not a golden-set string match over raw extraction). Left as a real,
recorded miss.

**Revisit if.** A second golden case is added whose category names collide in some way that makes
"array-valued schema field" no longer an unambiguous stand-in for "entity type" (see
`tests/golden/harness.py`'s own scoping note on this). Re-measure the tolerance if `N_RUNS` or the
pinned model changes — the 0.15 figure is tied to this specific model's specific noise profile,
not a universal constant.

---

## ADR-021 — Splink is pinned to 3.9.9, not the 4.x/5.x line, over a transitive GPL dependency

**Status.** Accepted, 18 September 2026.

**Decision.** `services/resolve` (Phase 6 Stage 4) depends on `splink==3.9.9`, not the current
4.x stable line or the 5.x pre-release line, and this is a deliberate, revisit-worthy pin, not
"whatever `uv add splink` resolved to".

**Why, found live rather than assumed.** `01_DOMAIN_MODEL.md` §4 names Splink as "the right choice
over Dedupe or Zingg here" on transportability grounds (DuckDB locally, Spark on the cluster
profile) and cites its MIT licence. That is true of Splink itself, but `uv add splink` (which
resolves to the current stable release, 4.0.17) pulls in `igraph>=0.11.2` as a hard, non-optional
runtime dependency — checked directly against the installed package's own metadata, not assumed
from a changelog. `python-igraph`'s own declared licence is GPL, which fails
`scripts/licence_check.py` immediately: `licence-check: igraph 1.0.0 — 'GNU General Public
License (GPL)' is not on the docs/00_ARCHITECTURE.md §7 allowlist`. `00_ARCHITECTURE.md` §7
already rejects Neo4j Community for exactly this class of reason ("GPL reciprocity on a platform
intended for wide distribution") — the same reasoning applies here regardless of how the GPL
package arrived, as a direct dependency or a transitive one four layers into `splink`'s own
install.

**Why 3.9.9 specifically, not a different exclusion.** Checked directly, not assumed: PyPI's own
per-release metadata shows `igraph` was added to Splink's dependency list at some point in the 4.x
line and is still present in the newest 5.0.0 pre-release (`5.0.0.dev4`) — this is not a
transient regression a patch release will lift. The last release before it, `splink==3.9.9`,
depends on `phonetics` (MIT) instead and has no `igraph` dependency at all — confirmed both by
reading its PyPI `requires_dist` and by actually installing it (`uv add "splink==3.9.9"`) and
re-running `scripts/licence_check.py` clean: 68 packages, all allowed. 3.9.9's own API (the
`splink.duckdb.linker.DuckDBLinker` class, raw settings-dict comparisons and blocking rules,
`predict()`, `cluster_pairwise_predictions_at_threshold()`) was exercised directly against a
synthetic five-row DuckDB dataset before this ADR was written, not assumed to work from
documentation — blocking, scoring and threshold-clustering all behaved as `01_DOMAIN_MODEL.md`
§4 describes.

**Cost.** `services/resolve` is written against Splink 3.x's API shape (`splink.duckdb.linker`,
dict-based settings), which differs from 4.x's (`splink.Linker` plus a separate `DuckDBAPI`
backend object). A future upgrade to a 4.x/5.x release that drops the `igraph` dependency — or
one where `igraph`'s own licence changes, or a deployment accepts a recorded GPL exception the way
LGPL-3.0 already has a path for (`00_ARCHITECTURE.md` §7) — is real, non-trivial rework, not a
version-number bump. Accepted because the alternative (shipping a GPL-licensed transitive
dependency in a platform explicitly built for wide redistribution) is not a trade this project
makes anywhere else in the stack, and 3.9.9 is not a dead end: it is a real, MIT-clean, previously
stable release of the exact library the domain model names, not a fork or an unrelated substitute.

**Revisit if.** A `splink` release drops the `igraph` dependency (check `requires_dist` on PyPI
before upgrading, the same way this ADR did, not just the changelog's feature list), or `igraph`
itself relicenses, or the project's own licence register grows a reviewed-exception path for GPL
the way it already has one for LGPL-3.0's dynamic-linking case.

**Addendum, 18 September 2026 — no m/u training (expectation-maximisation).** `services/resolve`
calls `linker.predict()` directly against `comparison_library` defaults
(`jaro_winkler_at_thresholds`, `exact_match`) and never calls Splink's
`estimate_u_using_random_sampling` or `estimate_parameters_using_expectation_maximisation`. This
is a real match-quality trade-off across the whole resolution system — the same category of call
as ADR-006's query-time-projection decision — not an implementation detail, so it is recorded
here rather than only in `services/resolve/splink_config.py`'s docstring.

**Why.** Splink's own documentation is explicit that EM training needs "a few hundred, preferably
thousand" labelled or blocked comparison pairs to produce statistically meaningful m/u
probabilities. A typical investigation's `Person` population in this build is nowhere near that
size, and training per-investigation on a handful of nodes would not converge on a real signal —
it would fit noise and then present that noise as a calibrated probability, which is worse than
an honestly-uncalibrated default because it looks trustworthy. Untrained `comparison_library`
defaults make no such claim; they encode a fixed, published prior about how much a given
similarity level should count as match evidence, transportable and honestly implementation
constants, not a certificate of trained precision for this task or this investigation.

**Evidence.** Correctness was not assumed from the design argument above; it was checked directly.
`tests/resolve/test_resolution_accuracy.py` runs six hand-labelled pairs against the real
`Person.resolution` ontology config and the untrained defaults — the same "deliberate
alias-variation pattern" fixture discipline `tests/scenarios/fixtures/cdr.py` established for
phone-number renderings, applied here to names (identical rendering, case-varied plus abbreviated
given name, misspelled surname via soundex block, given-name typo, and two negative controls with
no shared identity). Building this check found two real defects in `services/resolve/resolver.py`,
both since fixed, not merely asserted around:

- DuckDB's `jaro_winkler_similarity` is case-sensitive —
  `jaro_winkler_similarity('MERCER', 'Mercer')` returns `0.44`, not `1.0` — which silently scored
  a same-person, different-case pair as a near-certain non-match (`0.0001`). Fixed by casefolding
  `PropertyType.STRING` values before they reach Splink.
- The DataFrame builder passed to `DuckDBLinker` only included `comparison_columns()`, not the
  union with `blocking_columns()` — harmless only because `Person`'s own config happens to compare
  every column it blocks on; a hypothetical entity type blocking on a column it never compares
  would have raised a DuckDB "column does not exist" error. Fixed by unioning both column sets.

With both fixes applied, all six hand-labelled pairs land on the correct side of a permissive
0.5 decision threshold, including the case-plus-abbreviation pair (`0.766`). This is evidence that
the untrained defaults discriminate correctly on the comparisons this ontology actually configures
— it is not evidence that the resulting probabilities are well-calibrated, which is exactly the
thing EM training would buy and this decision forgoes.

**Cost.** Match probabilities from untrained defaults are directional, not calibrated: a score of
`0.77` means "closer to a match than not" under fixed, published priors, not "77% of pairs this
similar are true matches in this deployment's actual population." `services/resolve/projection.py`
already threshold-gates final decisions at `DEFAULT_THRESHOLD = 0.95` rather than the permissive
`0.5` this accuracy check uses, which absorbs some of that lack of calibration, but it does not
eliminate it — an investigation with unusual name-collision statistics (e.g. a population sharing
one extended family's surname) gets the same fixed priors as one without, and a case Splink itself
would need real EM training to resolve correctly (e.g. the "D" vs "Dana" abbreviation, which only
just clears the 0.5 line here because `date_of_birth` carries most of the match weight) remains a
genuine, disclosed limitation rather than a solved one.

**Revisit if.** A deployment's investigation populations grow large enough — Splink's own guidance
puts the floor at a few hundred, preferably thousand, comparison pairs per entity type — that
per-investigation (or per-deployment, pooled across investigations under the same access
boundary) EM training would produce statistically meaningful weights rather than fitting noise. At
that point, `linker.estimate_u_using_random_sampling()` plus a labelled or blocked EM pass becomes
a real option and this addendum should be superseded, not merely footnoted.

**Addendum, 18 September 2026 — the resolution-conflict detection threshold (Phase 6 Stage 5).**
`services/resolve/conflicts.py`'s `detect_conflicts` decides whether a fresh candidate "would have
merged" a manually-split pair (`03_CONDUIT_MIDDLEWARE.md` §5.3's "a later run that would have
merged the pair records the conflict for review"). This runs corpus-wide, outside any one
investigation's session, so there is no session-specific τ to test against — the spec names the
*behaviour* here, not which threshold decides it, and the value below is this build's own choice,
not spec text.

**Decision.** The bar is `services/resolve/projection.THRESHOLD_BROAD` (0.80) — the lowest of the
three officially offered detents (Strict 0.99, Balanced 0.95, Broad 0.80) — not `DEFAULT_THRESHOLD`
(Balanced, 0.95), which an earlier draft of this stage used.

**Why.** Merging is monotonic in score: a candidate that clears Strict or Balanced also clears
Broad. Broad is therefore the one single value that catches every candidate that could merge
under *any* of the three supported settings — a candidate that does not even clear Broad could
not merge under any officially offered τ, so it genuinely is not a conflict. Checking against
Balanced instead (this stage's first draft) had a real, silent gap: a candidate scoring, say,
0.85 clears Broad but not Balanced, so an investigation actually running at Broad would have
genuinely merged that pair while the conflict check stayed silent about it. This was not decided
unilaterally — flagged to the user as an arbitrary-vs-principled call in the same category as
ADR-020's model pin, and Broad was confirmed as the right choice before landing.

**Cost.** Broad is the most permissive of the three detents, so this is the most sensitive choice
available: it will flag more candidates as conflicts than Balanced or Strict would, including some
that would never actually merge for an investigation running Strict or Balanced. That is an
intentional trade — a false-positive conflict costs an analyst one cheap `explain` look; a missed
one costs a silent bad merge going unreviewed, which `03_CONDUIT_MIDDLEWARE.md` §5.3's whole
"record the conflict for review" design exists to prevent.

**Revisit if.** The three-detent scheme itself changes (a new detent, different values), or a
future stage gives conflict detection a genuine per-investigation τ to check against instead of a
single corpus-wide bar — at which point this should check the investigation's own running
threshold directly rather than the most permissive of three fixed constants.
