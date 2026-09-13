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

All eighteen records are accepted as of 13 September 2026, including all seven overrides of the
input documents. `07_BUILD_PLAN.md` is unblocked end to end; nothing in the plan now waits on an
open decision.

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

**Decision.** The MantisNexus design system governs. Hue encodes entity type across nine
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
cluster, context and namespace; drift detection against `mantis.yaml` on open; a
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
format from the same `mantis.yaml`; the harness is a generator either way.

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

---

## ADR-015 — Map providers ship as tiers, with OpenStreetMap as the shipped default

**Status.** Accepted, 13 September 2026.

**Decision.** Provider tiers, all driven from one registry in `mantis.yaml`. Tier 1 is
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

**What makes the swap safe.** Four invariants, checked by `mantis verify map`: a `Location` is
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
or `mantis map prefetch` the area of operations so live requests reveal nothing. The map shows a
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
client's own GIS team, verifiable by `mantis verify map`, and able to be wrong without affecting
anyone else. The registry already renders anything matching the source kinds, so the long tail
never needed code.

**Why the licensing fields are enforced rather than documented.** With one deployment, data
licensing is a procurement matter. Across a client base it becomes a product constraint, and the
failure mode is easy to walk into — building a demo on OS tiles under a PSGA entitlement and
showing it to a commercial client is a breach, because PSGA covers the licensed body and not
your product. So `mantis bundle` refuses to package anything marked `redistributable: false`,
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
