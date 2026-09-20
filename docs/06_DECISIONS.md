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
| 022 | Scenario B's exit criterion is split across Phases 6 through 8 | | **Accepted** — 18 Sep 2026, three addenda |
| 023 | `imei` belongs to `Device`, `imsi` stays on `Endpoint`; a new edge gives a SIM swap one hop | | **Accepted** — 18 Sep 2026 |
| 024 | The MSISDN↔IMSI link is a deterministic ingest-path write, not a resolution problem | | **Accepted** — 18 Sep 2026 |
| 025 | The corpus-wide resolution and alerting trigger | | **Accepted** — 18 Sep 2026, addendum |
| 026 | The VAST Challenge datasets are admitted shaped, not verbatim; rule 3 is not amended | | **Accepted** — 19 Sep 2026 |
| 027 | B1 and B13's device-extraction legs stay unowned in Phase 7 | | **Accepted** — 19 Sep 2026 |
| 028 | `ComputePort`'s three tiers: Tier 1 a plain Node script, Tier 3 deferred to Phase 8a | | **Accepted** — 19 Sep 2026, addendum |
| 029 | Neither compute tier can run Leiden; both run Louvain with a connected-components fix | | **Accepted** — 20 Sep 2026 |
| 030 | `PatternQuery` widened for a pinned second root; `match()` does not work on ArcadeDB | | **Accepted** — 20 Sep 2026 |
| 031 | The repository splits into `spec/` and `process/`; `docs/` is dissolved at Phase 8's close | | **Accepted, scheduled** — 20 Sep 2026 |

All thirty-one records are accepted, including all seven overrides of the input documents.
`07_BUILD_PLAN.md` is unblocked end to end; nothing in the plan now waits on an open decision.
This table lagged the actual record count for a stretch of Phase 7 (ADR-022 through ADR-029 were
written but never added here) — caught and closed in the same change that added ADR-030, not
worth its own record.

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
proven anyway. `CLAUDE.md`'s own standing rule is that a genuine spec gap gets fixed
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

---

## ADR-022 — Scenario B's exit criterion is split across Phases 6 through 8, not satisfied by Phase 7 alone

**Status.** Accepted, 18 September 2026.

**The contradiction.** `07_BUILD_PLAN.md` Phase 7's exit criterion reads "Acceptance scenario B
passes end to end" — but a step-by-step re-check of `08_ACCEPTANCE_SCENARIOS.md` Scenario B (B1
through B20) against the working tree and every phase's own bullet list finds six of its twenty
steps have no Glass screen and no phase committed to building one. B6's document view (the
Dossier, `00_ARCHITECTURE.md`'s own named Glass component) is `apps/workspace/src/dossier/`, an
empty directory. B9's resolution-threshold slider, B10's `explain` rendering and B11's manual-link
control were shipped by Phase 6 as API endpoints only (`services/api/resolution.py`), disclosed as
such in Phase 6's own gaps list — "no Glass/frontend screens ... backend/API only, consistent with
every other Phase 6 stage" — but the disclosure named the extraction review queue, not resolution
by name, and nothing after Phase 6 picked either half up; the Glass's own delta client
(`apps/workspace/src/workingset/store.ts`) still receives the `reproject` delta Phase 6's
threshold endpoint sends and explicitly does not act on it. B16's cross-case timeline overlay and
B18's playback-driven snail trail are named in `02_GLASS_FRONTEND.md` §3.4/§3.5 and appear in
Phase 5's own outcome bullet ("playback", "multi-track") — but `apps/workspace/src/timeline/
Timeline.tsx`'s own header comment records that Checkpoint 2 deferred `playback`, `multi-track`
and `cross-case overlay` past Phase 5, a deferral never carried into this document's Phase 5
known-gaps list, so the bullet's own wording still reads as delivered. Phase 7's bullet list —
compute adapters, the metrics panel, the visual query builder, hotlists/monitors/alert inbox, the
pathfinder — names none of these six.

Two further steps have a working mechanism with no way to trigger it inside a running deployment,
which is a different kind of gap from the six above and not fixed by moving a Glass screen between
phases. B8's resolution and B13/B20's alerting all need a corpus-wide job; Phase 6's own gaps list
already discloses that `resolve_entity_type`/`write_same_as_edges`/`detect_conflicts`/
`record_conflicts` are real and tested but nothing schedules or triggers a run against the live
corpus, and no phase since has claimed the trigger. B15 needs a single traversal from a SIM
`Endpoint` to a `Device`; the shipped ontology (`packages/ontology/default.yaml`) declares `imei`/
`imsi` as identifiers on both an `Endpoint` (`endpoint_kind`) and a separate `Device` type, with no
edge connecting them directly — only `USES` (`Person → Endpoint`/`Device`), a two-hop path through
a person, which is exactly the "special case" `01_DOMAIN_MODEL.md`'s own rationale for `Endpoint`
over `Phone` says this design is meant to avoid.

One step the same re-check flagged as suspect turned out to be already correctly claimed: B14
("open the alert into a pre-populated investigation ... a link to the originating investigation")
reads as unclaimed from Phase 7's bullet text alone, but `02_GLASS_FRONTEND.md`'s own "Hotlists and
watchlists" paragraph — the section Phase 7's "Hotlists" bullet is shorthand for — names "a
one-click jump into a pre-populated investigation" as intrinsic to that capability, not a separate
one. B14 needs no reattribution.

**Decision.** Phase 7's exit criterion is corrected to name what it actually proves: Scenario B,
scoped to B1–B5 and B7 (already proven by Phases 2–4), plus B12–B14, B19 and B20 (this phase's own
hotlist, alert-inbox, visual-query-builder and saved-pattern-monitor work), plus the Clique
Metric/A12 re-proof already in the text. B6, B9–B11, B16 and B18 — the six Glass screens no phase
has claimed — move to Phase 8, alongside its existing browser-harness/admin-console work.
`08_ACCEPTANCE_SCENARIOS.md` itself is unchanged: it remains the full definition of done for
Scenario B in one place, regardless of which phase proves which step.

B8, B13, B15 and B20's remaining blockers — the corpus-wide resolution/alerting trigger, and the
`Endpoint`-to-`Device` traversal — are not settled by this reattribution and are recorded
separately under `Gaps with no owning phase`, because moving a Glass screen to the phase that will
build it is a documentation fix, and building an ingest-triggered resolution job or correcting an
ontology's edge types is not.

**Why grow Phase 8 rather than Phase 7's bullet list.** Phase 7's outcome is "the remaining two
analytical capabilities" — pattern analysis and hotlist alerting — a scope that is already
backend- and metrics-heavy on its own: three `ComputePort` tiers, a visual query builder compiling
to Gremlin, an alert inbox. Adding a document viewer, three resolution controls, a cross-case
timeline mode and playback animation would roughly double the phase's Glass surface with work that
has nothing to do with graph analytics, for no better reason than that two earlier phases used UI
words in their own outcome bullets without building the UI. Phase 8 already runs a comprehensive
closing pass — "both acceptance scenarios pass unchanged" is its existing exit criterion, and it
already carries the browser harness, the admin console and the last two adapters. Adding the
remaining Scenario B screens to that pass is the same shape of fix ADR-019 already made for
Scenario A's A13–A15, not a new pattern being introduced for Scenario B alone.

**Why a doc correction rather than a silent partial build.** The alternative was letting Phase 7
close against the literal old exit text, quietly stopping six steps short of it, and leaving
whoever reads the build plan next to assume B6/B9–B11/B16/B18 either don't matter or were somehow
proven anyway — the exact failure mode ADR-019 already named for Scenario A, and the one this
document's own Phase 5 and Phase 6 known-gaps lists were supposed to prevent by disclosing a gap
where it was found. Two of the six gaps here were disclosed once, in a source comment or a
loosely-worded outcome bullet, and never carried into this document where the next phase's own
scoping would actually see them; that is the specific mistake this ADR is closing, not merely the
gap itself.

**Cost.** None to the platform's eventual scope — every step of Scenario B is still proven, by the
phase that actually builds what it needs. The cost is entirely to schedule and to this document:
Phase 7 closes without Scenario B passing end to end, which was already true before this ADR and is
now written down rather than discovered at the phase's own review point; six Glass screens move one
phase later than a literal reading of the old exit text implied; Phase 7's own B12–B14/B19–B20 work
still cannot be demonstrated against a live deployment (as opposed to fixture data assembled by a
test harness) until the corpus-wide trigger gap is separately closed.

**Revisit if.** A future reordering moves the Dossier or the resolution Glass controls earlier —
update the phase each deferred step is attributed to, not this ADR's reasoning, which stays correct
regardless of which phase number ends up building each screen. Also revisit if the corpus-wide
resolution/alerting trigger turns out to need Glass surface of its own (a review queue for pending
matches, say) rather than a pure backend job — in which case it stops being a `Gaps with no owning
phase` entry and becomes a seventh step in this same reattribution.

**Addendum, 18 September 2026 — Phase 6a replaces half of the Phase 8 assignment, and B15 leaves
this ADR for its own.** Two things above turned out to be wrong on the same day this ADR was
accepted, both found by re-reading the decision against the rest of the plan rather than against
Scenario B alone.

*B15 does not belong in "recorded under `Gaps with no owning phase`."* That section's own
preamble defines an entry there as something no phase's bullet list claims at all — an unowned
intention. B15 is a different kind of problem: `packages/ontology/default.yaml` already declares
`imei` on both `Endpoint.endpoint_kind` and `Device.identifiers`, a live contradiction between two
things that both exist, not an absent one. Standing rule 7 (a disagreement between the pack and
what was built is an ADR, not a gaps entry) applies directly. B15 is withdrawn from this ADR's
"Decision" and "Cost" paragraphs and given its own record, ADR-023, which also finds that Phase 7's
pathfinder and visual query builder compute over the exact traversal shape B15 questions — so
unlike the other five steps this ADR reattributes, B15 is resolved *before* Phase 7 begins, not
deferred past it. Phase 7's exit criterion (`07_BUILD_PLAN.md`) now scopes B15 in alongside A12 as
a step re-verified there rather than newly built there.

*Growing Phase 8 by six screens was accepted without pricing what Phase 8 already carries.* Phase
8 is the largest phase in the plan and the one whose exit criterion cannot slip: assessment
objects, the yardstick loader, export and the handling gate, two conformance-green adapters, the
entire browser harness and admin console, a headless CLI mirroring every screen, generated
Kubernetes manifests and runbooks, against an exit criterion of both acceptance scenarios passing
unchanged on both profiles. Adding six more screens to that load without comment understated the
decision's own cost.

The repository already has a precedent for exactly this shape of problem: Phase 5a exists because
the Ingest Studio — a wholly new analyst-facing surface over Phase 2's headless recipe engine —
was a coherent unit worth its own phase rather than a bullet added to Phase 3 or folded into
Phase 8 (ADR-018). B6 and B9–B11 are the same shape: a wholly new Glass surface over Phase 6's
extraction and resolution API, which shipped zero screens by its own gaps list's own words. B16
and B18 are not that shape — they are two small, incremental features (a second track on an
existing Timeline, a snail-trail mode on the existing Map) added to components Phase 5 already
built and Scenario A already exercises daily, not a new surface built from nothing.

**Revised decision.** B6, B9, B10 and B11 move to a new **Phase 6a — The analyst-facing surface
over extraction and resolution** (`07_BUILD_PLAN.md`), sequenced immediately after Phase 6 and
before Phase 7, mirroring where Phase 5a sits between Phase 5 and Phase 6. It calls Phase 6's
existing endpoints exclusively; no new backend route. B16 and B18 remain Phase 8's addition, now
priced correctly as two incremental features rather than folded in among four screens that needed
a phase of their own. This does not reopen the core finding above — Phase 7's own bullet list
still does not, and should not, grow to cover any of the six.

There is a second reason to prefer a named phase over folding this into Phase 8's queue, beyond
cost. `DESIGN_PROVENANCE.md` §6 still records that the Ingest Studio's own analyst review — the
one ADR-018 built the prototype-before-Phase-5a specifically to make cheap — "has not happened,"
a claim `NEXT_STEPS_PHASE7.md` §5 already flags as stale against the 15 September handover and
commit `87dbb7b`, itself unresolved because no single phase owned closing the loop on it. A named
Phase 6a, with its own exit criterion, is a place an analyst review of the Dossier and the
resolution controls is a checkable exit item rather than an assumed side-effect of "Phase 8 also
did some Glass work" — the same discipline ADR-018 established once, now applied to the surface
Phase 6 left unbuilt.

**Addendum, 20 September 2026 — Phase 8 has grown twice more since the addendum above, and this
time the growth is not the same shape.** This ADR's own first addendum weighed B16/B18 against
Phase 5a's precedent and correctly found them absorbable: two small, incremental features added to
components Phase 5 already built, not a new surface needing its own phase. Since then, Phase 8 has
absorbed two more additions, and a third finding, none processed against that same question until
now:

- **ComputePort Tier 3** (`06_DECISIONS.md` ADR-028): GraphFrames on Spark or HugeGraph Vermeer,
  registering in Phase 8's `cluster` profile because the dev host cannot host it at all.
- **The Postgres connection-pool exhaustion finding** (Phase 7 Stage 1): two live Conduit
  instances together exhausted `max_connections` — a hardening requirement that lands on the
  cluster profile by definition (concurrent instances are what a cluster profile is), and one no
  bullet in Phase 8's own list currently names.
- B16/B18 (above) remain correctly absorbed and are not reopened by this addendum.

**The finding, and why it is not the same question the addendum above already answered.** That
addendum's own test was cost — bullet count, added surface, whether Phase 8's existing closing
pass could absorb the work without comment. Tier 3 and the pool-hardening finding fail a
different, sharper test: verification profile, not size. Judgements/assumptions, export, the
yardstick loader, the browser harness/admin console, the headless CLI and the two existing
adapters (`graph_janusgraph`, `analytics_clickhouse`) are all provable on `local-lite`, or on a
docker-compose cluster-profile stand-in for one. Tier 3 cannot be — ADR-028's own finding was that
a local Spark/HugeGraph Vermeer session cannot coexist with this host's other services at all, not
merely that it is slow or awkward there. The pool-hardening finding is the same shape: it only
exists because concurrent instances are the cluster profile's own defining property, so it cannot
be demonstrated anywhere else either. Phase 8's own exit criterion — both acceptance scenarios
pass unchanged on `local-lite` and on `cluster` — now depends on two items that share a distinct,
harder verification story from everything else the exit criterion already covers, and nothing in
Phase 8's own bullet list names the pool-hardening item at all.

**Revised decision, 20 September 2026 — accepted.** The split is made, following this ADR's own
established precedent (Phase 5a for the Ingest Studio, Phase 6a for B6/B9–B11) rather than
inventing a new pattern. A new **Phase 8a — The cluster profile** (`07_BUILD_PLAN.md`), sequenced
after Phase 8, takes `adapters/graph_janusgraph`, `adapters/analytics_clickhouse`, ComputePort
Tier 3, the Postgres connection-pool hardening (Phase 7 Stage 1's own finding), and the `cluster`
half of the exit criterion. Phase 8 keeps judgements/assumptions, the yardstick loader,
export/the handling gate, the browser harness/admin console, the headless CLI, generated
Kubernetes manifests, B16/B18, and now reads its own exit criterion against `local-lite` alone —
each phase's own criterion is a test it can actually run on the infrastructure it has, not a
criterion split across two without saying so.

**Every reference to "Phase 8's own cluster profile" is chased down, not assumed limited to the
two named here.** ADR-028's own Tier 3 deferral and this document's Phase 7 known-gaps entry for
the connection-pool finding both pointed at Phase 8's cluster profile by name and are corrected in
the same change to point at Phase 8a instead; `07_BUILD_PLAN.md` itself is searched for every
other citation of Phase 8's cluster work rather than trusting that these two were the only ones.

---

## ADR-023 — `imei` belongs to `Device`, `imsi` stays on `Endpoint`, and a new edge gives a SIM swap one hop

**Status.** Accepted, 18 September 2026.

**The contradiction.** `01_DOMAIN_MODEL.md`'s own embedded ontology (§1) declares `Endpoint` with
`endpoint_kind: enum [msisdn, imsi, imei, email, handle, iban, card]` and, four lines later, a
separate `Device` entity type — with no identifiers of its own in the doc's own illustration, so
the doc never actually says what identifies a `Device` node. The shipped ontology
(`packages/ontology/default.yaml`) resolves that silence by giving `Device` `identifiers: [imei,
imsi]` — which now claims both values `Endpoint.endpoint_kind` already claims. One physical
handset can therefore exist as two nodes of two different types, in a platform whose own ADR-006
position is that duplicate identity is never merged in storage but reconciled by a scored `SAME_AS`
edge at query time; nothing here is scored, and nothing reconciles the two. The domain model's own
"Why `Endpoint` rather than `Phone`" section is unambiguous about why this matters: "a mobile
number, a WhatsApp handle, an IMEI and an IMSI are the same *kind* of thing analytically... The
journey's pivot is a suspect swapping SIMs while keeping a handset... modelling them as one
`Endpoint` type with an `endpoint_kind` makes it a single hop." Neither the doc's own embedded
ontology nor the shipped one currently delivers that single hop: the only edge either declares
between an `Endpoint` and a `Device` is `USES` (`Person → Endpoint, Device`), a two-hop path
through a person, which is exactly the "special case" the cited rationale says this design exists
to avoid. `08_ACCEPTANCE_SCENARIOS.md` B15 ("both SIMs link to one device; the SIM-swap pattern is
one traversal, not a special case") is the literal test this gap fails.

**Why none of the three options first considered is quite right as posed.** IMSI and IMEI are not
interchangeable, and every option that moves them as a pair gets this wrong. An IMSI, like an
MSISDN, identifies a subscriber — the SIM — which is squarely the "addressable point a person uses
and that can be swapped" the `Endpoint` rationale describes. An IMEI identifies the handset itself,
a physical object a SIM is inserted into, not an address a person is reached at. `Device`'s own
shipped identifier list (`[imei, imsi]`) already conflates the two by putting a SIM identifier on
the handset type — a second, sharper defect than the duplication itself, and one that survives
untouched under a naive reading of any of the three options ("both stay", "`Device` owns both", or
"`Endpoint` owns both") unless the split below is made explicit.

**Migration cost, checked against the working tree rather than assumed.** No real ingested data
uses either shape today. `Device` and an `Endpoint` of kind `imei`/`imsi` appear nowhere but
ontology declarations, JSON Schema, and three test/fixture references — `tests/resolve/
test_resolver.py:62` (a standalone `EntityTypeDef` in a unit test), `tests/ontology/
test_validation.py:26` (a standalone `EdgeTypeDef` in a unit test), and `apps/workspace/perf/
fixture.ts:10` (a synthetic performance-test entity list) — none of them real or persisted graph
data. `packages/knowledge_adapters/imei.py`/`imsi.py` are pure format normalisers, indifferent to
which entity type eventually consumes their output. This means every option below costs the same,
close to nothing, in migration terms; the choice is about correctness and the design system's own
constraints, not about disturbing anything already loaded.

- **Option 1 (`Device` owns `imei` and `imsi`; both leave `Endpoint.endpoint_kind`).** Cheap, but
  reproduces `default.yaml`'s own defect — an IMSI identifying a handset — just more explicitly.
- **Option 2 (`Endpoint` owns both; `Device` is removed).** Matches the "Why `Endpoint` rather than
  `Phone`" prose most directly, but costs more than it first appears: `01_DOMAIN_MODEL.md` §1.1
  states "nine entity types, nine data channels... not a coincidence" as load-bearing for the
  design system's channel/shape allocation. Removing `Device` drops the count to eight and
  requires rewriting that passage too, and gives up the one type naturally suited to holding
  seizure-time forensic properties (make, model, colour) that do not belong on an "addressable
  point" record.
- **Option 3 (both stay; a `SAME_AS`-style edge connects them).** `SAME_AS` (`system: true`) is
  documented and property-shaped for *probabilistic* resolution — `score`, `model_version`,
  `comparison_vector`, written by Splink under a τ. A SIM-in-handset pairing carries none of that
  uncertainty; it is either asserted or it is not. Reusing `SAME_AS` for a deterministic fact would
  overload a system edge type with a second, incompatible meaning rather than fix the model.

**Decision.** `imei` moves to `Device` as its identifier; `imsi` stays on `Endpoint` alongside
`msisdn`, since both identify a subscriber, not a handset. `Endpoint.endpoint_kind`'s enum drops
`imei`. A new edge type, `PAIRED_WITH` (`Endpoint → Device`, `directed: true`, `temporal: true`),
records that a given SIM `Endpoint` was installed in a given `Device` over a stated window —
**only an `Endpoint` of kind `imsi` writes this edge.** `msisdn` never does: an MSISDN and the
IMSI it is dialled through are the same SIM observed by two different technical channels (a CDR
names the MSISDN; a device extraction or HLR record names the IMSI), which is a duplicate-identity
question, not a pairing one — precisely the shape `SAME_AS` exists for and the same pattern
Scenario B already uses elsewhere (B8's handle-to-endpoint resolution, B11's manual link).
`WorkingSetService.manual_link` (`services/api/working_set/service.py`) already establishes the
right property shape for a directly-known, non-Splink link — `{"score": 1.0}` only, leaving
`model_version`/`comparison_vector` unset rather than inventing values a model never produced —
and this reuses that shape rather than adding a fourth option nobody proposed. `USES`
(`Person → Endpoint, Device`) and `PRESENT_AT` (`Person, Device, Vehicle → Location`) need no
change — a person already correctly uses a device as well as a SIM, and a device already correctly
has its own location history; both were right about `Device` all along, only the identifier
overlap was wrong.

**B15's own traversal is one hop for the SIM→Device leg specifically, not for the whole journey.**
An `Endpoint` of kind `imsi` carries one `PAIRED_WITH` edge into the `Device` node, so two swapped
SIMs both resolve to one handset in one traversal — the literal claim B15 makes, and all it makes.
Getting there from B5/B7's own landing point (an `Endpoint` of kind `msisdn`) is a second, separate
hop: `Endpoint(msisdn) --SAME_AS--> Endpoint(imsi) --PAIRED_WITH--> Device`, two graph edges,
collapsing to one presented node at the resolution projection the same way every other `SAME_AS`
in this scenario does — not a special case for this pairing, and not a claim that reaching the
handset from the number is itself "one hop." Neither the ontology's `from: [Endpoint]` (entity
type only) nor `validate_edge_endpoints` (`packages/ontology/validation.py`) can enforce the
`imsi`-only convention at the `endpoint_kind` level — this is documented in `default.yaml`'s own
comment and in `01_DOMAIN_MODEL.md`, not schema-checked, the same "disclose what the schema can't
enforce" pattern already used elsewhere in this ontology. `Device` keeps its ninth channel and
shape unchanged, so `01_DOMAIN_MODEL.md` §1.1's nine-and-nine claim stays true, and it gains a real
purpose beyond a bare identifier bag: the anchor for a handset's own physical properties and its
location history, addressed through whichever SIM was paired to it at the time.

This is closest to the first option as posed, refined by the asymmetry above — not a selection
among the three unmodified.

**Addendum, 18 September 2026 — Question 2 shipped unresolved, then fixed before anything built
on it.** This ADR's own "Why none of the three options... is quite right" section answered
*whether IMEI and IMSI move together* but never settled a second, distinct question the approved
implementation plan also asked: does an MSISDN `Endpoint` ever carry `PAIRED_WITH` directly, or
only an IMSI `Endpoint`? The Decision paragraph above originally said "two `Endpoint` nodes of kind
`msisdn`/`imsi`, each with its own `PAIRED_WITH` edge" — implying msisdn pairs directly — while
`01_DOMAIN_MODEL.md`'s prose said only "each SIM `Endpoint`," and the ontology's own
`from: [Endpoint]` permitted either reading. The one conformance test written against this ADR
exercised only `imsi`-kind endpoints, so nothing would have failed had the ambiguity gone either
way in a future writer. Found and corrected here, in the same migration, before any ingest or
recipe code was written against either reading — the Decision paragraph above is the corrected
text, not a later revision layered on top of it. `tests/conformance/graph_port/test_suite.py`
now carries a second case proving the two-hop shape specifically: `expand` one hop from an MSISDN
reaches its `imsi` `Endpoint` but not the `Device`; two hops reaches all three.

**Cost.** One ontology edit (`packages/ontology/default.yaml`, mirrored in `01_DOMAIN_MODEL.md`
§1's own embedded copy, per this project's own rule that a correction to the pack is a diffed edit
against the working copy, never a silent divergence) and one new edge type. Three test/fixture
references to `Device` update their own literal identifier lists; none touches persisted data,
because none exists yet. `services/ingest/profiler.py`'s pattern-recognition list and both
Knowledge Adapters are unaffected — they normalise a raw value, not the entity type it lands on.

**Lands before Phase 7, not inside it.** `07_BUILD_PLAN.md` Phase 7 builds the pathfinder
(access-filtered k-shortest paths) and the visual query builder, both computing directly over
traversal shape; B20 lets an analyst save a pattern as a standing monitor. Shipping either against
today's two-hop shape and correcting the ontology afterwards would silently change what an already
saved pattern matches, and would mean re-baselining `ComputePort`'s "identical values within
tolerance" conformance fixture against a topology that moved under it mid-phase. Since no real data
exists yet to migrate, there is no cost to fixing this now and a real, avoidable one to fixing it
later — this lands before Phase 7's own Session 5 (schemas and the `ComputePort` conformance
suite), the same pre-phase slot `01_DOMAIN_MODEL.md` §8.1's pattern-binding question already
occupies for the same phase.

**Revisit if.** A deployment needs a `Device` that is not a comms handset at all (a laptop, a
scanner, an IoT sensor with no IMEI) — nothing here prevents a `Device` node from carrying no
identifier value yet, the same way a `Person` node carries none of its four candidate identifiers
until one is confirmed, so this should not itself force a revisit; only a genuine second identifier
scheme for non-phone devices would.

**Addendum, 18 September 2026 — the two-hop claim was stated one layer higher than this ADR
builds.** This ADR's own Decision paragraph says the msisdn→imsi→Device path "collaps[es] to one
presented node at the resolution projection the same way every other `SAME_AS` in this scenario
does." That is true of the *cluster assignment* `services/resolve/projection.py`'s `compute_clusters`
produces — its own docstring is explicit that this is "collapse, not merge": `NodeId -> ClusterId`
only, no `Node` object touched, and "whether/how the Glass renders same-cluster nodes as one
visual entity is a rendering question for that tier." It is not true that anything in this build
today renders that collapse to an analyst — that rendering is Phase 6a's own unbuilt Glass work
(`07_BUILD_PLAN.md`), the same as the resolution-threshold slider and `explain` view it already
owns. `08_ACCEPTANCE_SCENARIOS.md` B15's own wording ("the SIM-swap pattern is one traversal, not
a special case") is a claim about the raw `GraphPort` shape, which `tests/conformance/graph_port/
test_suite.py`'s two `PAIRED_WITH`/`SAME_AS` cases prove; a *second*, separate claim — that the
two hops present as one node to an analyst — was never tested at the layer that would actually
produce that, until `tests/services/api/working_set/test_resolution_threshold.py`'s
`test_msisdn_and_imsi_endpoints_cluster_together_the_device_does_not` closed it at the one layer
this build has today: cluster assignment. Recorded here rather than only in that test's own
docstring, since this ADR is what a future reader will check the claim against.

---

## ADR-024 — the MSISDN↔IMSI link is a deterministic write from the ingest path, not a resolution problem

**Status.** Accepted, 18 September 2026.

**The contradiction.** ADR-023's own corrected answer to its second question routes B15's
msisdn leg through `SAME_AS`: `Endpoint(msisdn) --SAME_AS--> Endpoint(imsi) --PAIRED_WITH-->
Device`. But nothing in this build can produce that `SAME_AS` edge. `Person` is the only entity
type with a `resolution:` block anywhere in `packages/ontology/default.yaml` (line 77), and
`tests/resolve/test_resolver.py`'s own `test_no_resolution_config_returns_no_candidates` asserts
the direct consequence: `resolve_entity_type` returns `[]` for any type with no resolution
config, `Endpoint` included. `tests/scenarios/fixtures/seizure_record.py` writes the msisdn↔imsi
`SAME_AS` by hand, in the fixture, because nothing else in this build ever would. In a real
deployment, an analyst reaches the handset from the number only if someone has already run
`manual_link` for that specific pair — for every SIM, every time, with no route that ever
surfaces the need to do so.

**Why Splink resolution (Option a) is the wrong tool, not merely a hard configuration.** Checked
against `packages/ontology/resolution_functions.py`'s closed comparison/blocking registry, not
assumed: every comparison function there (`jaro_winkler`, `levenshtein`, `soundex`, `exact`)
scores *similarity between values of the same kind* — the mechanism that makes a misspelled
`family_name` resolvable. An MSISDN (`+447911123457`) and the IMSI of the SIM it is dialled
through (`234150123456782`) are not one value seen twice with noise; they are two different
identifier systems (E.164 numbering; 3GPP subscriber identity) that name the same SIM by a
carrier/HLR record's own say-so, with no lexical resemblance a comparison function could ever
detect. Blocking fails the same way: a blocking key needs a cheap, shared derived value to bucket
candidates before the expensive pairwise comparison (`soundex(family_name)` for `Person`), and
nothing derivable from an MSISDN's own digits and an IMSI's own digits would ever land them in
the same bucket. Giving `Endpoint` a `resolution:` block for this pair means either comparing
every MSISDN against every IMSI in the corpus with no blocking at all — exactly what blocking
exists to prevent — or inventing a blocking key that corresponds to nothing the values actually
share, which is building a fake signal to make Splink do a job it was never suited for.

**Why "disclose as unbuilt, no owning phase" (Option c) is also rejected, and for a different
reason than Option a.** The gap is real, but leaving it merely disclosed while a conformance suite
already exists that only passes because a fixture hand-writes the edge the resolver would need to
produce is the same defect this whole ADR-023 exercise was built to close: an invariant tested at
a layer that doesn't actually produce it. Recording where the mechanism lives, even before it is
built, is the fix; recording that it doesn't exist and stopping there is not.

**Decision.** The link is a direct, asserted write, not a probabilistic match. A device
extraction (or a carrier/HLR record) that reports an IMSI and an MSISDN together on one
structured record is not proposing a match under uncertainty — it is stating a fact the tool
already confirmed, the same category as a CDR row's own `value_raw`/`value_normalised`
(`ASSERTED`, never `inferred`). The property shape reuses `WorkingSetService.manual_link`'s own
precedent for a directly-known, non-Splink link exactly: `{"score": 1.0}`, `model_version`/
`comparison_vector` left unset. The natural home is the ingest recipe engine's own row-template
mechanism (`services/ingest/engine.py`) — the same mechanism that already turns one CDR row into
two `Endpoint`s, an `Event` and a `COMMUNICATED_WITH` edge
(`tests/scenarios/fixtures/cdr_recipe.yaml`) — extended so a row template can declare "these two
fields on this row name the same SIM" and have the engine write the `SAME_AS` deterministically,
using `on_match: reference` to find each `Endpoint` by its own declared identifier, the same
mechanism ADR-023 already established for `PAIRED_WITH`.

**Cost and owning phase — this depends on a connector this build has never had, and that gap has
never been written down before now.** `services/ingest/connectors/` holds only `csv_connector.py`.
Phase 2's own outcome bullet (`07_BUILD_PLAN.md`) promised "CSV, JSON and generic delimited"; only
CSV shipped, and Phase 2 — unlike Phase 5/5a/6 — has never carried a known-gaps list recording the
shortfall. Device-extraction formats (Cellebrite UFDR, XRY) are catalogue labels only
(`packages/schemas/ingest.py`), never claimed as a connector or a recipe capability by any phase's
bullet list at all. Both halves are fixed in `07_BUILD_PLAN.md` as part of this decision: a new
Phase 2 known-gaps list records the JSON/generic-delimited shortfall as Phase 2's own disclosed
gap, and a new `Gaps with no owning phase` entry records that no phase has ever claimed a
device-extraction connector or format. The row-template `SAME_AS` mechanism itself is small and
independent of the connector — it lands as a stage inside whichever phase eventually builds
device-extraction ingest, not as a phase of its own, and B15's msisdn leg stays honestly
fixture-only until that lands, unlike the imsi→Device leg, which is real today.

**Revisit if.** A future entity type's identifiers genuinely are similar-by-construction (unlike
MSISDN/IMSI) — Splink resolution remains the right tool for that case, and this ADR's rejection
of Option (a) is specific to MSISDN↔IMSI's own value spaces, not a general claim that `Endpoint`
can never have a `resolution:` block.

---

## ADR-025 — the corpus-wide resolution and alerting trigger: design, not yet built

**Status.** Accepted, 18 September 2026. Undesigned work per `CLAUDE.md`'s "before you write
code" rule — every inference below is a proposal, flagged as such, not a claim that `docs/`
already settles it. Where `docs/` does constrain the answer, it is cited directly.

**The gap, as `07_BUILD_PLAN.md`'s Phase 6 known-gaps list already states it.**
`resolve_entity_type`, `write_same_as_edges`, `detect_conflicts` and `record_conflicts`
(`services/resolve/`) are real and tested; nothing schedules or runs them against a live corpus.
Every test in `tests/resolve/` calls them directly, and so does Phase 6's own end-to-end scenario
test (`tests/scenarios/test_phase6_extraction_and_resolution.py`). Three things depend on this
closing: B8/B9 (`08_ACCEPTANCE_SCENARIOS.md`) presume resolution has already run before an analyst
moves τ; B13/B20 need a post-ingest hook — ingesting a seizure record must raise a hotlist alert,
and subsequent matching ingest must raise a saved-pattern alert of the same shape; and Phase 6a's
screens (`07_BUILD_PLAN.md`) have nothing to show unless a `SAME_AS` edge exists by some path other
than a test calling the resolver directly.

**The blocking discovery, found while designing this rather than assumed away: `GraphPort` cannot
fetch "all nodes of a type."** `resolve_entity_type(nodes, entity_type)` is a pure function over a
caller-supplied `Sequence[Node]` (`services/resolve/resolver.py`) — it does no fetching itself.
Checked against every method `packages/ports/graph.py` declares: `find_node`/`search_nodes` need
an exact identifier value, `expand`/`paths` need a known seed node, `match` needs a bounded
pattern (itself still constrained by `01_DOMAIN_MODEL.md` §8.1's own unresolved binding-rule
question). Nothing lists a type's population. **Proposed:** a new `GraphPort` method — paginated,
access-controlled the same as every other read (`GraphPort.list_nodes(entity_type, cursor, limit,
principal)` or equivalent) — written conformance-suite-first per standing rule 1. ArcadeDB's own
per-type indexes (`packages/adapters/graph_arcadedb/schema.py`'s `_apply_indexed_declared_
properties`) already make this cheap to serve; only the abstract port surface has never needed to
expose it. Recorded as its own `Gaps with no owning phase` entry in `07_BUILD_PLAN.md` — a
structural port gap, not an orchestration one, and the actual reason "wire up a scheduler" is not
enough on its own to close this.

**No worker process exists anywhere in this codebase yet.** `services/api/supersede.py`'s own
docstring already discloses this for `GraphPort.supersede_node`'s job path: the job is submitted
(`services/api/jobs.py`'s `JobQueue`, real, Valkey-Streams-backed), but "a worker process that
drains `jobs:supersede_node`... is not written here... the consumer is written against a real
caller, not a placeholder one." **Proposed:** this trigger is that real caller, and the worker it
needs should be one generic loop dispatching by `job_type` to a registered handler, not a
resolution-specific one — it closes `supersede_node`'s own long-open gap for free rather than
leaving two near-identical workers unbuilt side by side. Flagged as a scope decision: building the
first worker process this system has ever had is a materially bigger unit of work than "wire up
resolution," and can be its own stage rather than bundled silently into this one.

**On what event — two triggers, because they unblock different things.**
1. *Post-ingest hook.* `run_recipe` (`services/ingest/engine.py`) returns a `LoadReport` carrying
   `created_node_ids`; the natural integration point is the API route that calls it (`app.py`'s
   `POST .../ingest/recipes/{recipe_id}/run`), submitting a job scoped to the entity types that
   load actually touched, once the `list_nodes` gap above is closed. Nothing else can raise a
   post-ingest alert — this is what B13/B20 need.
2. *Manual "resolve now."* A small, analyst-facing route mirroring `submit_supersede_node`'s own
   sync-vs-job split (below).

**Against which population — proposed narrow, not corpus-wide, on the first pass.** Restrict to
entity types that actually declare a `resolution:` block (today, only `Person`), scoped to nodes
the triggering load touched. A full unrestricted corpus scan on every ingest is exactly the kind
of premature generality this build has avoided elsewhere (`01_DOMAIN_MODEL.md` §8's own
`filtered_count` reasoning: no second, less-audited query beyond what is actually needed). A
precise blocking-key-scoped incremental fetch is real design work of its own, not assumed here; a
defensible, honestly-priced first cut is "refetch the whole entity type," which does not scale
past a small corpus and is disclosed as such, the same way `ArcadeDBAdapter`'s own contention
notes disclose a real, known limit rather than hiding it.

**Principal and access control.** The job runs under a deployment-level service principal, not the
ingesting analyst's own — resolution is corpus-wide and cross-investigation, and the analyst who
happened to trigger a load has no special claim over every resulting `SAME_AS` edge. **Decided
during Phase 7 Stage 1, not left as this ADR's own open proposal:** `01_DOMAIN_MODEL.md` §2.2 now
settles exactly what that identity may see — the scheme's highest classification, an empty
`receivable_handling_codes`, and the structural reason a non-empty one cannot work for a single
fixed `org_unit` — proven against the real adapter by
`tests/resolve/test_trigger.py::test_service_principal_cannot_see_a_restricted_handling_code_record`.
This ADR only restates the pointer rather than duplicating that text, per this project's own
"settle it where an access-control audit would look" discipline. A written `SAME_AS`'s own
`handling` inherits the *more restrictive* of its two endpoint nodes' classifications, proposed on
the general principle that a derived edge should never be more visible than either fact it
connects — implemented in `services/resolve/same_as_writer.py::_handling_for`, ranking via the
active `HandlingScheme`'s own dominance order rather than a hardcoded one, and proven discriminating
(not merely non-contradicted) by `tests/resolve/test_same_as_writer.py::
test_edge_inherits_the_more_restrictive_endpoints_handling`. Every write still goes through the
same `GraphPort` access-control path standing rule 2 already requires everywhere else; the service
principal is a caller identity, not a bypass.

**Overlap and partial-run recovery.** Checked, not assumed: `write_same_as_edges`/
`record_conflicts` are already upsert/supersede-based (`record_conflicts` supersedes the existing
`NOT_SAME_AS` edge rather than appending), so re-running a resolution pass from scratch is safe
and idempotent. **Proposed recovery: re-run whole, never resume from a checkpoint** — checkpointing
a Splink batch is real added complexity this doesn't need if redoing the whole pass is already
cheap and correct at the scoped population size above. Overlap (two runs for the same entity type
at once) is then wasted work, not a correctness risk; **proposed guard:** a short-TTL Valkey key
per entity type (`resolve:running:{type}`), checked before submitting, skipping a redundant
submission rather than queuing or erroring it. `JobQueue`'s existing `pending`/`running`/`done`/
`failed` states and 24-hour TTL already cover "a job that never finished shows as `running` until
TTL expires" — no new mechanism needed there.

**Scoping question 1 — does Phase 6a need the full trigger?** No, and a manual "resolve now"
route is a real first stage, not a thing that needs undoing. Phase 6a's screens call Phase 6's
*existing* endpoints; they need `SAME_AS` edges to already exist to have something to show, not a
live corpus-scale automatic trigger. `submit_supersede_node`'s own sync-vs-job split is the same
shape a manual route would use — building the sync half first is the same mechanism the full
trigger later reuses for its job half, not a different design. It unblocks Phase 6a and B8/B9
(both presume resolution has *already run* by the time an analyst looks, which a manual button
satisfies). It does **not** unblock B13/B20 — an alert firing from ingest with nobody in the loop
needs the real post-ingest hook; nothing about a manual route substitutes for that.

**Scoping question 2 — does a scheduled run change the "no proactive conflict-discovery surface"
calculus?** Yes, and this ADR proposes a minimal fix, not reopening the full decision. Phase 6's
own gaps list accepted no review queue when conflicts could only arise from an analyst's *own*
manual actions later contradicted by another manual one — low-volume and self-inflicted, findable
by whoever would know to look. An automatic corpus-wide run generates conflicts as a side effect
of ingest nobody asked to see, which is the same class of risk the cross-cutting assertion "the
status bar count of dimmed and withheld items is correct at every step" already exists to prevent
— an investigation resting on a `conflict_pending` edge with nothing in the Glass saying so is an
analyst mistaking a partial picture for a complete one. **Proposed:** surface a *count* of pending
conflicts the same way the status bar already surfaces "N hidden by handling" — a `DeltaNotice`-
shaped signal (`03_CONDUIT_MIDDLEWARE.md`'s own "a count... never the withheld content"
precedent), not a browsable list. A full conflict review queue remains a separate, larger,
explicitly out-of-scope decision.

**Where this lands.** Not a new phase. Phase 7's own outcome already names "Hotlists,
saved-pattern monitors, alert inbox" — this trigger is the backend engine that makes that bullet
real against a live deployment rather than fixture data. `07_BUILD_PLAN.md`'s Phase 7 outcome list
gets explicit new bullets (the `list_nodes` method, the worker, the post-ingest hook, the manual
route, the conflict-count notice), and its `Gaps with no owning phase` trigger entry from the
previous session is updated to point here instead of standing alone.

**Cost.** A materially larger unit of work than "wire up resolution" reads as on its own: a new
port method with its own conformance suite, this system's first worker process, a service-principal
identity that doesn't exist yet, and a Valkey-based overlap guard. None of it is required to exist
before Phase 7 starts — it is required before B8/B9/B13/B20/Phase 6a can be demonstrated against a
live deployment rather than fixture data, which `07_BUILD_PLAN.md`'s Phase 7 exit criterion already
says plainly for B12–B14/B19–B20.

**Revisit if.** The blocking-key-scoped incremental fetch turns out to be needed sooner than "the
corpus is still small" holds — at which point the population-selection proposal above, not this
ADR's other decisions, is what changes.

**Addendum, 19 September 2026 — §5's own overlap fix as proposed was not built; found, checked and
replaced during Phase 7 Stage 1, and recorded here rather than left standing only in
`services/resolve/trigger.py`'s own module docstring.**

**What §5 assumed.** The paragraph above treats `write_same_as_edges`/`record_conflicts` as
uniformly safe under overlap because both are "already upsert/supersede-based," and proposes the
Valkey guard purely as a performance throttle ("checked before submitting, skipping a redundant
submission") on top of that assumed safety.

**Checked, not assumed, while building Stage 1 — and only half of it holds.** The `SAME_AS`-write
half is genuinely safe: `GraphArcadeDBAdapter.upsert_edges` already finds-and-merges an existing
edge by `(type, source, target)` via `_find_existing_edge`, using `bothE`/`otherV` for an
undirected type, and `SAME_AS` is declared `directed: false` (`packages/ontology/loader.py`'s
`_SYSTEM_EDGE_DEFS`) — two overlapping runs writing the same pair correctly collapse into one edge
regardless of which run names which endpoint `source`/`target`. The conflict-recording half does
not: `GraphArcadeDBAdapter.supersede_edge` fetches the target edge by raw id with no check that it
hasn't already been superseded, and blindly writes a new replacement. Two overlapping runs that
both detect the same conflict against the same `NOT_SAME_AS` edge id — plausible, since each run
does its own fresh Splink pass and its own fresh read of existing edges at its own start time — can
both call `record_conflicts` against that id; the second call does not fail or no-op, it produces a
second, independent replacement, forking `superseded_by` rather than leaving one clean conflict
record. This is a correctness problem the guard alone was never going to prevent, not merely
wasted work.

**Why the obvious fix — a revision-check inside `record_conflicts` before superseding — was not
built.** Closing it cheaply needs a way to re-fetch an edge's current state immediately before the
write. `GraphPort` has no `get_edge` method. Adding one now, solely for this internal safety net,
would repeat exactly the reasoning `07_BUILD_PLAN.md`'s Phase 6 gaps list already used to decline
one for a related but different reason (edge candidates needing their own conformance-suite
coverage, standing rule 1) — real, additional port surface, not a small addition to this stage.

**What replaced it.** `resolve:running:{entity_type}` (§5's own name) is a real Valkey lock
(`valkey.asyncio.lock.Lock`), acquired atomically and **held for the run's own duration, released
on completion** — not merely checked once before submitting, as §5's own wording has it. This
closes the common case without a new port method: as long as a run finishes inside
`LOCK_TTL_SECONDS`, no second run for the same entity type can execute concurrently at all, so the
conflict-recording race above cannot occur in practice.

**The residual gap, stated at the strength it actually has.** If a run genuinely outlives
`LOCK_TTL_SECONDS`, a second run can acquire the (now-expired) lock while the first is still
writing, and the conflict-recording race is not closed for that window — the mutex is
best-effort against a real duration, not a guarantee independent of how that duration is set.

**The measurement this residual gap actually turns on, checked rather than assumed, because it is
exactly the kind of substitution a future reader would otherwise make silently.**
`tests/resolve/test_projection_perf.py`'s 50,000-node, 0.056-second result is real, but it measures
`compute_clusters`/`diff_clusters` — the τ-threshold reprojection path called from the interactive
`set_resolution_threshold` endpoint, bounded by the working set's own 50,000-node cap. It says
nothing about how long this trigger's own expensive step — `resolve_entity_type`'s Splink
`linker.predict()` over "every `Person` node," per this ADR's own "refetch the whole entity type,"
explicitly **not** bounded by the 50k working-set cap — actually takes at corpus scale. No
measurement of that step exists anywhere in this repository. `LOCK_TTL_SECONDS` (set to two hours)
is therefore a conservative, disclosed guess, not a number derived from either figure — sizing it
off the 50k/0.056s result would be sizing a guard against the wrong operation. **What would retire
the guess:** a real timing of `resolve_entity_type` against a `Person` population at the largest
scale a deployment expects to run it, the same "measured, not assumed" discipline `01_DOMAIN_MODEL.md`
§8.2 already applied to `supersede_node`'s own ~41-second figure. Recorded in `07_BUILD_PLAN.md`'s
new Phase 7 known-gaps list alongside the status-bar notice, not only here.

---

## ADR-026 — The VAST Challenge datasets are admitted shaped, not verbatim; standing rule 3 is not amended

**Status.** Accepted, 19 September 2026.

**The question, as `docs/DEMO_GUIDE.md` §7 has posed it since it was written, unresolved until
now.** The VAST Challenge datasets are fabricated scenarios with no real people, clearing the bar
the real Enron corpus fails (`CLAUDE.md` rule 9; standing rule 3's own naming of the demo). VAST
2014 MC2 in particular — GPS tracks, credit-card transactions and employee records for a fictional
company — maps closely onto this platform's POLE model and would exercise cross-filtering harder
than any fixture currently in the repository. Three things need settling, the same three this
project already settled for map providers: licence and redistribution, in-repo versus fetched at
run time, and whether standing rule 3 itself admits a fixture that is synthetic but neither
in-repo nor generator-produced.

**Licence, checked against the actual source rather than assumed, and found genuinely
unresolved.** VAST 2014 MC2 circulates from at least two places. `data.pnnl.gov`'s DataHub states
its *platform default* licence is CC0 Public Domain Dedication, redistributable, unless a specific
dataset overrides it — but the dataset's own listing there (`data.pnnl.gov/group/nodes/dataset/
13213`) does not display an explicit CC0 confirmation or an override in what a fetch of that page
returns. The original distribution channel, `vacommunity.org`, has historically gated VAST
Challenge data behind a click-through research-use agreement, and this session could not verify
whether that still applies or in what form. This is recorded as an open fact, not a guess in
either direction — asserting a licence position in an architecture document on an incomplete web
fetch would be exactly the kind of unverified claim this project's own discipline already refuses
to make silently elsewhere (ADR-021's own live-checked licence finding for `splink`/`igraph` is
the precedent for checking rather than assuming).

**The decision does not require that question to be resolved, which is the reason it is the right
one.** `tests/scenarios/fixtures/cdr.py` and the still-unbuilt Fixture Corp (`docs/DEMO_GUIDE.md`
§6) already establish this project's own answer to "a real, well-known case study would be a
better demo than anything synthesised from nothing": not the real corpus, but a same-shaped
synthetic one — structural statistics modelled on the published case, zero real identifiers,
built by a seeded generator, labelled shaped-not-real rather than blurring the distinction.
VAST 2014 MC2's value to this platform is exactly that kind of structural property — the shape of
its GPS tracks, its transaction patterns, its employee hierarchy against POLE — which is a
property of the *published academic description* of the challenge (its own problem statement, and
the papers analysing submissions against it), not of the specific files IEEE VAST or PNNL
distributes. **Decision: build a VAST-2014-MC2-*shaped* fixture via a seeded generator, the same
discipline `cdr.py` and Fixture Corp both already follow, and never admit the published dataset's
own files into the repository.** This is a decision, not a same-session build commitment — the
fixture itself is future work, exactly as Fixture Corp is named in `DEMO_GUIDE.md` §6 but not yet
built.

**Why this answers the other two questions without needing to argue them separately.**
- *In-repo or fetched at run time* — moot under this decision. ADR-015 refused fetching a map
  tile at run time in terms that apply unchanged here: "a platform whose map is blank until
  someone obtains an entitlement is a platform that cannot be demonstrated, evaluated or tested."
  A generated fixture is checked in like every other one, with no third-party availability
  dependency at all — satisfied more completely by generation than redistribution ever could
  achieve, regardless of how the licence question above eventually resolves.
- *Standing rule 3* — **not amended.** The rule already requires synthetic, in-repo, and
  seeded-generator-produced, together. A shaped fixture clears all three exactly as written. Only
  admitting VAST's own published files verbatim would need the amendment `DEMO_GUIDE.md` §7
  already flagged as a real ADR question rather than a judgement call — and weakening a
  load-bearing standing rule when a working reference implementation of the alternative (Fixture
  Corp's own design, `cdr.py`'s own precedent) already exists in this same document is the more
  expensive choice, not the cheaper one, especially resting on a licence fact this session could
  not confirm either way.

**Cost.** A VAST-shaped fixture is real, unscoped work — structural statistics need extracting
from the challenge's own published problem statement and the papers analysing it, the same
research effort Fixture Corp's own Enron-shaped design already required. Nothing about this
decision reduces that cost; it only settles which fixture gets built rather than whether the real
files could be used instead.

**Revisit if.** Both of two things become true together: a human confirms the actual attached
licence terms (not the platform default) permit redistribution, *and* a later reader concludes the
real files would demonstrate something a shaped fixture cannot — at which point verbatim admission
becomes a live alternative to evaluate on its own merits, not a reason this decision was wrong.
Confirming a permissive licence alone does not reopen this ADR; the shaped fixture was never
chosen because the licence was assumed restrictive.

---

## ADR-027 — B1 and B13's device-extraction legs stay unowned; Phase 7 proves the underlying mechanism through what already exists

**Status.** Accepted, 19 September 2026.

**The contradiction.** ADR-022 asserted, without checking it against the working tree, that
Scenario B's B1–B5 and B7 were "already proven by Phases 2–4." Opening Phase 7 and re-walking
B1–B5, B7, B12–B14, B15, B19 and B20 against the repository at `5c8c72c` finds that claim false
for B1, and finds the identical gap reaching B13: `tests/scenarios/fixtures/cdr.py` is one
carrier's file (four renderings of one number, one recipe) — there is no second CDR file in a
different carrier format, and no device-extraction fixture, connector or recipe exists anywhere.
`services/ingest/connectors/` holds only `csv_connector.py`. `tests/scenarios/fixtures/
seizure_record.py`'s own docstring already discloses this for B13's fixture directly: "no
seizure-record connector or recipe exists yet to do it end to end." This is the same defect
ADR-022 was written to correct, found again, one phase later, inside the very exit criterion
ADR-022 itself wrote — the recurrence standing rule 9 exists to make visible rather than silent.

Checked and found **not** to need reattribution, contrary to a first reading of the same gaps
list: B4 ("seed a working set from the first cohort") is `GraphPort.search_nodes`, which matches
only a type's *declared* `identifiers` — `Person.identifiers = [nino, pnc_id, prison_number,
passport_number]`, not `family_name` — so seeding by a declared identifier is pure graph-leg
search, real since Phase 3/4, and the OpenSearch document/index gap (`Gaps with no owning phase`)
does not reach it. B15 is scoped by ADR-022's own addendum to the already-real `imsi→Device`
(`PAIRED_WITH`) leg only; the `msisdn` leg was already, correctly, left fixture-only by ADR-024.
Both are recorded here so a future reader does not have to redo either check.

**Why not absorb device-extraction ingest into Phase 7 (rejected).** A real device-extraction
connector (UFDR/XRY-shaped, per ADR-024) is Phase-2-shaped ingest/connector work, not analytics
work — the same distinction ADR-022 already drew to keep B6/B9–B11 out of Phase 7 and into their
own phase (6a) rather than bolting Glass work onto an analytics phase. Phase 7 already carries
three `ComputePort` tiers, the metrics panel, the visual query builder, the pathfinder and
ADR-025's own resolution/alerting trigger; adding connector-building work on top repeats the
uncosted-growth pattern ADR-022's addendum found and corrected for Phase 8.

**Why not a disclosed CSV substitution either (rejected).** `services/ingest/engine.py`'s
row-template writer (`_write_entity`/`_write_edge`) is generic over entity and edge type, and
`on_match: reference` already resolves against the live graph across loads via `GraphPort.
find_node` — a recipe could plausibly write `PAIRED_WITH`/`SAME_AS` edges today with no new engine
code. But representing a "device extraction" as CSV rows would satisfy B1's and B13's literal
graph-state assertions without ever proving the platform can ingest a structurally different
source format, which is the actual capability Phase 2's own known-gaps list and ADR-024 both name
as missing. Narrowing what the exit criterion tests, honestly, is the correct fix; narrowing what
a fixture proves while presenting it as the real thing is not — put to the user directly rather
than decided silently, and this is the option rejected.

**Decision.**
1. B1 is scoped, for Phase 7's exit criterion only, to its two-CDR-files half: two CSV-shaped
   files in different carrier column layouts, authored as a new recipe/fixture over the existing
   CSV connector — no new connector code — proving identifier collapse across carrier formats and
   `value_raw` retention. The "two device extractions" half of B1's fixture stays unbuilt and
   unowned, exactly its status today, until a phase claims device-extraction ingest.
2. B13 is scoped, for Phase 7's exit criterion only, to the post-ingest-hook → hotlist-match →
   alert mechanism (ADR-025), demonstrated via an ordinary CDR row carrying a previously-hotlisted
   MSISDN — not via the literal seizure-record/device-extraction fixture. The mechanism under test
   is identical either way; only the source-format claim changes.
3. B4 and B15 need no reattribution, per the checks above.
4. `07_BUILD_PLAN.md`'s Phase 7 exit-criterion paragraph and its `Gaps with no owning phase`
   device-extraction entry are both edited to record this.

**Cost.** None to the platform's eventual scope. Two ordinary fixture/recipe-authoring tasks
(a second-carrier CDR file, a hotlist-triggering CDR row) stand in for what would otherwise be
connector-building work. The literal "two device extractions" and "ingest the seizure record"
claims remain honestly unmet — the same status they hold today, now written down against Phase 7
specifically rather than silently carried past it a second time the way B1 already was once.

**Revisit if.** A future phase claims device-extraction ingest (ADR-024's own "whichever phase
eventually builds" it) — at that point B1 and B13 should be re-proven against their literal
fixtures, the same way A12 was re-proven once its own dependency landed.

---

## ADR-028 — `ComputePort`'s three tiers: Tier 1 runs as a plain Node script, not a browser; Tier 3 is deferred to Phase 8a's `cluster` profile

**Status.** Accepted, 19 September 2026.

**The question, named by `NEXT_STEPS_PHASE7.md`'s own Session 5 prompt before Phase 7's compute
work began, and settled here rather than re-deferred a second time.** Phase 7's exit criterion
requires "all three compute tiers return identical values within tolerance on the 5,000-node
fixture." `00_ARCHITECTURE.md` §2.3 names the three: graphology in a browser Web Worker (≤20k
nodes), `rustworkx` in a Conduit worker process (≤2M nodes), and GraphFrames on Spark or HugeGraph
Vermeer (>2M nodes, Vault, batch). Every conformance suite in this repository is a Python `pytest`
parametrisation over an adapter registry — there was no precedent for exercising a TypeScript
browser Worker, and no assessment on file of whether the third tier is feasible on the dev host at
all.

**Tier 1 — the suite exercises it as a plain Node script, never a browser or a `Worker`.** The
correctness claim `tests/conformance/compute_port/test_suite.py` exists to prove is algorithmic —
graphology's numbers agree with `rustworkx`'s on the same input — not a threading claim.
Browser-Worker message-passing is real, but it is a *frontend integration* concern
`apps/workspace`'s own Playwright suite already has an established pattern for (`glass-perf`/
`glass-keyboard`/`glass-map-verify`, `Makefile`'s `npm run test:X --workspace apps/workspace`), not
this port's conformance suite — which has never tested transport or threading for any other
adapter either (it proves Gremlin's answers, never ArcadeDB's own WebSocket framing). `graphology`
is already an `apps/workspace/package.json` dependency; `graphology-metrics` (the package that
actually implements degree/betweenness/eigenvector/pagerank/clustering-coefficient) is **not** —
checked directly against `package.json`, not assumed from `graphology` being present, and corrected
here rather than left standing (see this ADR's own addendum). `node`/`npm` are already present on
this host and every CI runner that builds the frontend. **Decision:** a
`ComputeAdapterFactory` entry (`tests/conformance/registry.py`, mirroring `AnalyticsAdapterFactory`'s
own shape) whose `context()` shells out to a small Node script reading a JSON-serialised `Subgraph`
and request on stdin and writing a JSON result on stdout — headless, no browser, no `Worker`. A
later, separate Playwright case (frontend-owned) is what would prove the Worker actually returns to
the main thread without blocking it; that is not this suite's claim and this ADR does not schedule
it. **Not built in Phase 7 Stage 2** — schemas and the suite only, standing rule 1 — named here so
whichever stage registers Tier 1 is not blocked re-deriving the mechanism.

**Tier 3 — not feasible on this development host; deferred to Phase 8a's `cluster` profile (named
Phase 8 at the time this ADR was first accepted; split out by ADR-022's third addendum, 20
September 2026), not tested and found wanting.** `docker info` on this host reports a fixed 8,214,585,344-byte
(~7.65GiB) Docker Desktop VM. `deploy/compose/dev.yaml`'s own `arcadedb` service already carries
four dated incident notes on exactly this budget: two concurrent conformance suites OOM'd at the
JVM's default heap; a single heavy sequential HMP graph build OOM'd at 4G; `ollama`'s own resting
~3.5GB footprint OOM-killed ArcadeDB repeatedly during Phase 6 Stage 6; orphaned `conformance_*`
databases from a hard-killed test run filled the VM's own disk. Phase 7 Stage 1 added a fifth,
different-in-kind incident this same session: two live Conduit instances together exhausted
Postgres's connection limit. A local Spark session's own driver and executor JVMs typically need
several gigabytes of their own headroom on top of whatever else is running — asking that to coexist
with ArcadeDB (already tuned to 6G), Ollama, Postgres, MinIO, Valkey and LiteLLM on a budget that
has already produced five distinct incidents from lighter combinations is answered by the evidence
already on file, not a proposal worth spending a sixth incident to confirm.

**Decision: Tier 3 registers in Phase 8a's `cluster` profile, not in Phase 7, and not on this
host.** Phase 8a already owns exactly this class of work — `adapters/graph_janusgraph`,
`adapters/analytics_clickhouse`, "runs on more than a laptop" (`07_BUILD_PLAN.md`) — so this is not
inventing a new home for orphaned scope, the same shape ADR-022 already used once for Scenario B's
own six Glass screens. `tests/conformance/compute_port/test_suite.py`'s cross-tier agreement case
(`test_all_registered_tiers_agree_within_tolerance`) already collects zero cases with fewer than two
tiers registered and needs no change when Tier 3 eventually joins — the suite this ADR is attached
to was written to accommodate exactly this deferral without a rewrite.

**What this means for Phase 7's own exit criterion, stated plainly.** "All three compute tiers
return identical values within tolerance" cannot be demonstrated inside Phase 7 on this host.
Recorded in Phase 7's own known-gaps list (`07_BUILD_PLAN.md`), not silently narrowed — the third
tier's own conformance case joins the suite the moment its adapter registers, on whichever host
actually runs it.

**Cost.** None to the platform's eventual scope — every tier is still built, by the profile that
can actually host it. The cost is to Phase 7's own literal exit-criterion demonstration, which
proves two tiers agree on this host and defers the third rather than three.

**Revisit if.** The dev host's Docker Desktop VM memory allocation is raised well beyond ~7.6GB
(a host setting, `deploy/compose/dev.yaml`'s own notes already name this lever), *or* the actual
deployment target is the `cluster` profile regardless, at which point Tier 3 registers there
directly rather than being retested on this host first.

**Addendum, 20 September 2026 — the tolerance number, measured rather than assumed, opening Phase
7 Stage 3; and a dependency correction found while measuring it.**

**Correction first.** This ADR's own Tier 1 section said `graphology-metrics` was already an
`apps/workspace/package.json` dependency alongside `graphology`. Checked directly rather than
re-asserted: it is not. Only `graphology`/`graphology-types` are listed;
`graphology-metrics` — the package that actually implements degree, betweenness, eigenvector,
PageRank and clustering coefficient — is a real, undisclosed addition whichever stage builds the
Tier 1 Node harness must make. Small (MIT-licensed, same author/ecosystem as `graphology` itself,
no transitive licence conflict found), but a real line item, not zero-cost as this ADR originally
implied.

**The tolerance, measured, not chosen because it looked reasonable.** `rustworkx` (Rust core) and
`graphology-metrics` (pure JavaScript) were run against the identical seeded 5,000-node/14,991-edge
fixture (Barabási–Albert-shaped, seed 42) with the same explicit convergence settings
(`tol=1e-10`, `max_iter=1000`) on both sides — a real cross-implementation run, not a projection.
Two materially different regimes, not one number:

- **Exact, closed-form metrics** (degree, weighted degree, clustering coefficient, betweenness,
  the Clique Metric — none involve iterative approximation, only summation order): measured max
  relative divergence `1.17 × 10⁻¹⁴` (betweenness), consistent with plain IEEE 754 double-precision
  summation-order noise. **`rel=1e-9` is generously safe** — five orders of magnitude of headroom,
  the same "tight enough that a real regression would trip it, loose enough ordinary variance
  never does" philosophy `test_projection_perf.py`'s own `_CEILING_SECONDS` already uses.
- **Iterative metrics** (eigenvector, PageRank — convergence-tolerance-dependent, and the two
  implementations' own iteration/convergence paths differ): measured max relative divergence
  `2.59 × 10⁻⁶`. **`rel=1e-4` is safe with real margin** (~40×), but only if both adapters *pin* an
  explicit convergence tolerance and iteration cap rather than trusting each library's own
  default — an unpinned default is a silent, version-dependent moving target this measurement does
  not cover and a future dependency bump could quietly widen.

**Communities (Leiden) are not a numeric-tolerance question at all, found while designing the
cross-tier case rather than assumed to fit the same pattern.** Leiden is a stochastic, heuristic
optimisation: cluster *labels* are arbitrary and interchangeable between two runs, and two correct
implementations are not guaranteed to converge on the *same partition*, only on partitions of
comparable quality — "identical values within tolerance" has no meaning for a
`dict[NodeId, CommunityId]` the way it does for a `dict[NodeId, float]`. **Proposed, for whichever
stage builds the cross-tier `communities` case:** compare partitions by modularity score (a single
float per partition, the same exact-metric tolerance class as the Clique Metric) rather than
per-node cluster-id equality — this is a real, undesigned test-shape decision for that stage, not
answered by this ADR's own tolerance figures, which is why it is named here rather than left to be
discovered when that specific case is written.

**Cost.** One dependency addition (`graphology-metrics`) not previously disclosed; two tolerance
constants to carry in the eventual cross-tier test (`rel=1e-9` exact, `rel=1e-4` iterative), pinned
against a real measurement rather than each reader's own guess; the `communities` comparison shape
is real, separate design work for whichever stage writes that specific case.

**Revisit if.** Either library's own default algorithm changes in a way that moves the measured
figures — re-run this comparison rather than assume the old numbers still hold, the same discipline
this addendum was written to establish in the first place.

---

## ADR-029 — Neither compute tier can run Leiden; both run Louvain with a connected-components fix

**Status.** Accepted, 20 September 2026.

**The premise, checked precisely rather than assumed either way.** `01_DOMAIN_MODEL.md` §6.3 says
"Prefer Leiden; Louvain can produce disconnected communities," and `packages/schemas/compute.py`'s
own `CommunityRequest` (Phase 7 Stage 2) already committed to "Leiden only... no algorithm choice
is exposed." Opening Stage 3, neither compute tier actually has one. `rustworkx` has no
community-detection function at all — checked directly against its own module contents, not
assumed absent. `leidenalg` (the standard Python route) pulls in `python-igraph`, confirmed GPL
via `importlib.metadata` — the same package `06_DECISIONS.md` ADR-021 already rejected for Splink.
But that is not the only Python Leiden, checked rather than stopped at the first result:
`graspologic.partition.leiden`, backed by `graspologic-native` (a Rust core), is genuinely MIT —
confirmed via the same metadata check on both packages, not assumed from the parent package's own
licence. It comes at real transitive cost: installing it pulled 39 packages (`matplotlib`, `scipy`,
`scikit-learn`, `numba`, `gensim`, `umap-learn`, among others) to reach one function. Three
JavaScript Leiden packages exist on npm — `@aflsolutions/graphology-communities-leiden`,
`leiden-ts`, `ngraph.leiden` — but none is graphology's own official ecosystem package the way
`graphology-communities-louvain` is: a single-maintainer extraction, a `v0.1.0` package with no
version history, and a different graph library entirely, respectively.

**The architectural reason, which forces the answer independently of any licence question, and is
therefore the reason this ADR leads with it rather than with ADR-021's own GPL line.** Tier 1 is
`graphology` in a browser Web Worker. There is no mature, trusted Leiden implementation in that
ecosystem — checked above, not assumed. Phase 7's own exit criterion requires every registered
tier to agree, and Leiden versus Louvain is not a numerical-tolerance question the way PageRank's
own convergence path is (this ADR's own addendum above) — it is a genuinely different partition of
the same graph. A licence-clean Leiden on Tier 2 alone (`graspologic`) would not help this
particular problem: it would make the two tiers agree with each other *less*, not more, and would
add a 39-package dependency tree to buy that. ADR-021's GPL finding is the second, independent
reason the common route is closed regardless — cited alongside the architectural one, not in place
of it, so a future reader does not conclude that vendoring a licence-clean Leiden on Tier 2 in
isolation would fix anything it doesn't.

**Decision.** Both tiers run Louvain. Tier 2 uses NetworkX's native
`networkx.algorithms.community.louvain_communities` — BSD-3, confirmed against the installed
package's own `LICENSE.txt`, not assumed from the project's general reputation — rather than a
separate `python-louvain` package: the bare install has **zero** required dependencies (confirmed
via `Requires-Dist`; numpy/scipy/matplotlib are opt-in `extras` this build does not need), and
`04_VAULT_BACKEND.md` already names NetworkX as "a reference implementation for the conformance
fixtures" — this reuses a dependency the spec already anticipated rather than introducing a new
one. Tier 1 uses `graphology-communities-louvain` (MIT, the actual official graphology-ecosystem
package, not one of the three Leiden extractions checked above).

**Mitigating the specific, named hazard, rather than only disclosing it.** §6.3's own objection to
Louvain is precise, not vague: it can merge two components sharing no edge into one labelled
community, because merging two already-disconnected pieces is never worse, and can tie, under
modularity optimisation — the exact failure Traag, Waltman & van Eck (2019) built Leiden to close.
**Fix: a connected-components split pass over Louvain's own output, run identically — the same
O(n+m) algorithm, written natively in each tier's own language, not shared code — on both tiers.**
For each community label Louvain returns, find the connected components of its own induced
subgraph and give each one its own label. **Stated at the strength this actually buys, not
further:** the specific disconnection hazard is closed — every returned community is now
guaranteed internally connected, the one property Leiden guaranteed and Louvain alone does not. It
does **not** restore Leiden's own partition quality (Leiden's refinement step improves modularity
beyond plain Louvain in ways this split pass does not attempt), and the resulting partition is a
Louvain partition, not a Leiden one — a real, disclosed trade, not a free fix dressed up as one.

**The test this needs, per standing rule 12 — proving the fix directly, not hoping a fixture
happens to reproduce Louvain's own nondeterministic tie-breaking.** Louvain's disconnection
failure mode is real — the literature that motivated Leiden establishes it — but is not reliably
reproducible on demand from an arbitrary constructed graph, since it depends on the specific
implementation's own tie-breaking under an exact modularity tie. The rigorous test is therefore of
the *mitigation function itself*, not of Louvain:
`test_split_disconnected_communities_separates_unconnected_members` — hand-construct a partition
that is deliberately wrong (two disjoint edges, `A–B` and `C–D`, sharing no path between them, both
labelled as one community — bypassing Louvain's own output entirely for this specific proof) and
assert the post-processed result gives `{A, B}` and `{C, D}` two different labels. Written and run
in both languages against the identical adversarial input, since the fix itself is duplicated, not
shared.

**Every site naming Leiden is corrected in the same change as this ADR, not left to drift — the
exact failure this build has already named more than once (`playback`/`multi-track`, the
keyboard-registry gap, the graphify-hook instruction) when a correction lived in only one place:**
`01_DOMAIN_MODEL.md` §6.3's own table row and §10's `CommunityRequest` sketch comment;
`07_BUILD_PLAN.md`'s Phase 7 outcome bullet and the Stage-2 `temporal_motifs` gaps entry that
quotes it verbatim; `02_GLASS_FRONTEND.md` §2's "a Leiden/analytics grouping" and §3.2's "Community
assignment (Leiden)"; `04_VAULT_BACKEND.md`'s own conformance-suite description; and
`packages/schemas/compute.py`'s `CommunityRequest` docstring, with its generated TypeScript
regenerated in the same change.

**Cost.** Two new dependencies (`networkx`, bare install, zero transitive weight;
`graphology-communities-louvain`, MIT, four dependencies of its own), one small mitigation function
duplicated in two languages with its own adversarial test in each, eight documentation sites
corrected in one change.

**Revisit if.** A Leiden implementation ships in the graphology ecosystem with the maturity/trust
profile this build already requires of its other dependencies — an official package, a real
version history, real adoption — at which point Tier 1 could adopt it and the cross-tier
agreement question reopens on its own terms, not before.

**A second, independent route back to Leiden, recorded now because it is the realistic one and
costs more to re-derive later than to write down here — not a scope change, nothing below is
built by this ADR.** Leiden never joins the browser tier at all. Instead, "recompute communities
with Leiden" becomes an explicit, analyst-initiated action that always runs server-side, at any
working-set size, while Louvain stays the default computed under the ordinary tier rules
(browser-first, falling back per `00_ARCHITECTURE.md` §2.3's own boundaries). This beats a
size-based split on two separate grounds, not one: the browser tier exists to buy interactivity, not
because computation is otherwise impossible — a small working set can afford a server round-trip
for an algorithm the browser cannot run at all, the same way `submit_supersede_node`'s own sync/job
split already treats "runs client-side" as an optimisation, not an entitlement. And an analyst who
explicitly asks for Leiden is asking for a different answer, not the same one delivered faster — a
silent reshuffle of community membership the moment a working set crosses the 20,000-node
sync/job boundary would be the wrong failure mode entirely, mistaking a deliberate choice for
tier-selection noise.

Three things this design would need, none built here:

1. **A permissively-licensed server-side Leiden — still unverified, not merely unbuilt.** This
   ADR's own premise check found exactly one MIT candidate, `graspologic.partition.leiden`, at a
   real cost (39 transitive packages for one function) that was disqualifying for the *default*,
   always-on path this ADR actually decided. Whether that same cost is acceptable for an
   *explicit, occasional, analyst-initiated* action is a real question this ADR has not answered
   either way — the check so far only established that no *free* option exists, not that
   `graspologic` is the one to take.
2. **The algorithm recorded alongside each community, the same way a `SAME_AS` edge carries its
   own `model_version`.** Without it, two analysts working the same investigation could see
   different community groupings with no way to tell whether that is a Louvain/Leiden split or a
   real change in the underlying data — exactly the kind of silent inconsistency `provenance`
   already exists to foreclose everywhere else in this domain model.
3. **An amendment to `01_DOMAIN_MODEL.md` §10's `CommunityRequest` sketch ("no algorithm choice is
   exposed").** That constraint was written to prevent *accidental* inconsistency between tiers —
   two tiers silently disagreeing because a caller picked differently on each. A deliberate,
   labelled analyst choice, recorded per-community the way item 2 above requires, is a different
   thing entirely and is not what that sentence was written to forbid; the sentence itself would
   need to say so, not merely be read around.

---

## ADR-030 — `PatternQuery` is widened for a pinned second root; Gremlin's `match()` step does not work on this adapter

**Status.** Accepted, 20 September 2026.

**The premise, flagged since before Phase 7 was scoped, settled here.** `01_DOMAIN_MODEL.md`
§8.1's own `MatchBuilder` compiled a `PatternQuery` by walking `pattern.edges` in list order,
starting from `pattern.nodes[0]`, requiring every edge's `from_var` to already be bound. This
expresses exactly one shape: a single directed chain rooted at one node, walked forward via
`.outE()` only. A phase-3-era handover already flagged this as "more restrictive than Phase 7
will want," deferred to Phase 7 Stage 4 — the visual query builder — because that is where an
analyst first draws an arbitrary pattern rather than a caller constructing one in code.

**Not a hypothetical — `08_ACCEPTANCE_SCENARIOS.md` B19 is exactly the shape the old compiler
rejected.** "Expand to common contacts across the two principal endpoints" is a diamond: two
independent, already-known starting nodes converging on a shared third. The old compiler's second
root is never bound by anything and raises. B19 is named in `07_BUILD_PLAN.md`'s own Phase 7 exit
paragraph — restricting the builder and explaining the limitation at the point of drawing, the
cheaper and safer of the two options originally weighed, cannot be the whole answer, because it
cannot pass this phase's own exit criterion without a bespoke mechanism built outside
`PatternQuery` entirely, which the acceptance table's own "Pattern query" mechanism column argues
against.

**The first design tried, and why it does not work on this adapter — checked directly against a
live ArcadeDB instance, not assumed from the TinkerPop specification.** Gremlin's own `match()`
step is the standard, general-purpose way to join independently-expressed traversal fragments on
a shared variable — the textbook answer to a diamond pattern, and the one this ADR originally
intended to ship. It does not work here: every attempt at a `match()` fragment introducing a
genuinely independent second enumeration (a fragment starting its own fresh `V()`, needed for any
second root that is not already reachable from the first) failed with a bare
`CommandExecutionException`, including the simplest possible case with no filters, no access
checks, and an empty database. `g.V().match(__.as('a').out().as('b'))` — the canonical single-root
form, where `match()`'s own fragments only ever *extend* a binding the outer traversal already
provides — works correctly. `g.inject(0).match(__.V().as('a'), ...)` and every variant seeding a
fresh enumeration inside a fragment does not. ArcadeDB's own Gremlin engine, in short, supports
`match()` only for elaborating a single existing binding, not for the general multi-root join
TinkerPop's own documentation describes.

**The mechanism actually shipped: a pinned-root reachability check, not a general join.** Every
root beyond the primary one must carry a new `PatternNode.node_id` field pinning it to an
already-known node — which is B19's own real shape (the analyst has already selected both
"principal endpoints"; the query discovers their common contacts, not the endpoints themselves).
The primary root's own chain compiles forward exactly as the original single-chain algorithm
already does. Each pinned secondary root's own chain to the convergence point is reversed into a
`.where()` step — walked backward with `.in(edge_type)` in reverse order, ending in
`.has("id", <the known id>)` — proving "this known node also reaches the same convergence point,"
without ever needing to enumerate or bind a second, independent root at all. Confirmed directly
against a live ArcadeDB instance with real fixture data before being accepted as the design.

**What this narrows, stated plainly rather than left to be discovered later.** An open (unpinned)
second root — a genuinely general diamond, "any two Persons of this shape converging on a shared
node," neither already known — remains unsupported. There is no general join to fall back to on
this adapter; a pattern needing one is rejected by the builder with a specific error naming the
unbound root, not silently mis-compiled or silently wrong. This is narrower than the `match()`-based
design originally planned, and is disclosed as such rather than presented as the general fix a
reader might assume "widened" means.

**Does this weaken ADR-003's bounded-query guarantee? Answered directly.** The guarantee ADR-003
actually names is that the compiler — not the caller — controls every traversal step, which is
what makes access-filtering reliable; free-form Gremlin is the thing rejected, not any particular
traversal shape. Under this design, every step in both the primary chain and every reversed
secondary check is still built exclusively by `MatchBuilder`, one hop at a time, with the same
`access.gremlin_has_step()` fragment injected at every `.outE()`/`.inV()`/`.in()` the single-chain
compiler already used. Nothing about a reachability check changes who constructs a step. What it
does change is what must be *proven*: a hidden common node must not change an intersection
query's own result, count, or presence for a principal who cannot see it — a new conformance case
(`test_match_intersection_never_leaks_a_hidden_common_endpoint`) proves exactly this against the
real adapter, not a fake, the same standing discipline every access-control claim in this
repository already follows.

**A no-regression guarantee, proven as a compiled-string comparison, not only a behavioural one.**
`test_match_single_chain_pattern_compiles_to_the_same_gremlin_as_before` asserts the exact Gremlin
string an existing single-chain pattern compiles to is byte-identical to what it was before this
widening — checked because "the query still returns the right nodes" could pass even if the
compiler took a slower or differently-shaped path to the same answer, which would not itself be a
regression but would be an undisclosed one.

**Cost.** One new `PatternNode` field, regenerated TypeScript. `MatchBuilder` gains a second
compilation path (`_render_matched`), used only when the pattern cannot be linearised from a
single root — the existing path is untouched code, not merely untouched output. Three new
conformance cases. The real, ongoing cost is scope: this ADR does not deliver a general
multi-root query capability, only the specific pinned-root shape B19 needs; a future pattern
requiring a true open diamond join is a new question, not something this ADR's own mechanism
answers by extension.

**Revisit if.** A future ArcadeDB release fixes `match()`'s own independent-enumeration case
(worth re-testing before assuming it still fails, not re-asserting this ADR's own finding
indefinitely), or the adapter layer gains a second graph engine whose `match()` support is more
complete — at which point the general join becomes available and the pinned-root mechanism can
stay as a cheaper special case rather than the only path. Revisit sooner if a real pattern needing
a true open (unpinned) multi-root join is named by name against an acceptance scenario, the same
way B19 forced this one.

---

## ADR-031 — The repository splits into `spec/` and `process/`; `docs/` is dissolved; the move waits for Phase 8's close

**Status.** Accepted, 20 September 2026. Scheduled for the end of Phase 8 — not built by this
record, which documents and schedules the move rather than performing it.

**The problem.** `docs/` today mixes three kinds of thing with no marker distinguishing them: the
binding specification (`00_ARCHITECTURE.md` through `09_INGEST_STUDIO.md`, `06_DECISIONS.md`,
`design/tokens.css`), the process record (`SESSION_HANDOVER.md`, `NEXT_STEPS_PHASE7.md`,
`DESIGN_PROVENANCE.md`, `archive/`), and operator-facing product documentation (`README.md`,
`DEMO_GUIDE.md`). A maintainer who inherits this repository after the build has no way to tell
which is which without reading each file — the process record in particular is noise to anyone
who was not part of the build, and actively misleading if mistaken for a live commitment (a
handover note describing what a session *intended* to do next reads, to an outsider, exactly like
a spec).

**The target layout.**

- **`spec/`** — the binding pack: `00_ARCHITECTURE.md` through `09_INGEST_STUDIO.md`, `design/`
  (`tokens.css`, brand foundations), and `06_DECISIONS.md`. `06_DECISIONS.md` reads like a process
  record — a log of decisions made over time — but is not one: `CLAUDE.md` makes every accepted
  ADR binding on the same footing as the numbered spec files, so it belongs in `spec/`, not
  `process/`, despite its own narrative shape. Filenames are unchanged, including their numeric
  prefixes — only the leading path segment changes (`docs/01_DOMAIN_MODEL.md` →
  `spec/01_DOMAIN_MODEL.md`), which is what makes the citation-rewrite below a mechanical prefix
  swap for the numbered files rather than a rename.
- **`process/`** — the record: `SESSION_HANDOVER.md`, `NEXT_STEPS_PHASE7.md`,
  `DESIGN_PROVENANCE.md`, `archive/` (unchanged internally).
- **Root-level product documentation, not a third top-level directory.** `README.md` and
  `DEMO_GUIDE.md` are neither binding spec nor process record — they document the finished
  product for an operator or a visitor, the same class of thing a `CONTRIBUTING.md` or a
  `CHANGELOG.md` would be. This repository currently has no root-level `README.md` at all (`docs/
  README.md` is the closest thing, an internal docs-index page) — a real gap for a repository
  anyone opens on GitHub, where a root `README.md` renders automatically and is the conventional
  landing page. Both move to the repository root, `README.md` rewritten to serve as that landing
  page (pointing into `spec/` for the specification, `process/` for the history) rather than
  staying an internal docs index. This is the smallest structure that actually separates the three
  kinds of thing named above — inventing a fourth top-level directory for two files would not
  clarify anything a root-level file doesn't already.
- `docs/` no longer exists once the move completes; `spec/` and `process/` are its two
  replacements, not new siblings kept alongside an empty shell.

**One repository with two top-level directories, not two sibling repositories — considered and
rejected on evidence, not on convention.** `392` source files carry `1,150` citations of the
specification by filename, in docstrings and comments shaped like `` `01_DOMAIN_MODEL.md` §8.1:
`match()` takes a bounded `PatternQuery`` ``. Those citations are not decoration: they are how
this build has actually found some of its own real defects — ADR-023's `Endpoint`/`Device`
identifier contradiction and Stage 1's `_handling_for` bug were both caught by following a
docstring's own citation back to the spec and finding the two disagreed. A citation only does
that job when the cited file is a `git checkout` away, not a submodule pin or a separate clone
that can silently drift to a different commit. Splitting into two repositories would also end
spec-and-code co-versioning — code at one commit, spec at another, with nothing to detect the
drift — in a build whose own central discipline, stated throughout `CLAUDE.md`, is that the
repository itself is the source of truth. Two top-level directories inside one repository keep
every one of those 1,150 citations exactly as load-bearing as it is today, at the cost of nothing
this ADR can find.

**Why the move waits for the end of Phase 8, not Phase 8a, and why that distinction matters.**
The specification is still genuinely moving — five ADRs accepted in the week this record was
written alone. Restructuring a moving target multiplies merge conflicts between in-flight spec
edits and the move itself for no offsetting benefit; better to move a specification that has
stopped changing shape. Phase 8a, by its own ADR-022 addendum, is *specifically* the part of this
build that needs real multi-node infrastructure that may not be available on any given host —
tying a clean-handover step to a phase defined by that uncertainty risks the handover step never
happening at all. The restructure has no actual dependency on cluster work: nothing about `spec/`
versus `process/` versus root-level product docs is affected by whether Tier 3 or the two cluster
adapters are done. Phase 8a's own later spec edits, whenever they land, simply land inside the
new structure rather than the old one — the ordering (Phase 8 closes, then the move, independent
of whether Phase 8a has also closed by then) is the one point this record fixes now rather than
leaving to be re-argued at the time.

**The engineering the move actually requires — an invariant with a test, not a bullet point.**
1,150 citation rewrites cannot be verified by eye; a single missed or mistyped path is a silent
dangling reference this build has a standing rule about (rule 12: name the test that would fail).
The move's own Phase 8 bullet must ship with a checker, running in CI, that confirms every
spec/process/product path cited anywhere in the repository resolves to a file that actually
exists — not a one-time manual grep, a permanent gate the same way `scripts/schemas_check.py`
gates generated-type drift and `scripts/licence_check.py` gates dependency licences.

**A new script, not an extension of either precedent.** `schemas_check.py` (Pydantic-to-TypeScript
parity) and `licence_check.py` (dependency licence scanning) share this checker's *shape* — a
small, standalone, `make`-invoked gate — but neither shares its *logic*: there is nothing in
either script's own domain (type generation, licence text matching) that a citation-path
existence check would extend rather than bolt on. A new script,
`scripts/doc_citations_check.py` in the same family, wired into `Makefile`'s own `ci` target
(`ci: lint typecheck licence-check trivy trivy-image-ingest trivy-image-api schemas-check
conformance-guard`) alongside its two precedents, is the consistent choice — matching the
established pattern exactly rather than forcing a fit.

**Run before the move, as a baseline, not only after.** The checker's first real run must happen
*before* any file moves, against the current `docs/`-rooted citations, for the reason named
directly: a citation that is already dangling today — a stale filename, a typo, a reference to
something already renamed — would otherwise be indistinguishable from one this move itself broke,
and the move would take the blame for a pre-existing defect. The sequence: run the checker against
the pre-move tree and fix whatever it finds first, so the baseline is clean; move the files; run
the mechanical prefix rewrite across all 1,150 citations; run the checker again as the real
post-move gate; wire it into `ci` permanently from that point on, not only for this one move.

**Cost.** One new script and its own test fixture (a small tree of files with a deliberately
dangling citation, proving the checker actually fails on one — the same "prove it can fail"
discipline this repository already applies to every other invariant). A large, mechanical
citation-rewrite pass across 392 files, verified by the checker rather than by review. Every
existing citation of `docs/06_DECISIONS.md`'s own ADR numbers, `01_DOMAIN_MODEL.md`'s section
numbers, and so on stays correct without further edits, since only the leading path segment
changes for the numbered files.

**Revisit if.** The specification is still changing shape materially at Phase 8's own close —
delay the move a further, explicitly-named increment rather than force it against a target still
moving, the same reasoning that sets this timing in the first place.

---

## ADR-032 — The visual query builder is a keyboard-native list/palette editor, not a second drawing canvas; `02_GLASS_FRONTEND.md` §3.3 is corrected to match

**Status.** Accepted, 20 September 2026.

**The premise.** `02_GLASS_FRONTEND.md` §3.3 specifies the visual query builder as "a
node-and-edge pattern the analyst draws" — language that reads, and was built against elsewhere in
this document, as a second Sigma/graphology drawing surface beside `GlassCanvas`. Phase 7 Stage 4
built something else: `apps/workspace/src/patterns/QueryBuilderPanel.tsx`, a `Panel` of native
controls — an entity-type palette that places a pattern node, `GlobalSearch` reused to pin one, a
list of the pattern's own nodes and edges, and Preview/Run. This was disclosed as a scope choice in
the implementation session's own summary rather than recorded in `docs/`, which this repository's
own standing discipline (ADR-019, 022, 023, 027, 028, 029, 030 each correcting spec text the moment
implementation diverged from it) does not permit a session summary to substitute for. This record
is that correction, made after the fact rather than before — the deviation is real and already
built, and what follows is the case for keeping it, not a proposal.

**Why a second canvas was the default assumption, and why it does not survive contact with what
this repository already knows about `GlassCanvas`.** A drawing surface is the obvious reading of
"draws," and `02_GLASS_FRONTEND.md` §1 already chose Sigma for exactly this kind of interactive,
WebGL-rendered graph structure. But a second canvas is not a second instance of a solved problem —
it is a second instance of every interaction problem the first one has, including ones this build
has already had to find and fix once. `06_DECISIONS.md`'s own Phase 7 Stage 4 write-up and
`07_BUILD_PLAN.md`'s "Gaps with no owning phase" both record the Tab-trap: `GlassCanvas.tsx`'s own
`onKeyDown` intercepted every Tab keydown once its container held focus, discovered only when
`metrics-panel.spec.ts` needed a keyboard user to leave the canvas and reach a sibling panel, and
fixed by moving ring-establishment to `onFocus` and ring-cycling off Tab entirely. A second,
independently-built canvas inherits the same design questions from scratch — what does Tab do
inside it, what does arrow-key focus mean over a pattern instead of a working set, how does a
screen-reader user perceive a node with no accessible-tree equivalent — and each is a place the
same class of defect can recur, proven by the fact that it already has once. `02_GLASS_FRONTEND.md`
§6's own accessible-alternative-view requirement (Matrix, standing beside the graph canvas) is the
existing acknowledgement that a canvas is not, by itself, a fully accessible surface — it is made
one by a second, non-canvas rendering next to it. A list/palette editor does not need that second
rendering built afterward, because it never leaves the accessible-by-default DOM in the first
place: every pattern node is a real `<div role="group" tabIndex={0}>` inside ordinary tab order,
every action is a native `<button>`/`<select>`, and `Combobox`'s own keyboard-selection gap
(surfaced by this same stage — see the "Gaps with no owning phase" entry) shows that even a
*non-canvas* control's keyboard path needs checking, not assuming; a canvas starts from further
back on exactly that axis.

**What a canvas would have bought, named honestly rather than assumed away.** A node-link diagram
is a genuinely better tool than a list for reasoning about topology once a shape has more than a
handful of elements — an analyst can see a diamond converge at a glance in a drawing, where a list
of `PatternEdge` rows requires reading and mentally reconstructing the same shape. This is a real
cost, not a hypothetical one. It is bounded, though, by what `06_DECISIONS.md` ADR-030 already
narrowed `MatchBuilder` to compile: one primary chain plus pinned secondary roots converging on a
variable the primary chain reaches — not an open, arbitrary graph. Every pattern this compiler can
actually run is, by construction, small and shallow enough that a list renders it in a handful of
rows (`nodes`, then `edges`, each one line) — B19's own shape is two pinned roots and one discovered
node, three list rows and two edge rows, legible without a diagram. The list editor's real weakness
— scaling to a shape with many convergence points or long chains — is a cost this build is not
currently paying, because ADR-030's own compiler cannot express that shape either. **This is a
coupled trade, not an independent one:** if ADR-030's own "revisit if" is ever exercised (a second
graph engine, or an ArcadeDB release that supports a genuine multi-root `match()` join), the
pattern space this builder needs to represent grows past what a list renders well, and this ADR's
own conclusion should be re-examined at the same time, not treated as settled independently of it.

**Was "draws" load-bearing in the source journey, or incidental phrasing?** Checked against
`08_ACCEPTANCE_SCENARIOS.md` directly rather than assumed either way. B19 ("expand to common
contacts across the two principal endpoints") is Scenario B's own pattern-query step, "derived from
the City of London Police demonstration journey" per that document's own header — but B19's
assertion is "the intersection set is returned, with the estimated count shown before running," an
assertion entirely about *output*, with no reference to drawing, a canvas, or any other input
mechanism. B20 ("save the pattern as a monitor") is the one CoLP-derived step that names an
interaction verb at all, and it is "save," not "draw." Nothing in Scenario B's own eighteen-row
journey, nor in `01_DOMAIN_MODEL.md`'s or `02_GLASS_FRONTEND.md`'s own CoLP citations (both about
hotlist/watchlist alerting, the *second* of §3.3's three pattern-analysis mechanisms, not the
visual query builder), needs the query to be *drawn* rather than *composed*. "Draws" reads as the
same kind of inherited, not-yet-checked-against-this-build's-own-constraints phrasing
`02_GLASS_FRONTEND.md` §1 already found and overrode once before, for the same reason: that
section's own opening paragraph records that "both the research brief and the Gemini specification
nominate Cytoscape.js," a recommendation this document itself rejected once it was checked against
the platform's actual scale requirement. "Draws" was never checked against this build's own
compiler narrowing (ADR-030 postdates it) the way the renderer choice was checked against the scale
requirement — this ADR is that check, arriving after the implementation rather than before it.

**The correction.** `02_GLASS_FRONTEND.md` §3.3's "Visual query builder" bullet is amended in the
same change that adds this record: "draws" becomes "composes," describing the palette/pin/connect
list editor `QueryBuilderPanel.tsx` actually is, not the canvas the original phrasing implied.

**On "saveable, shareable and versioned," the same bullet's own third promise.** Checked separately
and found not built at all, in any of the three: `PatternQuery` has no persistence path, no owner
or share target, and no version history — Stage 4 built the compose/preview/run loop only. B19's
own assertion does not need any of the three (it is a one-shot expand-and-return), but B20's does
("save the pattern as a monitor"), and B20 is named in Phase 7's own exit criterion alongside B19.
Saving-as-a-monitor (B20, Stage 6's own hotlist/saved-pattern-monitor bullet) and saving a pattern
as a reusable, shareable, versioned object in its own right (this bullet's own promise) are related
but not the same capability — a monitor is one specific consumer of a saved pattern, not a
demonstration that generic save/share/version exists. Recording this in `07_BUILD_PLAN.md`'s own
Phase 7 known-gaps list rather than treating Stage 6 as an automatic answer to it.

**Cost.** One corrected word in `02_GLASS_FRONTEND.md` §3.3, this record, and a new Phase 7
known-gaps entry for the still-unbuilt save/share/version promise. No code changes — the
implementation this ADR describes already exists and is already tested; nothing here proposes
redoing it.

**Revisit if.** ADR-030's own pinned-root mechanism is superseded by a general multi-root join
(that ADR's own "revisit if"), at which point the pattern shapes this builder must represent grow
past what a list renders legibly and this ADR's own list-editor conclusion needs re-examining
alongside it — not before, and not on a general "canvases are nicer" preference absent that
trigger.

---
