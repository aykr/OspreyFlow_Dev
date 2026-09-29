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
| 032 | The visual query builder is a list/palette editor, not a second drawing canvas | | **Accepted, partially implemented** — 20 Sep 2026; save/load/list/version built 21 Sep (Part 3), sharing still deferred to ADR-040 |
| 033 | `Path.nodes`/`Path.edges` carry hydrated objects, not bare ids | | **Accepted** — 20 Sep 2026 |
| 034 | Publication and licence boundary; supersedes ADR-031 | | **Accepted** — 21 Sep 2026 |
| 035 | Demo distribution classes (`shipped`/`internal`); Fixture Corp is the shippable demo | | **Accepted** — 21 Sep 2026, one item declined as written |
| 036 | Saved-pattern monitor principal identity | | **Accepted** — 21 Sep 2026, its pattern-persistence contingency satisfied same day (Part 3) |
| 037 | Monitor trigger model and execution bounds | | **Accepted, amended** — 21 Sep 2026 |
| 038 | Hotlist membership and existence | | **Accepted, two-mode deployment policy** — 21 Sep 2026 |
| 039 | Alert inbox lifecycle | | **Accepted, two additions** — 21 Sep 2026 |
| 040 | Pattern sharing and query-definition disclosure | | **Proposed** — 21 Sep 2026 |
| 041 | Structural control for the fetch-then-check authorization bug class | | **Accepted, option (b)** — 21 Sep 2026, same day |
| 042 | The alpha gate: testers receive a build only after Phase 8's full exit criterion is green | | **Accepted** — 22 Sep 2026 |
| 043 | Principal resolution for a stored `owner_id`: OAuth2 Token Exchange (RFC 8693) | | **Accepted** — 22 Sep 2026 |
| 044 | Distinguishing an unreachable identity provider from a revoked principal | | **Accepted** — 22 Sep 2026 |
| 045 | Export withheld-item manifest and the recipient outside the boundary | | **Accepted, a deployment-level switch defaulting to disclosure** — 22 Sep 2026 |
| 046 | Assessment evidence lifecycle | | **Accepted, option (a), one addition and an export requirement** — 22 Sep 2026 |
| 047 | The Osprey export mark, and the durable record of what left the boundary | | **Accepted, both gaps** — 22 Sep 2026 |
| 048 | The disclosure doctrine: what makes "something was withheld" safe, unsafe or required to be visible | | **Accepted** — 22 Sep 2026 |
| 049 | The harness / packaging pipeline; Phase 8's Stage 2 §1–§7 | | **Accepted** — 24 Sep 2026, after rulings on all seven objections, D1 narrowed, and the four follow-on items settled |
| 050 | Sign-in for the Glass: OIDC authorization code with PKCE against the deployment's realm | | **Proposed** — 25 Sep 2026, milestone-blocking; seven open objections, three of them blocking |
| 051 | Sign in first, then show the interfaces the role allows: one launcher, one realm, the Admin console enforcing `osprey-admin` itself | | **Accepted** — 29 Sep 2026, owner's ruling; design only, build in progress |

**This table lagged again, and is caught here for the second time.** Records 042 through 048 were
written on 22 September 2026 and never added above — the identical omission this section's own
paragraph below already records for ADR-022 through ADR-029, recurring in the same document that
names it. Added 24 September 2026, in the same change that added ADR-049, which is also how the
lag was found: the new record was almost numbered ADR-044, because this table's own last row said
041 and nothing but a `grep` of the file's own headings would have said otherwise. **The standing
consequence, stated once:** the next record's number comes from the file's own last `## ADR-`
heading, never from this table.

Thirty-nine records (001–039) are accepted, including all seven overrides of the input documents.
ADR-036 through ADR-039 were drafted Proposed and accepted in the same session, two (037, 038)
with changes from their own first draft recorded in place rather than rewritten silently — see
each record's own amendment/decision section. ADR-036's acceptance was contingent on pattern
persistence existing; Part 3 of the same session built it (save/load/list/version, Stage 4's own
unfinished business), so the contingency is satisfied and the owning-principal reference ADR-036
needs now lives on `SavedPattern.owner_id`. ADR-040 is **Proposed**, not accepted —
it presents three options for pattern sharing without deciding one, and pattern sharing is not
built until it is accepted; a saved pattern is readable only by its own owner until then. ADR-041
is **Accepted, option (b)** — the mechanical `authorized-query-check` script, chosen over option
(a) (a composition point, kept recorded as the longer-term shape) because it works against the
codebase as it exists today; see the record itself for why documentation alone (this table's own
entries recording the first two occurrences) did not prevent a third, and for which of the three
live instances found while scoping it were hazards rather than leaks (all three).
`07_BUILD_PLAN.md`'s Phase 7 Stage 6 entry is cross-referenced to ADR-036–039, and its Phase 7
Stage 4 known-gaps entry is cross-referenced to ADR-032 and ADR-040. This table lagged the actual
record count for a stretch of Phase 7 (ADR-022 through ADR-029 were written but never added here)
— caught and closed in the same change that added ADR-030, not worth its own record.

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

**Addendum, 23 September 2026 — the same bypass, extended to a case this ADR's own text did not
yet name: two `Endpoint`s of *different* kinds, where a source asserts the link rather than
Splink inferring it.** The clause above covers person-like entities under genuine Splink scoring
and E.164-keyed endpoints under deterministic matching; it was silent on two differently-typed
endpoints (a messaging handle and a phone number, say) being linked at all — found while
correcting `08_ACCEPTANCE_SCENARIOS.md` B8 (`07_BUILD_PLAN.md`, 23 September 2026): `Endpoint`
carries no `resolution` block (`packages/ontology/default.yaml`), and the closed comparison
registry (`packages/ontology/resolution_functions.py`) has nothing that could meaningfully compare
a handle's own lexical space against an `e164` number's — the identical reasoning ADR-024 already
applied to MSISDN/IMSI. **The same bypass applies here as there**: where a data source states,
rather than infers, that two differently-typed identifiers name the same addressable point — a
device extraction's own record linking a handle to a phone number, the same category as an HLR
record linking an IMSI to an MSISDN — the write is a deterministic, asserted `SAME_AS` at score
1.0 (`WorkingSetService.manual_link`'s own shape, ADR-024's own precedent), never a Splink
comparison. This names a case the original text left silent; it is not a new exception to it.

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
proven anyway. The standing rule for this build is that a genuine spec gap gets fixed
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

**Decision.** The `ModelPort` conformance suite (`tests/conformance/model_port/test_suite.py`)
runs against Ollama's `qwen2.5:0.5b-instruct`
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
License (GPL)' is not on the spec/00_ARCHITECTURE.md §7 allowlist`. `00_ARCHITECTURE.md` §7
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

**Status.** Accepted, 18 September 2026. Undesigned work, per this build's own standing rule that
a spec silence is said so and proposed rather than filled silently — every inference below is a
proposal, flagged as such, not a claim that the spec already settles it. Where the spec does
constrain the answer, it is cited directly.

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

**The question, as `DEMO_GUIDE.md` §7 has posed it since it was written, unresolved until
now.** The VAST Challenge datasets are fabricated scenarios with no real people, clearing the bar
the real Enron corpus fails (fixtures must be synthetic and in-repo, with no real intelligence
data anywhere in this repository or in CI; standing rule 3's own naming of the demo). VAST
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
one.** `tests/scenarios/fixtures/cdr.py` and the still-unbuilt Fixture Corp (`DEMO_GUIDE.md`
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
Phase 8 at the time this ADR was first accepted; the naming was later split out into its own
addendum, 20 September 2026), not tested and found wanting.** `docker info` on this host reports a fixed 8,214,585,344-byte
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
inventing a new home for orphaned scope, the same shape already used once for Scenario B's
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

**Status.** Accepted, 20 September 2026. **Superseded by ADR-034** (21 September 2026), which
carries this record's own `spec/`/`process/` split forward unchanged (see ADR-034's own B1) and
adds the licence boundary, the restructure/publication trigger split, the new-repository
publication mechanism, authorship neutrality and the copyright-holder decision that this record
never addressed. Read this record for the physical-layout reasoning and ADR-034 for everything
about what leaves the repository, when, and under what name. Scheduled for the end of Phase 8 —
not built by this record, which documents and schedules the move rather than performing it.

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
  record — a log of decisions made over time — but is not one: this build's own standing rule
  makes every accepted ADR binding on the same footing as the numbered spec files, so it belongs
  in `spec/`, not `process/`, despite its own narrative shape. Filenames are unchanged, including their numeric
  prefixes — only the leading path segment changes (`spec/01_DOMAIN_MODEL.md` →
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
drift — in a build whose own central, standing discipline is that the repository itself is the
source of truth. Two top-level directories inside one repository keep
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
existing citation of `spec/06_DECISIONS.md`'s own ADR numbers, `01_DOMAIN_MODEL.md`'s section
numbers, and so on stays correct without further edits, since only the leading path segment
changes for the numbered files.

**Revisit if.** The specification is still changing shape materially at Phase 8's own close —
delay the move a further, explicitly-named increment rather than force it against a target still
moving, the same reasoning that sets this timing in the first place.

**Executed 28 September 2026, round 14a — see `process/07_BUILD_PLAN.md`'s own Trigger A entry for
the full closure record** (the exit-criterion result, the root listing, and the gates re-verified
against the new tree). `docs/` no longer exists in this repository.

---

## ADR-032 — The visual query builder is a keyboard-native list/palette editor, not a second drawing canvas; `02_GLASS_FRONTEND.md` §3.3 is corrected to match

**Status.** Accepted, 20 September 2026. **Partially implemented — recorded explicitly here
because this record had been reading as done.** Stage 4 (20 September 2026) built compose, preview
and run only. **Save, load, list and version built 21 September 2026 (Part 3 of the same session
that accepted ADR-036–039)** — see the updated paragraph below and `07_BUILD_PLAN.md`'s Phase 7
Stage 4 known-gaps entry, both updated to record what shipped. Sharing is deferred to ADR-040,
Proposed, not accepted — a saved pattern remains readable only by its own owner until that record
is decided.

**The premise.** `02_GLASS_FRONTEND.md` §3.3 specifies the visual query builder as "a
node-and-edge pattern the analyst draws" — language that reads, and was built against elsewhere in
this document, as a second Sigma/graphology drawing surface beside `GlassCanvas`. Phase 7 Stage 4
built something else: `apps/workspace/src/patterns/QueryBuilderPanel.tsx`, a `Panel` of native
controls — an entity-type palette that places a pattern node, `GlobalSearch` reused to pin one, a
list of the pattern's own nodes and edges, and Preview/Run. This was disclosed as a scope choice in
the implementation session's own summary rather than recorded in `docs/`, which this repository's
own standing discipline (ADR-023, 028, 029, 030 each correcting spec text the moment
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

**On "saveable, shareable and versioned," the same bullet's own third promise — updated 21
September 2026, not left as originally drafted.** At first checked and found not built at all, in
any of the three: `PatternQuery` had no persistence path, no owner or share target, and no version
history — Stage 4 built the compose/preview/run loop only. **Save, load, list and version are
built, 21 September 2026 (Part 3 of this same session):** `services/api/pattern_store.py`'s
`PatternStore` and `POST/GET /v1/patterns*` (`services/api/app.py`) make a `PatternQuery`
saveable, loadable, listable and versionable, with an `owner_id` field satisfying ADR-036's own
contingency. **Sharing is not built** — a saved pattern is readable only by its own owner — and
stays that way until ADR-040 (pattern sharing and query-definition disclosure, Proposed) is
accepted; ADR-040 records why sharing is a distinct leak from the result-time leaks ADR-038
already settled for hotlists. B19's
own assertion does not need any of the three (it is a one-shot expand-and-return); B20's does
("save the pattern as a monitor"), and save/version is what B20 actually needed — sharing was
never B20's own requirement, only this bullet's separate, broader promise. **This gap now lives in
`07_BUILD_PLAN.md`'s Phase 7 Stage 4 known-gaps entry, not Stage 6's** — a monitor is one specific
consumer of a saved pattern (Stage 6's own concern), not the same thing as generic save/share/
version existing (Stage 4's own unfinished bullet), and the two should not be scoped together a
second time.

**Cost.** One corrected word in `02_GLASS_FRONTEND.md` §3.3 (20 September), this record, real
implementation work for save/load/list/version (21 September, Part 3 — a new Postgres-backed
store, three routes, TS type regeneration, direct-Postgres access-control tests, and two new
keyboard-registered actions with their own Playwright proof), and a residual, still-open gap for
sharing, priced separately once ADR-040 is decided.

**Revisit if.** ADR-030's own pinned-root mechanism is superseded by a general multi-root join
(that ADR's own "revisit if"), at which point the pattern shapes this builder must represent grow
past what a list renders legibly and this ADR's own list-editor conclusion needs re-examining
alongside it — not before, and not on a general "canvases are nicer" preference absent that
trigger.

---

## ADR-033 — `Path.nodes`/`Path.edges` carry hydrated `Node`/`Edge` objects, not bare ids; `PathBuilder`'s own `elementMap()`-inside-`path()` limitation on this adapter

**Status.** Accepted, 20 September 2026.

**The gap, found while tracing how a found path would actually reach the canvas.** `Path.nodes:
list[NodeId]` and `Path.edges: list[EdgeId]` (`packages/schemas/domain.py`) have carried bare ids
since Phase 1 — `PathBuilder.render_gremlin`'s own compiled query ended `.path().by("id").by
("id")`, and `GraphArcadeDBAdapter.paths()` parsed the interleaved result straight into bare-id
`Path` objects. This was never exercised against a real caller before Phase 7 Stage 5, because
nothing before the pathfinder read a `Path`'s own `.nodes`/`.edges` for anything beyond a
conformance assertion on `.length`. A bare id cannot be rendered: `canvas/nodeAttributes.ts`'s own
`computeNodeGraphAttributes` needs a node's `type` (via `OntologyRegistry.visualFor`) to choose a
channel/shape at all, and a node not already in the analyst's working set has no other source for
its own properties. `02_GLASS_FRONTEND.md` §3.1's own "paths render with the on-path node state"
is not satisfiable from an id alone.

**The fix.** `Path.nodes: list[Node]`, `Path.edges: list[Edge]` — the same hydrated shape
`Subgraph` already carries. Checked against every existing caller before widening: nothing outside
`tests/conformance/graph_port/test_suite.py` touches `Path.nodes`/`.edges` today, and every
existing assertion there reads `.length`, never `.nodes`/`.edges` — this widens cleanly, the same
"checked, not assumed, that nothing breaks" discipline every other widening in this record follows.

**The real mechanism, checked against a live ArcadeDB instance rather than assumed from the
compiled-string change alone — the second time this build has found an ArcadeDB-specific Gremlin
limitation this way, after ADR-030's own `match()` finding.** The natural first attempt —
`.path().by(elementMap()).by(elementMap())`, hydrating in place of the two `.by("id")` calls —
fails on this adapter: ArcadeDB's own Gremlin engine raises a server-side `ClassCastException`
("`T$2` cannot be cast to `java.lang.String`") the moment an `elementMap()` modulator is cycled
through `path()`'s own interleaved vertex/edge/vertex/... steps, confirmed directly by running the
query against a live instance, not inferred from the TinkerPop specification. `render_gremlin`
itself is therefore unchanged — still `.by("id").by("id")`, still exactly the query
`test_unauthorised_path_length_matches_a_graph_without_the_hidden_hop` already proves is
access-filtered at every step. Hydration happens in two new, separate follow-up queries
(`PathBuilder.render_hydrate_nodes_gremlin`/`render_hydrate_edges_gremlin`), anchored at `g.V()`
with the path's own (already access-proven) ids passed via `within()` — the same "separate query
per element type" shape `ExpandBuilder.render_nodes_gremlin`/`render_edges_gremlin` already use,
not a new pattern invented for this. `has_access` is re-applied on both follow-up queries as
defence in depth, not because it is load-bearing: every id being hydrated already passed the
original path traversal's own filter before this stage ever sees it.

**Does this weaken the access-control guarantee SECOND (Phase 7 Stage 5's own session) names?**
No, and for the same reason ADR-030 gives for its own widening: what changed is what is
*materialised* per step, never which step is allowed onto the path in the first place. The
`has_access` injection points inside `render_gremlin` are untouched; the two hydration queries
only ever run against ids the filtered traversal already produced.

**Cost.** One widened schema (`Path`), a compiled-string no-op (`render_gremlin` itself
unchanged), two new builder methods, and two extra round trips per `paths()` call — bounded by the
number of distinct nodes/edges across every found path (at most `k × max_hops`, tens of elements,
not hundreds). `tests/conformance/graph_port/test_suite.py` gains
`test_paths_returns_hydrated_nodes_and_edges_not_bare_ids`; `01_DOMAIN_MODEL.md` §8's own `Path`
code block is updated to match, the same synchronisation this record's own precedents (ADR-030 for
`PatternNode`) already established.

**Revisit if.** A future ArcadeDB release fixes `elementMap()`'s own behaviour inside `path()`
(worth re-testing before assuming it still fails, the same "revisit sooner" discipline ADR-030's
own `match()` finding already states) — at which point the two-query hydration could collapse back
into the single traversal, a performance refinement, not a correctness one; nothing about the
`Path` schema itself would need to change again.

---

## ADR-034 — Publication and licence boundary: ADR-031's split carried forward, Apache 2.0 scoped to the product tree, two independent triggers, new-repository publication, authorship neutrality, and "The OspreyFlow Authors"

**Status.** Accepted, 21 September 2026. Supersedes ADR-031 (`06_DECISIONS.md` above), whose own
`spec/`/`process/` physical split this record carries forward unchanged rather than revisits.

**Scope note.** This record is documentation only — no product code changes. `07_BUILD_PLAN.md`'s
Phase 8 close step is amended to cite this ADR (alongside ADR-031, not in place of the physical-
layout reasoning ADR-031 still owns).

### B1 — Top-level segregation, unchanged from ADR-031

ADR-031's `spec/`/`process/` split, and root-level product documentation (`README.md`,
`DEMO_GUIDE.md`), is carried forward exactly as that record states it — `docs/` dissolves into
`spec/` and `process/` at Trigger A (below), one repository with two top-level directories, not two
repositories, for the citation-integrity reasons ADR-031 already gives in full. Nothing in this
record revisits that reasoning or that layout.

### B2 — Licence boundary

**Apache 2.0** covers the core product code (`packages/`, `services/`, `apps/`, `scripts/`,
`tests/`) and the installation, developer, architecture and user guides: `spec/00_ARCHITECTURE.md`
through `spec/05_DEPLOYMENT.md`, `spec/08_ACCEPTANCE_SCENARIOS.md`, `spec/09_INGEST_STUDIO.md`,
`spec/design/` (including `tokens.css`), and the root-level `README.md`/`DEMO_GUIDE.md` ADR-031
already places outside `docs/`.

**Excluded and private** — the build framework: the prompt register (`.claude/`, including
`CLAUDE.md`), the phase plan (`07_BUILD_PLAN.md`), the decision log (`06_DECISIONS.md`), the
distribution/delivery record (`PRODUCT_DELIVERY.md`, new 22 September 2026 — the alpha gate, the
analyst review, and every owner action described in that record's own text, the
same "how the product reaches people rather than how it gets built" material this list already
excludes elsewhere in the phase plan's own case), design provenance (`DESIGN_PROVENANCE.md`),
the gap inventory (contained entirely within `07_BUILD_PLAN.md` — no separate file), and handover
documents (`SESSION_HANDOVER.md`, `NEXT_STEPS_PHASE7.md`, `archive/`).

**This is not the same axis as ADR-031's `spec/`/`process/` split, and the overlap needs stating
precisely rather than left to be inferred.** ADR-031 places `06_DECISIONS.md` inside `spec/`
because this build's own standing rule makes every accepted ADR binding "on the same footing as
the numbered spec files" — a statement about what is operationally authoritative *for continuing
this build*, unrelated to who should be allowed to read it. `06_DECISIONS.md`'s own content is, in
substance, exactly the process record ADR-031's own text says it "reads like" — a log of decisions,
the mistakes found on the way to them, the internal deliberation behind each — which is precisely
the class of thing B2's "excluded and private" list is drawn to keep out of a published artefact.
The two records are not in tension: `06_DECISIONS.md` stays in `spec/` at Trigger A (ADR-031's own
directory move, unchanged per B1) and is *also* excluded from what Trigger B ever publishes — a
file's physical location in the private working tree and its licence/publication status are
independent facts about it, and this is the one file in the tree where they visibly disagree.
`07_BUILD_PLAN.md` has no such tension — ADR-031 already places it in `process/`.

**A consequence, checked and recorded rather than left for whoever reaches Trigger B to discover.**
`06_DECISIONS.md` carries the only copy of every ADR's own reasoning, and a large fraction of the
1,150 citations ADR-031's own count established are citations *of* `06_DECISIONS.md` by ADR number,
from docstrings scattered across the product code that does publish (this session alone added
citations to ADR-033 from `builders.py` and `adapter.py`, both Apache-tree files). Once
`06_DECISIONS.md` itself stays private, every one of those citations becomes, to a reader of the
published repository, a reference to a document they cannot open. Not a defect in the citations
themselves — they remain exactly as load-bearing as ADR-031 already established for this repository
— but a real, foreseeable degradation of the published artefact's own self-explanatory-ness, not
previously named anywhere. Recorded as **open item, owned by Trigger A**: `scripts/
doc_citations_check.py` (ADR-031's own new checker, built at the same Phase 8 close this record's
own restructure fires at) should be extended, or a sibling check added, to flag any ADR-number
citation inside a file that itself lives in the Apache tree — not to remove the citations, which
stay true and useful to this repository's own maintainers, but so the gap is measured rather than
discovered by an external reader.

**Correction, 23 September 2026 — "not to remove... so the gap is measured" no longer describes
the whole of this gap, only the larger part of it this session did not touch.** This paragraph's
own 1,150-citation figure (ADR-031's own original estimate, and this paragraph's — both left as
originally written, above and here, rather than edited after the fact) is superseded: §B10's own
later, gate-derived census puts the real source-code figure at 1,579, found the same day this
correction was written. Wherever this document quotes a citation count for the source-code half
of this gap, treat it as a snapshot dated to its own paragraph, not a fixed number — §B10 has the
reasoning for why a bespoke regex kept undercounting it. This paragraph's own reasoning stands:
still almost entirely source-code docstrings (`packages/`/`services/`/`apps/`), genuinely still
unsettled, "measured, not removed" remains the right call for that set, unchanged here. **The documentation-to-documentation subset of the identical gap — an
Apache-scoped *document* citing `06_DECISIONS.md`/`07_BUILD_PLAN.md`/`CLAUDE.md`, not a source
file's own docstring — is now settled, differently: `scripts/product_tree_link_check.py`
(§B9, below) measures it exactly as this paragraph proposed, but the decision on what to do with
what it finds is rewrite, not permanent measurement** — state the rule, lose the private-file
reference (§B9 has the method and the 72 current instances). The two subsets share one underlying
gap and now have two different, deliberate dispositions, not one paragraph quietly describing
both.

### B3 — Two triggers

- **Trigger A, restructure.** Fires at the close of Phase 8. Moves files per ADR-031/B1. The
  repository stays private throughout.
- **Trigger B, publication.** Fires only on explicit owner instruction, once Trigger A, publication
  readiness (the documentation-refresh stage) and the Trigger B rehearsal (including a green CI
  run) are all done and §B4's own open items are decided. **Owner ruling, 28 September 2026:
  alpha and beta testing (analyst review) follow Trigger B — they do not precede it and are not a
  precondition of it.** Nothing is shown to anyone outside the project before publication.

**Trigger A completing does not imply Trigger B, and nothing in `07_BUILD_PLAN.md` may treat it as
implying it.** The Phase 8 close-step paragraph this ADR amends is written to name Trigger A only —
publication is never described there as a consequence of Phase 8 closing.

### B4 — Publication is a new repository, not this one made public

Moving a file into the private `process/` tree at Trigger A does not remove its earlier versions
from git history — every prior revision of the gap inventory, design provenance, handover documents
and prompt register stays readable via `git log -p`, in this repository, forever. The segregation
B1/B2 describe is effective for the working tree only.

**Binding: the published artefact is a new repository**, seeded from the restructured product
subtree, with a single initial commit and no inherited history. Rewriting this repository's own
history is not a substitute unless the owner explicitly chooses it — every commit SHA cited across
`docs/`/`spec/` and `process/` would be invalidated by a history rewrite, and nothing chooses that
lightly.

**Record: destination account `github.com/ospreyflow`, currently a personal account.** The name
`github.com/ospreyflow/ospreyflow` is reserved and deliberately unclaimed until Trigger B. **Open
item, owned by Trigger B:** whether that account converts to a GitHub organisation before the first
public push — GitHub's terms permit one free personal account per person, so this needs settling
before the account becomes publicly active, not after.

**Updated to record fact, not intent — checked directly, not assumed from the paragraph above.**
This working repository's own `origin` remote now points at `github.com/ospreyflow/ospreyflow-dev`
(`git remote -v`; the prior `origin`, `github.com/ayankarsolirius/ospreyflow.git`, survives only as
a `backup` remote) — the `ospreyflow` account is already in active use for this private working
tree, not merely reserved. **This is not Trigger B**: `ospreyflow-dev` is a second, still-private
repository under that account, not the published artefact B4's own binding requires (a new
repository seeded from the restructured subtree, at Trigger B, on explicit owner instruction) —
recorded here because the destination account's own state changed, not because Trigger B fired.
`github.com/ospreyflow/ospreyflow` (no `-dev` suffix) **remains unclaimed**, reverified the same
way as the paragraph above's own claim, not re-asserted from it: `git ls-remote https://github.com/
ospreyflow/ospreyflow.git` — using the identical credentials that resolve `ospreyflow-dev`
successfully — returns `remote: Repository not found`, the strongest evidence available from
inside this session that the name is genuinely unclaimed rather than merely private-and-
inaccessible (an unauthenticated `curl` against the GitHub API cannot distinguish the two, checked
directly: it returns `404` for both `ospreyflow/ospreyflow` and the known-to-exist
`ospreyflow/ospreyflow-dev` alike).

### B5 — Authorship neutrality

**The identifier set, established from the whole commit history, not `HEAD`:**

```
git log --format='%an|%ae|%cn|%ce' | sort -u
```

```
Ayan Kar|ayan.kar@solirius.com|Ayan Kar|ayan.kar@solirius.com
ayankarsolirius|ayan.kar@solirius.com|ayankarsolirius|ayan.kar@solirius.com
OspreyFlow|331628805+ospreyflow@users.noreply.github.com|OspreyFlow|331628805+ospreyflow@users.noreply.github.com
```

Search patterns taken from this: the personal name "Ayan Kar", the handle "ayankarsolirius" (also
the URL path segment of what was `origin` when this record was written, `github.com/
ayankarsolirius/ospreyflow.git` — now the `backup` remote; B4 above records `origin`'s own move to
`github.com/ospreyflow/ospreyflow-dev`, which changes nothing here since the search pattern comes
from the commit-author identity, not the remote URL, and that identity is unchanged), and the
employer domain `solirius.com`. The third identity (`OspreyFlow` / the GitHub noreply address) is
already neutral and is not a search pattern.

**Verified against every tracked file, not assumed from a prior count:**

```
git grep -liE "ayan\.?kar|ayankarsolirius|solirius" -- .
```

matches exactly one tracked file: the current handover document (its own byline line, "2026-09-18 ·
@Ayan", and two body references to "Ayan"/"Ayan's Mac"). No other tracked file in the repository —
product code, the spec, or any other build-record document — carries a personal name,
handle or employer domain. The handover document is explicitly out of scope for this session
(its byline is handled at Trigger A) and is unchanged here.

**Binding: the product tree, the published guides and the prompt register carry no personal name,
employer name or employer email domain.** Where an owner decision needs attributing, the term is
"the owner". The handover document is the one currently-tracked exception, already scoped to
Trigger A rather than this session.

**Open item, owned by Trigger B:** the initial commit of the published repository is authored under
a neutral identity, set in git config before that commit is made — not the identities in the table
above, none of which is anonymous enough to seed a repository whose whole point is to carry no
personal identity.

**Open question for the owner, not decided here:** published documents (the guides moving to the
Apache tree, and — per B2's own new finding above — every product-code docstring citing an ADR by
number) cite commit SHAs and ADR numbers from this private repository, neither of which resolves
for a reader of the published artefact. Options are to strip SHA/ADR citations from published docs
at Trigger B, or to accept that a published citation is sometimes a dead end and say so once,
prominently, rather than fix every instance. The owner's call, not this record's.

### B6 — Copyright holder: "The OspreyFlow Authors"

Year set at Trigger B, being the year of first publication.

**Three consequences, recorded rather than left implicit:**

1. **The choice is reversible until the first external contribution, and effectively irreversible
   after it.** Consolidating under a named entity after external contributions have landed requires
   assignments from every contributor. The contributor agreement is therefore a blocking gate on
   the first external pull request — a later, distinct moment from publication itself, and not to
   be conflated with Trigger B.
2. **Recommended, not decided: a DCO (a `Signed-off-by` line, no paperwork) over a CLA.** No
   relicensing right is needed for a services-based commercial model, and a CLA suppresses casual
   contribution a DCO does not. Recorded as the owner's own call to make, not made here.
3. **The published artefact will contain no record of who the authors are** — B6's own notice
   enumerates no names, and B4's single squashed initial commit under a neutral identity (B5) is
   the only history it carries. Anonymisation removes the evidence of authorship along with the
   name unless something else preserves it. **Trigger A deliverable, in the private build tree:** a
   dated authorship record, created at the restructure rather than assumed to exist later.

**Dated context, not a decision:** Companies House showed no registration for "OspreyFlow" or
"Osprey Flow" as at 2026-09-20. Companies House availability is not trademark availability — the
IPO register is a separate check, an owner action with months of lead time, not addressed here.

### B7 — Packaging's own artefact-hygiene properties

**Restated 22 September 2026, when `07_BUILD_PLAN.md` was restructured to read as construction
only: these are properties of the packaging pipeline producing an artefact at all, not a condition
on who receives one.** A built artefact that leaks the private build tree or an authorship
identifier is wrong the moment it exists — the same way an access-control bug is wrong whether or
not an unauthorised principal ever actually exploits it — independent of whether that artefact is
ever handed to anyone. Two assertions are required on the packaging step itself, both failing the
build:

1. **No file originating in the private build tree appears in the built artefact.** If a packaging
   step copies the repository root, `docs/`/`spec/`/`process/` and `.claude/` ride along inside
   image layers — invisible at runtime, fully recoverable from the tarball. The same containment
   check already run for `scripts/mint_dev_token.py`; never run for `docs/`.
2. **No identifier from B5's set appears in the built artefact**, including whatever the build
   reads out of git for version metadata — a version string built from an author field would
   reintroduce the name into an artefact this pipeline produced.

**Not addable in this session** — no packaging/harness step exists yet to attach either assertion
to (the browser harness and its packaging pipeline are Phase 8's own outcome, not built until then).
**Recorded here as required work owned by Trigger A**, per this ADR's own §B3: the harness that
Phase 8 builds must ship with both assertions from its first version, not add them later —
`07_BUILD_PLAN.md`'s own packaging stage states and tests them as its own exit criterion. Who an
artefact satisfying both may then be given to, and when, is a distribution decision downstream of
this one, recorded in the distribution/delivery record, not in this ADR or in the build plan.

**Cost.** Documentation only in this session: two ADR cross-references (this record, and ADR-031's
own superseded pointer), one `07_BUILD_PLAN.md` amendment (below), and one open item added to
`scripts/doc_citations_check.py`'s own eventual scope (owned by Trigger A, not built here). Trigger
A itself carries real cost when it fires — the authorship record (B6), the tester-artefact gates
(B7) — recorded as owed work, not discharged by this record.

**Revisit if.** The owner settles any of B4's account-conversion question, B5's SHA/ADR-citation
question, or B6's DCO-vs-CLA recommendation before Trigger B — each is written here as open
precisely so settling it is a small, targeted edit to this record rather than a new ADR.

**Addendum — §B2/§B6 decide the licence and the holder; they do not, on their own, create the
files that carry either.** Checked directly, not assumed: no `LICENSE`/`NOTICE` file exists
anywhere in this repository, and neither `make licence-check` leg checks for one, both being scoped
to third-party dependency licences only. Filed as two new Trigger A deliverables in
`07_BUILD_PLAN.md`'s own Phase 8 close step (LICENSE/NOTICE presence; a licence-check gate covering
them), not decided or built here — a decision record and the build step that discharges it are not
the same thing, and this is the one place in this ADR where that gap had gone unrecorded. Per-file
Apache 2.0 headers are a distinct, still-open question for the owner, the same "not made here"
treatment §B6 already gives DCO-vs-CLA — recorded in the same `07_BUILD_PLAN.md` entry, not answered
by this addendum.

### B8 — The split cannot be decided by directory name alone: what the product actually reads

**Found 23 September 2026, generalising a single instance (`spec/design/tokens.css`) that
Trigger A's own exit criterion (`07_BUILD_PLAN.md`, above) had already named.** Every file under
`docs/` that any code path actually reads or imports, at build time or run time, checked directly
— `grep` for `import`/`open`/`Path`-construction patterns combined with a `docs/` path, across
every `.py`/`.ts`/`.tsx` file in the repository, not assumed from directory structure:

| File | Real consumer(s) | Mechanism |
| --- | --- | --- |
| `spec/design/tokens.css` | 12 real source files under `apps/workspace/{export-capture,map-verify,perf,a11y,keyboard}/` and, critically, `apps/workspace/src/main.tsx` — the Glass's own real entry point; plus `apps/workspace/src/color/tokens.test.ts` | TypeScript `import` (compile-time, 12) + `readFileSync` (run-time, 1) |
| `spec/00_ARCHITECTURE.md`, `02_GLASS_FRONTEND.md`, `04_VAULT_BACKEND.md`, `05_DEPLOYMENT.md`, `08_ACCEPTANCE_SCENARIOS.md`, `09_INGEST_STUDIO.md` | `scripts/route_coverage_check.py`'s own `APACHE_DOC_PATHS` | `Path.read_text()` |
| `spec/01_DOMAIN_MODEL.md` | `scripts/route_coverage_check.py` (via `APACHE_DOC_PATHS`) and `scripts/domain_model_coverage_check.py` (its own dedicated `DOC_PATH`) | `Path.read_text()` |
| `spec/03_CONDUIT_MIDDLEWARE.md` | `scripts/route_coverage_check.py`, both via `APACHE_DOC_PATHS` and its own dedicated `DOC_PATH` (route-table extraction) | `Path.read_text()` |
| `DEMO_GUIDE.md` | `scripts/route_coverage_check.py` (via `APACHE_DOC_PATHS`) and `scripts/demo_guide_check.py` (its own dedicated `DEMO_GUIDE_PATH`) | `Path.read_text()` |
| `README.md` | `scripts/route_coverage_check.py` (via `APACHE_DOC_PATHS`) | `Path.read_text()` |
| `spec/06_DECISIONS.md`, `07_BUILD_PLAN.md`, `spec/design/OspreyFlow_Brand_Foundations.html`, everything under `process/archive/`, `SESSION_HANDOVER.md`, `NEXT_STEPS_PHASE7.md`, `DESIGN_PROVENANCE.md` | **None found** | — |

**Two different relationships, not one, and the split follows the relationship, not the file
extension or the current directory.**

- **`scripts/route_coverage_check.py`/`domain_model_coverage_check.py`/`demo_guide_check.py`
  reading spec prose to check it against real code (a drift gate) is not the case this session's
  own instruction names.** Every file these three scripts read is already destined for `spec/` or
  the repository root under ADR-031's own existing target layout — `scripts/` itself is not named
  in that layout and does not move (`07_BUILD_PLAN.md`'s own Trigger-A exit-criterion entry has
  the full check). Both sides of this dependency move together, inside the same repository,
  exactly the shape ADR-031's own "one repository, two top-level directories" reasoning already
  covers — this needs the path strings rewritten (`docs/` → `spec/` or root), the same mechanical
  pass every other citation gets, not a reclassification.
- **`spec/design/tokens.css` is a different relationship in kind, not only in count.** The Glass
  does not check this file for drift against something else — it **cannot build or render without
  it**: `main.tsx`, the application's own real entry point, imports it directly, and a build with
  the import unresolved fails outright. **Per this session's own principle, stated plainly: a file
  the product links against to function is product source, regardless of which directory it
  currently sits in.** ADR-031's own target layout currently places `design/` (`tokens.css`, brand
  foundations) inside `spec/` — correct for `OspreyFlow_Brand_Foundations.html`, which nothing
  code-linked touches, but **not correct for `tokens.css` by this same principle, and this ADR's
  own text should not be read as having settled that question already.** `06_DECISIONS.md` ADR-032
  and `02_GLASS_FRONTEND.md` both already treat `tokens.css` as the authoritative source of the
  Glass's own design tokens, not as prose about them — the file is closer in kind to
  `packages/schemas/domain.py` (authoritative, code-linked, not merely descriptive) than to
  `01_DOMAIN_MODEL.md` (describes the schema; does not run as it).

**Decision, owned by Trigger A, not made here as a side effect of finding it:** `spec/design/
tokens.css` moves with the product tree (a real candidate location: `apps/workspace/src/design/
tokens.css`, updating all thirteen real consumers' own paths in the same pass, mechanically
verified by `scripts/product_tree_link_check.py` — built the same session this was found, §B9
below has the full record), not into `spec/design/` alongside `OspreyFlow_Brand_Foundations.html`,
which stays exactly where ADR-031 already puts it. **This is Trigger A's own seventh deliverable:
the product tree must contain everything the product actually reads, and this split cannot be
decided by which top-level directory a file happens to sit in today.** Not built here — the
physical move waits for Trigger A, per this document's own standing instruction that a rewrite
against a structure that has not happened yet drifts before it lands.

### B9 — `README.md`/`README.md` audited against this ADR's own boundary; a link-integrity
gate built; the build process itself found mentioned throughout the Apache-scoped set, not only
in the READMEs

**Found and built 23 September 2026.** Two things this session's own instruction asked for
separately, reported together since the gate exists specifically to make the audit's own findings
mechanically enforceable rather than a one-time report that goes stale.

**No root `README.md` exists yet — checked directly, not assumed** (matches ADR-031's own already-
recorded gap: "this repository currently has no root-level `README.md` at all"). `README.md`
is the only one that exists, and is the one audited below; ADR-031's own text already names it as
the file `README.md`'s eventual content is drawn from.

**Every reference in `README.md`, classified:**

| Reference | Category | Disposition |
| --- | --- | --- |
| "for implementation by Claude Code" (L3); "Supersedes the v1.0 draft… folded into this folder at the start of the project" (L3-5) | **PROVENANCE** | Goes |
| `06_DECISIONS.md` (L64, L78) | **LINKS PRIVATE** | Must go — stays inside `spec/` but excluded from the Apache-scoped/published set (`route_coverage_check.py`'s own `APACHE_DOC_PATHS` deliberately excludes it); dangles the moment this becomes the published root `README.md` |
| `07_BUILD_PLAN.md` (L65) | **LINKS PRIVATE** | Must go — same reasoning as `06_DECISIONS.md` |
| `NEXT_STEPS_PHASE7.md`, `SESSION_HANDOVER.md`, `DESIGN_PROVENANCE.md`, `archive/` (L70-73) | **LINKS PRIVATE** | Must go — explicitly `process/`-destined under ADR-031's own target layout |
| `00_ARCHITECTURE.md`, `01_DOMAIN_MODEL.md`, `02_GLASS_FRONTEND.md`, `03_CONDUIT_MIDDLEWARE.md`, `04_VAULT_BACKEND.md`, `05_DEPLOYMENT.md`, `08_ACCEPTANCE_SCENARIOS.md`, `09_INGEST_STUDIO.md`, `design/tokens.css`, `DEMO_GUIDE.md` (L58-69) | **PUBLISHED DOCUMENTATION** | Stays — not removed, per this session's own instruction that orphaning deliberately-published documentation is the opposite failure |

**Not removed here** — per the same instruction, and per this document's own standing rule that a
rewrite against a structure that has not happened yet drifts before it lands. Recorded as Trigger
A's own work, below.

**The build process, found mentioned well beyond the two READMEs — grepped across every
Apache-scoped document, not assumed absent.** `CLAUDE.md` — this project's own AI-assistant
instruction file, squarely build-process material — is cited by name and by numbered rule
(`CLAUDE.md` rule 3/7/9/12) from **six** Apache-scoped documents: `01_DOMAIN_MODEL.md` (×2),
`02_GLASS_FRONTEND.md`, `09_INGEST_STUDIO.md` (×2), `DEMO_GUIDE.md` (×2), plus `README.md`'s
own "for implementation by Claude Code." Each is both a **LINKS PRIVATE** case (`CLAUDE.md` is not
Apache-scoped) and a direct instance of what this search was for.

**Separately, and at far greater scale: "Phase N"/"Stage N"/"found during"/"found while"
annotations — a real, pervasive provenance pattern embedded throughout the spec's own prose, not
a README-only phenomenon.** Counted directly (`grep -c`), not estimated: `00_ARCHITECTURE.md` (7),
`01_DOMAIN_MODEL.md` (28), `02_GLASS_FRONTEND.md` (20), `03_CONDUIT_MIDDLEWARE.md` (7),
`05_DEPLOYMENT.md` (2), `08_ACCEPTANCE_SCENARIOS.md` (11), `09_INGEST_STUDIO.md` (8),
`DEMO_GUIDE.md` (17), `README.md` (2) — 102 in total, `04_VAULT_BACKEND.md` the only
Apache-scoped document with none. These are **PROVENANCE** by this session's own category
definition (they describe how the product was designed or built — "Implementation note (Phase 5
Checkpoint 3a)," "found during Phase 5 Checkpoint 2's live verification" — not what it is or how
to use it), and the volume is the finding: this is not a handful of stray mentions to excise from
two READMEs, it is a load-bearing citation style this entire specification pack was written in.
**Not rewritten here** — 102 instances across the core spec, several load-bearing for a reader
tracing *why* a decision was made, is real editorial work (rewrite to remove the process framing
while keeping the reasoning, not a bulk delete), not a mechanical pass, and belongs to whoever
does the documentation refresh and Trigger A together, not invented as a side effect of an audit.

**One false positive worth naming, so it is not later mistaken for a hit:** `03_CONDUIT_
MIDDLEWARE.md`:290's own "prompt" ("Changing a prompt or a model runs the set and reports
precision and recall") is the product's own extraction-pipeline configuration — a real runtime
concept the Conduit exposes, not a reference to prompts given to a build-time AI assistant. Found
by the same grep, correctly excluded from the count above.

**Built: `scripts/product_tree_link_check.py`, a link-integrity gate — `make product-tree-link-
check`, wired into `make ci` and `.github/workflows/ci.yml` as its own job.** Scoped to
documentation-to-documentation references, not every citation in the repository — its own
docstring has the full reasoning, including why the 1,150 source-comment citations ADR-031 already
counts are deliberately out of scope (a different, much larger concern `doc_citations_check.py`
already owns). Checks every Apache-scoped document (the same `APACHE_DOC_PATHS`
`route_coverage_check.py` already defines, imported rather than redeclared) against a private-tree
marker list (`06_DECISIONS.md`, `07_BUILD_PLAN.md`, `CLAUDE.md`, `SESSION_HANDOVER.md`,
`NEXT_STEPS_PHASE7.md`, `DESIGN_PROVENANCE.md`, `PRODUCT_DELIVERY.md`, `archive/`). **Runs today,
against the real repository: 72 violations found**, all real, all allowlisted (`tests/fixtures/
product_tree_link_allowlist.txt`) rather than fixed, per this document's own instruction not to
rewrite yet — the same "known debt enumerated, new debt fails immediately, list shrinks to zero as
part of Trigger A's own exit criterion" shape `route_coverage_check.py`/`domain_model_coverage_
check.py` already hold their own allowlists to. **Proven non-vacuous**: `tests/test_product_tree_
link_check.py::test_the_checker_actually_flags_a_private_tree_citation` plants a real violation in
an isolated fixture file and asserts the checker reports it — this caught a real bug in the first
implementation (a bare `Path.relative_to()` call that raised on a path outside the repository,
exactly what a fixture file needs) before it shipped, the "prove it can fail" discipline doing its
actual job, not a formality.

**Relationship to `scripts/doc_citations_check.py`'s own still-open ADR-citation question
(ADR-031, above), stated directly: genuinely different checks, not one wearing two names.**
`doc_citations_check.py` asks whether a citation *resolves* — true or false depending only on the
filesystem, the same answer regardless of where the citing file lives; a `06_DECISIONS.md`
docstring citing `07_BUILD_PLAN.md` must keep resolving after Trigger A, since both move into
`spec/` together. `product_tree_link_check.py` asks whether an Apache-scoped file cites a
non-Apache-scoped one at all — the identical citation, from `README.md`, must not exist,
because one side of it never publishes. **The two checks reach opposite verdicts on structurally
identical citations, depending only on the citing file's own destination — they cannot be merged
into one mechanical rule.** A shared citation-*extraction* utility is a reasonable future
refactor; the *judgement* applied to what each extracts cannot be shared without one gate silently
doing the other's job wrong.

### B10 — The source-code citation census, corrected; the filtered decision-log accepted; the
gate built; the rewrite done

**Counted twice.** The first pass (23 September 2026, earlier the same day) matched a
backtick-anchored filename pattern and reported 1,046 total / 717 product / 329 private. That
count was wrong, found wrong the same day: asked to re-derive it by taking
`scripts/product_tree_link_check.py`'s own marker-matching logic as the authoritative census
rather than a bespoke regex, the corrected count came out materially higher — **the method was
the finding, not the number**, exactly as the instruction that triggered the correction said it
would be.

**What the first pass got wrong, stated precisely.** It matched only `` `NN_NAME.md` `` —
backtick-quoted, no leading path. `product_tree_link_check.py`'s own `PRIVATE_TREE_MARKERS` match
is a plain substring search, no backticks required, no anchoring — and the corpus turned out to
cite these documents four ways the first pass missed entirely: `` `docs/NN_NAME.md` `` (a leading
path inside the backticks), bare mentions inside a runtime string literal (`"(07_BUILD_PLAN.md
Phase 6's own disclosed gap)"` in an exception message), and section-divider comments
(`# --- writes (07_BUILD_PLAN.md Phase 5) ---`). Checked directly and ruled out: markdown-link
citations, relative-path (`../docs/...`) citations, and bare-stem citations with no `.md` at all —
none exist anywhere in this corpus; every real citation is one of the forms above. `06_DECISIONS.md`
ADR-031's own approximate `1,150` turns out to undercount too, for the same reason at a smaller
scale — the true source-code total is higher, not close to it.

**The corrected method, now the standing one: the gate's own matcher, run against the source-code
population instead of the Apache-scoped-docs population `product_tree_link_check.py` itself
checks.** `find_violations()` already takes `doc_paths` as a parameter; passing every `*.py`/`*.ts`/
`*.tsx` file under `packages/`, `services/`, `apps/`, `scripts/`, `tests/` reuses the exact logic
the actual gate runs, rather than a second, divergent regex. Extended with the same substring
matcher over all ten spec filenames (not only the eight private-tree markers) for the product-side
total:

| Document | Citations | Tree |
| --- | --- | --- |
| `00_ARCHITECTURE.md` | 147 | product |
| `01_DOMAIN_MODEL.md` | 287 | product |
| `02_GLASS_FRONTEND.md` | 172 | product |
| `03_CONDUIT_MIDDLEWARE.md` | 144 | product |
| `04_VAULT_BACKEND.md` | 20 | product |
| `05_DEPLOYMENT.md` | 18 | product |
| `08_ACCEPTANCE_SCENARIOS.md` | 76 | product |
| `09_INGEST_STUDIO.md` | 159 | product |
| `06_DECISIONS.md` | 247 | private |
| `07_BUILD_PLAN.md` | 221 | private |
| `CLAUDE.md` | 82 | private |
| `SESSION_HANDOVER.md`, `NEXT_STEPS_PHASE7.md`, `DESIGN_PROVENANCE.md`, `PRODUCT_DELIVERY.md`, `archive/` | 6 | private |

Product-tree total **1,023**; private-tree total **556**; sum **1,579** — every occurrence counted
once per line via `findall`, not `search`'s first-match-only, which itself silently undercounts
any line citing two documents at once (common: `` `00_ARCHITECTURE.md` §1.2's tier-1 gazetteer
row, `08_ACCEPTANCE_SCENARIOS.md` A1, `07_BUILD_PLAN.md` Phase 5 `` cites three in one line). Every
product-tree citation still needs only a path rewrite at Trigger A. **`CLAUDE.md`'s own 82
source-code citations are a genuinely new finding** — Stage 3b's existing "6 files citing
`CLAUDE.md` by name and rule number" line item is documentation-only (READMEs, spec prose); this
is source code, a different and much larger population, not discovered until this gate-based
re-derivation. Not sized or actioned further here — recorded as its own open item, below.

**The decision-log question: classify every ADR as PRODUCT or PROCESS — accepted, not merely
proposed.** Rule applied, and the rule every future ADR is classified by without re-deriving it:
PRODUCT is a decision about the shipped system itself (a port, a data model, an algorithm, a
security or behavioural contract) that a contributor building or extending the product needs;
PROCESS is a decision about how this build was scoped, phased, released, or published — the
project's own management, not the product's behaviour. Checked ADR-by-ADR against that rule, not
assumed from the number's own neighbourhood:

**PROCESS (8):** ADR-012 (vendor demo dropped from the requirements baseline), ADR-019 (Scenario
A's exit criterion split across phases), ADR-022 (Scenario B's exit criterion split across
phases), ADR-026 (VAST dataset admission / fixture policy), ADR-027 (B1/B13 ownership split
across phases), ADR-031 (the repository split, above), ADR-034 (this document, above), ADR-042
(the alpha gate / release timing). **These stay private.**

**PRODUCT (40):** every other accepted ADR, ADR-001 through ADR-048. **These publish with the
product tree.**

**Citations naming a specific ADR number, re-verified: 426, unchanged** — this figure used a
different, already-robust pattern (`ADR-0[0-9][0-9]` against the literal string, not a two-digit
capture group) and reproduces exactly on re-check. Of those, **10 cite a PROCESS ADR by number in
source-code prose** (ADR-022 ×6, ADR-031 ×1, ADR-034 ×3): **416 of 426 (97.7%) resolve** under the
accepted filtered log; 10 need the source-code rewrite, done below. Separately, of the 247
`06_DECISIONS.md` filename citations, 26 carried no ADR number on the same source line; re-examined
individually (not assumed unresolvable in bulk, per the instruction that triggered this): 20 had a
real ADR number on the *next* line (a line-wrap the same-line check missed, not an unresolvable
citation) — every one names a PRODUCT ADR (021 ×3, 025 ×2, 030 ×3, 033 ×2, 036, 041, 043, 047, 002,
017, plus generated-file mirrors) and needs no rewrite. Six were genuinely bare: two named the
exact PatternQuery-widening content of ADR-030 without citing it by number, fixed by adding the
number rather than deleting the reference (`packages/schemas/domain.py`, `packages/adapters/
graph_arcadedb/builders.py`, and both occurrences in `tests/conformance/graph_port/test_suite.py`
— the citation was accurate, just missing its own ADR number); two had no identifiable ADR at all
and were cut rather than guessed at (`apps/workspace/keyboard/keyboard.spec.ts`, `apps/workspace/
src/map/MapView.tsx` — the latter already carried `ADR-014` for the same claim, making the bare
`06_DECISIONS.md` mention pure redundancy). The rest were exempt, self-referential mentions inside
`scripts/product_tree_link_check.py` and its own test fixture — the marker-list data and the
docstring explaining it, not narrative citations.

**Checked directly, corrected: this document's own PRODUCT-ADR sections cite PROCESS ADRs six
times today, not zero as first reported.** The first check used a regex capturing two digits after
`ADR-0` (`ADR-0(\d{2})`) against a three-digit `PROCESS_ADR_NUMBERS` set — `"034"` never equals
`"34"`, so every comparison silently failed and "zero violations" was a false negative, not a
verified finding. Rerun with matching digit widths: **ADR-028 cites ADR-022 (×2), ADR-032 cites
ADR-019, ADR-035 cites ADR-026 (×5) and ADR-034 (×5) and ADR-042, ADR-037 cites ADR-042** — 6
distinct `(product, process)` pairs. Not rewritten here (editing this document's own prose is a
different, larger editorial task than a one-line code comment); allowlisted as known debt in
`tests/fixtures/decision_log_publication_allowlist.txt`, the same "known debt enumerated, new debt
fails immediately" shape every other gate in this repository already holds itself to.

**The cost, now paid rather than only stated.** `scripts/decision_log_publication_check.py` — `make
decision-log-publication-check` — checks exactly this: does a PRODUCT-classified ADR section cite a
PROCESS-classified one by number. A new script, not an extension of `product_tree_link_check.py`
(different extraction unit — ADR sections inside one file, not filenames across many — the same
"shares a shape, not an implementation" reasoning ADR-031 already applied to `schemas_check.py`
versus `licence_check.py`). Non-vacuous: `tests/test_decision_log_publication_check.py::
test_the_checker_actually_flags_a_product_adr_citing_a_process_adr` plants a real bad reference in
an isolated fixture and asserts the checker reports it — this caught the digit-width bug above
before the gate shipped with it, the "prove it can fail" discipline doing its job again. Wired into
`make ci` and `.github/workflows/ci.yml`.

**The rewrite: done, not merely sized.** Every real source-code citation of `07_BUILD_PLAN.md`
(all forms) rewritten to the agreed method — keep the constraint, drop the private pointer — with
one exception category left untouched by design: `06_DECISIONS.md` citations naming a PRODUCT ADR
need no rewrite at all (they resolve once the ADR publishes; the Trigger A path prefix is the only
change they ever need). Verified against the gate's own re-run after the rewrite: `07_BUILD_PLAN.md`
source-code citations fell from 221 to **0** real remaining (3 hits left are `product_tree_link_
check.py`'s own marker-list data and its docstring explaining that data, exempt for the same reason
the marker list itself is not a citation). `06_DECISIONS.md` citations are essentially unchanged in
count (247 → 250 under the more accurate `findall` recount) because the overwhelming majority were
always legitimate PRODUCT-ADR citations that never needed touching — the filtered-log decision
means most of this document's own source-code footprint was never a problem. **Comment-only
throughout**: no logic changed in any edit; `packages/schemas/generated/*.ts` regenerated from the
rewritten Python docstrings via `python3 packages/schemas/generate_ts.py`, not hand-edited, keeping
`make schemas-check`'s own drift guarantee intact. Full suite run before and after
(`.venv/bin/python3 -m pytest tests/`), both green — see this change's own commit for the count.

**`CLAUDE.md`'s 82 source-code citations: found, not actioned.** A genuinely new item this
re-derivation surfaced, distinct from Stage 3b's existing 6-file *documentation* citation count.
Not rewritten in this pass — scoped, sized, and left as its own open item so it does not vanish
into "already handled" the way the original miscount nearly did. See `07_BUILD_PLAN.md`'s own
entry, below, for its placement.

### B11 — The gate audit the digit-width bug provoked; three items sized, not solved

**Every gate in `make ci` checked for the same class of defect §B10's bug was: has it ever been
shown red by deliberate injection, not only observed green.** Eight already held themselves to
this — each with its own `test_the_check_fails_for_X`/`test_X_is_flagged` case, `CLAUDE.md` rule
12's "name the test" discipline already applied at the time each gate was built: `demo-guide-
check`, `domain-model-coverage-check`, `route-coverage-check`, `authorized-query-check`, `test-
file-coverage-check`, `product-tree-link-check`, `schemas-check`, and the Python half of
`licence-check`. Re-run live (23 September 2026), all pass. `decision-log-publication-check`
itself received an additional live `make`-level demonstration beyond its own unit fixture, being
the gate specifically found broken: a real `(ADR-006, ADR-042)` reference injected into
`spec/06_DECISIONS.md`, `make decision-log-publication-check` failed with the new pair named,
reverted, passed again clean.

**One gate had never been tested at all.** The Node half of `licence-check`
(`scripts/licence_check.mjs`) has run in CI since Phase 0 with no test file — its own `isAllowed`
predicate never shown red. Built `tests/licence_check/test_licence_check_mjs.test.mjs`. First
injection attempt (removing the GPL-rejection branch, asserting a bare `"GPL-3.0"` string still
correctly rejected) passed even with the bug present — the default-deny fallthrough
(`ALLOWED_MARKERS.some(...)`) already rejects any string matching no allowlisted marker, so a bare
GPL string is caught either way. The real risk is `main()`'s own `licenses.join(" AND ")` shape: a
dual-licensed package naming an allowed marker *and* GPL in one string. With the branch removed,
`isAllowed("MIT AND GPL-3.0")` returned `true`. Test corrected to cover this case; now genuinely
red-then-green. Wired into `make licence-check` and CI. **`CLAUDE.md` rule 15 records the standing
rule this incident makes: a gate's first green is not a result, it is an untested state; a new
gate is not wired into `make ci` until it has been shown red.**

**a. The 6 real ADR cross-reference violations — disposition, not fix.** All six: **rewrite the
citation**, none need reclassifying the cited ADR.

- **ADR-028 → ADR-022 (×2).** Both citations are build-process history attached to a PRODUCT
  decision ("split out by ADR-022's third addendum, 20 September 2026"; "the same shape ADR-022
  already used once for Scenario B's own six Glass screens") — precedent for how a phase's scope
  was reorganised, not architecture content. Rewrite: state the precedent without the ADR number.
- **ADR-032 → ADR-019.** Cites a mixed list (ADR-019, 022, 023, 027, 028, 029, 030) as examples of
  "this repository's own standing discipline" of correcting spec text immediately. The claim being
  illustrated is a documentation habit, not a technical fact; the PROCESS numbers in the list
  (019, 022, 027) can be dropped, keeping only the PRODUCT ones (023, 028, 029, 030) as the
  illustration, or dropping the enumerated list entirely.
- **ADR-035 → ADR-026 (×5), reconsidered, not reclassified.** First read: ADR-026 seemed
  misclassified, since ADR-035 cites it for a real technical fact ("the generated, VAST-shaped
  fixture ADR-026 already designs") a fixture-builder needs. Re-examined against ADR-026's own
  title — "the VAST Challenge datasets are admitted shaped, not verbatim; standing rule 3 is not
  amended" — the decision itself is a data-admission *policy ruling* (does this violate the
  fixtures-synthetic rule, and is that rule changed): governance of what the build is allowed to
  use, not a description of the shipped system. The technical consequence (fixtures must be
  shaped, not verbatim) is real, but it is a *consequence* of the policy, restatable directly in
  ADR-035's own prose without depending on ADR-026's number. **PROCESS stands.** Rewrite.
- **ADR-035 → ADR-034 (×5).** Cites the publication/licence boundary itself — "ADR-034's own B7
  finding," "ADR-034 §B3," "ADR-034 §B2." Unambiguously process: ADR-034 *is* the product/private
  split: it cannot be reclassified PRODUCT without contradicting its own purpose. Rewrite.
- **ADR-035 → ADR-042 (×1) and ADR-037 → ADR-042 (×1).** Cites the alpha gate/release-timing
  decision to explain why a demo review's timing matters, and to scope an amendment against it.
  Release gating, not architecture. Rewrite both.

**b. `CLAUDE.md`'s 82 source-code citations, broken down — where and for what.** By directory:
`packages/` 8, `services/` 15, `apps/` 21, `scripts/` 11, `tests/` 27. By shape: **59 of 82 (72%)
name a specific numbered rule** (`` `CLAUDE.md` rule 2/3/7 ``, "standing rule 2/`CLAUDE.md` rule
3") — the same rewrite already agreed for `07_BUILD_PLAN.md`: state the rule, drop the reference.
**23 of 82 (28%) cite it as a document, not a rule** — two are exempt (`scripts/product_tree_link_
check.py`'s own marker-list data and docstring, functional, not narrative), the other 21 cite a
named *section* ("Conventions," "before you write code") or paraphrase a rule without its number
("standing... no `osprey` CLI yet," "fail loudly, never dropped silently posture," "own session
priority"). **That is different, as asked**: "state the rule, drop the reference" only works when
the citation already names which rule; a section-name or paraphrased citation needs the actual
constraint pulled forward first, the same judgement call the `07_BUILD_PLAN.md` "standing rule 3"
cases needed earlier this session. Not rewritten here — sized for whoever does the `CLAUDE.md`
source-code rewrite next: 59 mechanical, 21 needing individual judgement, 2 exempt.

**c. The known-failure baseline, restated so it does not move unnamed.** Two floors, not one,
found and named together for the first time this session — previously real but never written down
together as an expected result:

- **Floor A — pre-existing CI-gate drift, unchanged by this session's own work, confirmed via
  `git stash` A/B against the pre-session commit.** 2 failing tests: `test_route_coverage_check.py
  ::test_no_new_drift_beyond_the_allowlist` (6 routes registered with no matching documentation or
  allowlist entry) and `test_test_file_coverage_check.py::test_no_new_drift_beyond_the_allowlist`
  (`test_phase8_exit_criterion_end_to_end.py` wired into neither the `test` job's ignore list nor
  a live-service job) — the latter already disclosed earlier in `07_BUILD_PLAN.md`, the former not
  previously named as a standing floor anywhere.
- **Floor B — the local model backend unreachable, newly named.** 7 failing tests (4
  `tests/conformance/model_port`, `tests/golden/test_golden_set.py`,
  `tests/scenarios/test_phase6_extraction_and_resolution.py`,
  `tests/scenarios/test_witness_statement_extraction.py`), confirmed via `compose-litellm-1`'s own
  logs (`litellm.APIConnectionError: Cannot connect to host ollama:11434`) and `compose-ollama-1`'s
  own logs (`dial tcp: lookup registry.ollama.ai ... server misbehaving` — this sandbox has no
  route to the public internet, so Ollama cannot pull its model even when started). `DEMO_GUIDE.md`
  §0 already discloses Ollama/LiteLLM/speaches are not required for either demo scenario; this is
  the same fact restated as a test-suite floor, not a new constraint.
- **The full baseline: 9 known-failing tests** (`tests/` run whole) **when Ollama is unreachable,
  2 when it is not.** A run reporting more than this, in either state, is real drift; a run
  reporting fewer without either floor being fixed is a measurement taken wrong, not progress.

### B12 — CLAUDE.md rule 15's second clause, and the injection-shape audit it demands

**Rule 15 gained a second paragraph**, from the `licence_check.mjs` finding: an injection any
default-deny fallthrough would have caught proves nothing about the specific branch under test.
The planted violation must take the shape the code under test actually emits or receives at its
own real call site — for `licence_check.mjs` that was `main()`'s own `licenses.join(" AND ")`
dual-licence string, not a bare `"GPL-3.0"`. Full text in `CLAUDE.md` rule 15.

**Applied as an audit to all 9 gates' own red-then-green tests — one line each, real-shape or
hand-written:**

| Gate | Injection shape | Real call-site shape? |
| --- | --- | --- |
| `demo-guide-check` | Real `DEMO_GUIDE.md` text + real `DEMO_REGISTRY` with one fabricated entry appended | Yes — identical to `main()`'s own inputs |
| `domain-model-coverage-check` | Synthetic doc string + a `(name, bases)` tuple, passed straight to `find_undocumented` | Yes — `main()` calls `find_undocumented(doc_text, classes)` with the same two argument types; content is synthetic, the interface is real |
| `route-coverage-check` | Synthetic route list + empty doc-route set, passed straight to `find_undocumented` | Yes — same reasoning: `main()` calls `find_undocumented(live_routes, doc_routes)` |
| `authorized-query-check` | A fabricated Python source string passed to `check_source(path, text)` | Yes — `main()` calls the identical function on real files' own text |
| `test-file-coverage-check` | Synthetic file list + ignore/job-token dicts, passed straight to `find_orphaned` | Yes — `main()` calls `find_orphaned(test_files, test_job_ignored, live_job_tokens)` with the same shapes |
| `product-tree-link-check` | A real file written to `tmp_path` with a deliberate citation, read via `find_violations(doc_paths=...)` | Yes — the most end-to-end of the nine: real file I/O through the real function |
| `decision-log-publication-check` | A real `06_DECISIONS.md`-shaped file written to `tmp_path`, read via `find_violations(decisions_path=...)` | Yes — same shape as above |
| `schemas-check` | A real `pydantic.BaseModel` subclass with a genuinely different field, run through the real `generate()`/`diff_against_committed` pipeline | Yes — actual codegen, not a stand-in |
| `licence-check` (Python) | A fabricated `dist-info` directory read through the real `run_pip_licenses` path | Yes — reads actual package metadata the same way the real scanner does |
| `licence-check` (Node) | **Originally no** (bare `"GPL-3.0"`, caught by the audit itself, already fixed before this commit — rule 15's own worked example); now `"MIT AND GPL-3.0"`, `main()`'s own `licenses.join(" AND ")` shape | Yes, after the fix |

**No other test's injection was found provably vacuous.** The synthetic-content cases (domain-
model/route/test-file coverage) are not the same defect class as `licence_check.mjs`'s original
one: they pass fabricated *content* through the real function *signature* `main()` itself calls,
so the comparison logic under test is fully exercised even though the string wasn't scraped from
a real file. `licence_check.mjs`'s original version was different in kind — the fallthrough,
not the branch under test, was what actually caught the bare string, so the test passed for the
wrong reason. Nothing else in this audit matched that shape; nothing else was changed.

### B13 — Stage 3b executed: the census corrected again, the 60 mechanical rewrites done, the
6 ADR violations mostly rewritten, one reported not decided

**a. Every stale citation-count figure found, and disposed by whether it presents a number as
current or as a frozen historical record.** `07_BUILD_PLAN.md`'s Trigger A blast-radius section
("~1,150 citations, already tooled for") rewritten to point at `scripts/product_tree_link_check.py`
as the authoritative, live census rather than quote a fourth number due to go stale in turn — and,
found in the same passage, a second real defect: it credited `scripts/doc_citations_check.py` with
already running clean pre/post-move, but that script **does not exist**, checked directly. Both
fixed together. **Update, 25 September 2026:** `scripts/doc_citations_check.py` now exists, built
the same day under this exact name — this bullet is left otherwise unchanged as the record of what
B13 found at the time, not rewritten to match the later state. Grepped the whole of `docs/` for
`1,150`, `1,046`, `195`, `94`, `117`, `212`: every
other hit is either (i) ADR-031's own original accepted text (`06_DECISIONS.md` lines in its own
body) — left untouched, per this document's own standing instruction not to edit an accepted ADR's
own words, or (ii) this document's own later addenda (§B2's correction paragraph, §B9's citation
count) — given a short pointer to §B10's corrected figure rather than a fourth restated number.
None referred to `195`/`94`/`117`/`212` outside material already superseded in §B10/§B11 above.

**b/c. The 83 `CLAUDE.md` source-code citations, re-enumerated — the split moved, the same class
of bug §B10 already found.** The first pass (60 rule-numbered, 21 not, 2 exempt) undercounted the
rule-numbered set the same way the original citation census did: a single-line grep missed
citations where the rule number wraps to the next line (`` `CLAUDE.md` rule\n2 `` split across a
comment's own line break). A two-line-window structural check found **5 more** — the real split is
**65 rule-numbered, 15 not, 2 exempt** (65 + 15 + 2 = 82, plus the one new citation this session's
own `test_statelessness.py` work added = 83 counted before the rewrite). All 65 rewritten: state
the rule's substance, drop the reference, the same method already proven on `07_BUILD_PLAN.md`.
`packages/schemas/generated/ListNodesPage.ts` regenerated, not hand-edited. `product-tree-link-
check` before/after: **72 / 72, unchanged** — expected, since that gate scans only the Apache-
scoped *documents*, not source code; this rewrite's own population was never in its scope. Full
suite run before and after this rewrite (see this change's own commit for the count).

**The 15 non-numbered citations, tabled rather than rewritten, grouped by what they cite:**

| File:line | Text | Points at | One-line proposal |
| --- | --- | --- | --- |
| `packages/schemas/generate_ts.py:3` | "Pydantic is the source of truth (``docs/CLAUDE.md`` conventions)" | §"Conventions" section | Drop the citation; the sentence already states the fact standalone |
| `services/resolve/conflicts.py:11` | "flagged as such per `CLAUDE.md`'s "before you write code" rule" | §"Before you write code" section heading | "flagged as such rather than folded in as if the spec already said so" — drop the section name |
| `services/api/alerts.py:55` | "(`CLAUDE.md`: "No `osprey` CLI yet")" | §Conventions, quoted | "(this codebase has no migration tooling yet)" — the quote is redundant with the sentence's own words |
| `services/api/assessments.py:42` | "`CLAUDE.md`'s own "don't design for hypothetical future requirements" rule" | A "Doing tasks" bullet, not a numbered rule | "exactly the kind of unscoped, speculative expansion this codebase avoids" |
| `apps/workspace/src/canvas/GlassCanvas.tsx:618` | "(CLAUDE.md's own session priority)" | Unclear — no "session priority" concept found in `CLAUDE.md`'s current text | Needs the owner: either name what this actually refers to, or it is drift and should be cut |
| `apps/workspace/src/export/pngMark.ts:82` | "(`CLAUDE.md`'s own "fail loudly, never dropped silently" posture)" | No literal match in `CLAUDE.md`'s current text — closest is rule 2's "never truncate silently" | Likely drift from rule 2, paraphrased loosely; restate as "the same never-silently-drop posture rule 2 states for truncation" or confirm with the owner |
| `scripts/seed_hmp_fixture.py:5`, `scripts/verify_map.py:9`, `scripts/register_tier4_provider.py:3`, `scripts/build_local_basemap.py:8`, `scripts/build_local_basemap.py:281`, `scripts/seed_fixture_corp.py:6`, `scripts/osprey_bundle.py:5` | "No `osprey` CLI yet (`CLAUDE.md`'s own Conventions)" — 7 near-identical instances | §Conventions' "No `osprey` CLI yet" bullet | Mechanical once agreed: "No `osprey` CLI yet" stands alone, drop the parenthetical every time — same shape as the other 65, held back only because the fix is identical prose repeated 7 times, worth a single agreed pattern rather than 7 separate judgement calls |
| `scripts/domain_model_coverage_check.py:51` | "the one Apache-scoped document CLAUDE.md's own routing table assigns to…" | The file-routing table near the top of `CLAUDE.md` | "the one Apache-scoped document this build's own routing convention assigns to…" |
| `tests/scenarios/fixtures/fixture_corp.py:16` | '...around one," `CLAUDE.md`) does not extend to' | §Conventions' CLI-shape convention, quoted | Drop the trailing `CLAUDE.md` attribution; the quote already carries the content |

**Kind breakdown**: 9 are the same "No `osprey` CLI yet" convention repeated (mechanical once a
single pattern is agreed, held back only for that reason); 3 point at a real section (Conventions,
"Before you write code," the routing table) and can be restated without the pointer; 2
(`GlassCanvas.tsx`, `pngMark.ts`) are paraphrases that do not match `CLAUDE.md`'s current text
exactly and need the owner's own confirmation of what they meant, not a rewrite guessed at; 1
(`assessments.py`) paraphrases a "Doing tasks" bullet correctly and can be restated directly.
**This comes back to the owner as a method question, per the instruction — not rewritten here.**

**d. The 6 ADR cross-reference violations: 5 of 6 rewritten, 1 reported rather than decided.**
`028→022` (×2), `032→019`, `035→034` (×5), `035→042`, `037→042` — all ten instances rewritten:
state the constraint, drop the process-ADR pointer, exactly the disposition §B11 already gave each.
`035→026`: **4 of 5 instances rewritten** (the technical consequence — "shaped, not verbatim" —
restated directly, dropping the citation). **The fifth is reported, not decided**: "**One
clarification, checked against ADR-026 rather than assumed:** ADR-026's own title states it
plainly — …" — this sentence's own point *is* the verification act itself, checking a specific
document rather than assuming; removing the citation would remove a reader's ability to confirm
that check was real, not merely restate a fact it produced. Whether that verification act needs
its own citation to stand as a check, or can be restated without one, is a judgement call left to
the owner. **`tests/fixtures/decision_log_publication_allowlist.txt` reduced from 6 entries to 1**
(only `035	026` remains) — not empty and deleted, because one real violation remains by design,
not by oversight. `make decision-log-publication-check`: green, "1 known (allowlisted), 0 new."

---

## ADR-035 — Demo distribution classes (`shipped`/`internal`), fail-closed and enforced at packaging time; Fixture Corp (R24) is the shippable demo; Enron and VAST stay internal, one of them narrower than requested

**Status.** Accepted, 21 September 2026, with one item this record declines to accept as written
(C3, below) rather than implement silently against a standing rule.

**The problem.** Every demo case this build has named or built — Scenario A (HMP fixture, built),
the Ingest Studio (CDR fixture, built), Scenario C / "Fixture Corp" (Enron-shaped, not built), a
generic reference to "the Enron corpus," and the VAST Challenge datasets — has been tracked
informally, in prose, in `DEMO_GUIDE.md`. Nothing today enforces, mechanically, which of these may
leave this repository in a built artefact and which may not; `DEMO_GUIDE.md` §6 already relies on
prose ("No real intelligence data anywhere, ever") to keep the real Enron corpus out, with nothing
that would catch a packaging step that copied it in by accident.

### C1 — Demo distribution classes

Every demo carries a manifest declaring a `distribution` field: `shipped` (included in artefacts
given to customers and testers) or `internal` (never included in any artefact leaving this
project).

**The registry fails closed.** A manifest with a missing, empty, misspelled or unrecognised
`distribution` value is treated as `internal`. **The test that proves this:**
`tests/demo_registry/test_fail_closed.py::test_a_manifest_with_no_distribution_field_is_excluded_
from_a_shipped_build` — asserts, for a manifest literally lacking the field (not one explicitly set
to `"internal"`), that the demo it describes does not appear in a shipped-build listing. A second
case in the same file, `test_an_unrecognised_distribution_value_is_treated_as_internal`, covers the
misspelled/unrecognised half separately, since "missing" and "wrong" are different code paths
(a missing key vs. a value that fails an enum check) and each needs its own proof.

**Exclusion happens at packaging time, by omitting the demo's files from the artefact — not a
runtime flag.** A build that contains an internal demo's data and disables it with configuration
has shipped that data; C2 below is the packaging-time gate this requires.

**Datasets for internal demos are never committed.** They are provisioned to a gitignored directory
located by environment variable (`OSPREYFLOW_INTERNAL_DEMO_DATA_DIR`, no default — absence is
"nothing provisioned," never a fallback path that might silently point somewhere real), referenced
by the manifest by filename rather than contained in it. **Gitignore entry added in this session:**

```
# Internal-only demo datasets (spec/06_DECISIONS.md ADR-035, C1) — never committed, provisioned to
# OSPREYFLOW_INTERNAL_DEMO_DATA_DIR at runtime, referenced by filename from a demo's own manifest.
/demo-data/
```

(`/demo-data/` is this session's own choice of the conventional default `OSPREYFLOW_INTERNAL_DEMO_
DATA_DIR` points at when unset in local dev — anchored at the repository root, not matched at every
directory level, since nothing about this data is a build artefact like `.DS_Store` that can appear
anywhere.)

**The Glass renders a demo whose dataset is not provisioned as unavailable, with a clear reason —
never an error, never a leaked stack trace.** Design note, not built: the natural place is the same
demo-selection surface `DEMO_GUIDE.md` §1's table already documents in prose; a demo whose manifest
resolves to `internal` and whose `OSPREYFLOW_INTERNAL_DEMO_DATA_DIR` file is absent renders a
disabled entry with the reason "dataset not provisioned," the same shape `services/api/config.py`'s
own fail-fast-on-missing-`OIDC_JWKS_URL` already establishes for "tell the operator exactly what is
missing," not a 500 from a route that assumed the file would be there.

**`make demo-manifest` prints each demo and its distribution class** — this session's chosen name,
matching the `make licence-check`/`make schemas-check` naming convention — so what will ship is
inspectable before shipping rather than after.

**Not built in this session — design only, per this ADR, owned by Phase 8.** No demo-manifest
schema, registry, packaging hook or Glass unavailable-state component exists anywhere in this
repository today (checked: `git grep -li "distribution.*class\|demo.*manifest"` over `packages/`,
`services/`, `apps/` returns nothing), and Phase 8 is the first phase that builds any packaging
pipeline at all ("the browser harness and its packaging pipeline are
Phase 8's own outcome, not built until then"). Building C1's registry ahead of Phase 8's own
packaging work would have nothing to attach to. `07_BUILD_PLAN.md`'s Phase 8 outcome bullets are
amended below to own this design.

### C2 — Packaging gate

An assertion on the packaging step, failing the build, that no internal demo's id, directory path
or dataset filename appears anywhere in the built artefact — **including inside image layers**, not
merely the running filesystem: if a packaging step copies the repository root, `/demo-data/`'s own
gitignore exclusion is irrelevant to what a `docker build` context includes unless the `Dockerfile`
also excludes it (`.dockerignore`), the same "check the build context, not just the running
container" finding already made for the private build tree.

**The test, named prospectively (not built — no packaging step exists to test yet):**
`tests/packaging/test_internal_demo_exclusion.py::test_reclassifying_an_internal_demo_as_shipped_
fails_if_its_data_remains` and a sibling,
`test_removing_the_exclusion_step_itself_fails_the_gate` — both required, per this session's own
"name the test that would fail" discipline (rule 12): a gate that only ever proves the *current*
correct state passes is not proof it would catch either the reclassification mistake or its own
removal.

**Not completed in this session; recorded, per this item's own explicit instruction, as required
work owned by Trigger A (Phase 8's own close), and no artefact may be given to any
third party until it exists.**

**Addendum, 24 September 2026 — the `.dockerignore` this item names now exists; the packaging gate
it serves still does not.** When this section was written there was no `.dockerignore` anywhere in
the repository, so the mechanism C2 names by name had nothing behind it. There is one now, at the
repository root, with `tests/test_dockerignore.py` proving it non-vacuously: two cases delete a
single line each and assert the path it names stops being excluded — the "prove it can fail"
discipline applied to the one trap a `.dockerignore` actually has, which is the inverse of a
default-deny fallthrough. Nothing is excluded unless a line says so, so the risk is not a violation
slipping through a gap; it is crediting a specific line for an exclusion some broader pattern was
already making. It excludes the private build tree via `scripts/product_tree_link_check.py`'s own
`PRIVATE_TREE_MARKERS`, imported rather than restated; `config/real_data_exceptions.yaml`; `data/`,
`backups/` and `demo-data/`; and the tooling, test and development trees.

**Two things this addendum deliberately does not claim.** First, **it fixes no live leak, because
there is none** — checked directly, not assumed: the only two Dockerfiles in this repository
(`services/api`, `services/ingest`) copy selective directories (`pyproject.toml`, `uv.lock`,
`packages`, `services`), never `COPY . .`, so nothing under `docs/`, `.claude/` or `config/` reaches
an image layer today. What the file does do today is keep the whole repository from being uploaded
to the daemon as build context on every build; what it is *for* is the images that do not exist yet
— the harness's own above all (`05_DEPLOYMENT.md` §2/§3's `ghcr.io/ospreyflow/harness:latest`),
which by construction runs against a mounted `/workspace` and is the likeliest future candidate for
a broad copy. A defence written before the image that needs it. Second, **it is not C2's gate.** C2
requires an assertion *on the packaging step*, failing the build, that no internal demo's id, path
or dataset filename appears in the artefact including inside image layers, with the two named tests
(`test_reclassifying_an_internal_demo_as_shipped_fails_if_its_data_remains`,
`test_removing_the_exclusion_step_itself_fails_the_gate`). No packaging step exists to attach either
to. `.dockerignore` is the precondition that makes such a gate enforceable, not a substitute for it,
and C2's ownership above is unchanged. The harness/packaging stage's own packaging sub-stage
(`07_BUILD_PLAN.md`) carries both, alongside a third exclusion no record had previously named:
`config/real_data_exceptions.yaml`, gitignored and therefore exactly the file most likely to be
present, uncommitted and unnoticed, on the one machine that builds an owner-run demonstration.

**One hazard, recorded when the file was created and closed the same day.** Excluding `docs/`
wholesale also excludes `spec/design/tokens.css`, and that file is product source rather than prose
— thirteen real consumers, twelve TypeScript `import`s including `apps/workspace/src/main.tsx`, the
Glass's own entry point, plus one `readFileSync` — so a build with the import unresolved fails
outright. **Closed by an explicit negation, `!spec/design/tokens.css`, added 24 September 2026 on the
owner's instruction**, with `tests/test_dockerignore.py` asserting three things rather than one: that
the file is included; that everything else under `docs/` stays excluded, its own sibling
`OspreyFlow_Brand_Foundations.html` included in that list; and that removing the negation line
excludes it again, so the inclusion is attributable to that line. **Temporary by design** — once the
restructure moves `tokens.css` into the product tree, the negation has nothing to re-include and
should be deleted with the `docs/` path it rescues, not left matching nothing.

**One semantic caveat, verified rather than assumed.** Git itself would not honour this negation
("it is not possible to re-include a file if a parent directory of that file is excluded"). Docker's
own matcher does honour `!` exceptions, and `pathspec`'s gitignore matcher — what the test uses —
agrees with Docker here rather than with git; checked directly before the line was added. A real
`docker build` remains the final authority if the two ever diverge.

### C3 — The Enron email corpus, narrower than requested

**Research and reasoning, recorded in full because it is useful regardless of the disposition
below:**

- No licence or terms are stated by the CMU maintainer — only an informal request to be sensitive
  to the privacy of those involved. Absence of a stated restriction is not a grant of rights.
- Documented redaction history: messages have been removed at the request of affected employees, so
  the corpus is mutable, and a local copy may contain material since withdrawn elsewhere.
- UK GDPR applies to processing regardless of repository visibility — repository privacy controls
  who can *read* the repository; it is not a lawful basis and not a packaging control.
- Size: ~1.7GB, above GitHub's per-file limits and unsuitable for git regardless of the above.

**Where this record departs from what was asked, and why, rather than implementing it silently.**
The request was: distribution class `internal`, permitting "local development, scale and realism
testing, and demos run by the owner for the owner's own purposes." Standing rule 9 —
binding on every session, not merely an accepted ADR — is unqualified: "No real intelligence data
anywhere, ever." Standing rule 3, which `DEMO_GUIDE.md` §6 already cites
by name against using the real Enron corpus at all, is scoped precisely: "No real intelligence data
in the repository, in CI, **or in a demo**." A demo "run by the owner for the owner's own purposes"
is still, in the rule's own words, a demo. This build's own standing discipline is that an accepted
decision record believed wrong gets said so and stopped on, not silently implemented around — the
same discipline applies with more force to a standing rule than to an ADR. **This record does not
amend standing rule 3 or standing rule 9, and does not grant the "demos run by the owner"
permission as requested.**

**What this record originally accepted, before the amendment below, because it did not touch
either rule's own explicit scope:** distribution class `internal`, permitted for **local
development and scale/realism testing only** — neither the repository, CI, nor a demo of any
kind, the three channels standing rule 3 actually names. The corpus could sit on the owner's own
machine, outside `/demo-data/` and outside git entirely (it is 1.7GB and ungitignorable-by-size
regardless), used to stress-test the platform at a scale Fixture Corp does not reach, and never
rendered to any audience, the owner included, as a "demo."

**Open item for the owner — decided, 23 September 2026, by the owner directly, not inferred.**
Standing rule 3 and standing rule 9 are amended: both now admit a dataset explicitly named in
the local, never-committed real-data exceptions list (`scripts/real_data_exceptions.py` —
`config/real_data_exceptions.yaml`, gitignored), for local development, scale/realism testing, or
an owner-run demonstration on the owner's own secured device — never committed, never in CI, never
distributed to any attendee. **This record's own disposition above is superseded to match**: the
Enron email corpus may now also be used for an owner-run demonstration, on the same terms, once
the owner adds it to that list themselves — the repository, CI, and distribution to any attendee
remain absolutely excluded, unchanged. No other real dataset is admitted by this decision; each
needs its own entry and, for anything beyond Enron, its own record. **"Revisit if" — fired**: the
condition this open item existed to track (an explicit owner decision on the amendment) has
occurred; this paragraph is that record, not a placeholder awaiting one. **Separately, and
regardless of the amendment:** whether even development-only use requires a documented lawful
basis and retention period under UK GDPR is recorded as requiring legal advice before alpha, per
the original request — **that requirement now also covers demonstration use**, added by this same
amendment, not narrower than the development-only case it already applied to.

### C4 — VAST Challenge datasets, and the same conflict in miniature

Distribution class `internal`, for the **generated, VAST-shaped fixture** already designed as
shaped, not verbatim — no licence or terms found on any host checked (the moved benchmark repository,
the GitHub organisation, PNNL Datahub, OSTI, or the GitHub repositories; none carries a `LICENSE`
file), and publication for challenge participation reads as a reasonable implied licence to
participate, a thin one for redistribution. No personal data, so no GDPR question — a materially
different risk profile from Enron.

**One clarification, checked against ADR-026 rather than assumed:** ADR-026's own title states it
plainly — "the VAST Challenge datasets are admitted shaped, not verbatim; standing rule 3 is not
amended." If "distribution class `internal`" is read as license to keep the *actual published VAST
files* on this project's own infrastructure for any purpose, that already conflicts with the
datasets-admitted-shaped-not-verbatim holding, the same shape as C3's conflict above, just already resolved rather than newly
found. Read correctly, C4's `internal` class attaches to the *generated fixture's own build
artefacts* (intermediate files a seeded generator might produce before the final fixture is
committed as `shipped` test data) — not to a cached copy of VAST's own files, which the
datasets-admitted-shaped-not-verbatim rule already declines to admit into this project at all, in
any distribution class.

### C5 — Fixture Corp (R24) — distribution class `shipped`

Synthetic and generated — Enron-*shaped*, not Enron-derived, per `DEMO_GUIDE.md` §6's own framing.
Candidate generators, both Apache-2.0: AMLSim and gen-fraud-graph. Generated output is owned
outright and carries no third-party licence — the one demo dataset this record can actually put in
front of a customer.

Fixture Corp is the demo shown to customers and the one an analyst review runs against, being the
only one shippable and the only one whose content is arrangeable deterministically. It must
exercise, at minimum:

- entity resolution at τ 0.99, 0.95 and 0.80 producing visibly different projections;
- community structure the selected algorithm (Louvain, per `06_DECISIONS.md` ADR-029) actually
  finds;
- path lengths across the pathfinder's own supported range (`max_hops<=8`, per this session's own
  Part A);
- an access-control boundary where a hidden hop lengthens the path rather than removing it — the
  same property `test_unauthorised_path_length_matches_a_graph_without_the_hidden_hop`
  (`tests/conformance/graph_port/test_suite.py`) already proves for the pathfinder generally, here
  demonstrated against fixture data an analyst can actually see rendered.

**R24 has been the only backlog item with no owning phase. Owning phase: Phase 8.** `07_BUILD_PLAN.
md`'s Phase 8 outcome bullets are amended below to claim it, alongside C1's demo-manifest registry
it is the first real `shipped`-class citizen of.

**Addendum, 22 September 2026 — stage confirmed, not only phase.** Phase 8's own stage breakdown
gives Fixture Corp sub-stage **4a**, ahead of the assessment/export build it would otherwise be
mistaken for a closing-pass afterthought of (`07_BUILD_PLAN.md`'s own Stage 4 entry has the full
reasoning: it is the demo an analyst review runs against — this build's own
only external signal before alpha). This addendum exists so a reader of
this record alone, not only of the build plan, finds the placement rather than just the phase.

**Addendum, 22 September 2026 — built, and neither candidate generator named above turned out to
be usable.** Checked directly once Stage 4a actually started, not assumed from this record's own
text: neither AMLSim (a Java/Python source checkout with its own build toolchain, not a package)
nor `gen-fraud-graph` (no PyPI distribution) is pip-installable. Built instead — and disclosed as
such in its own module docstring — an original, 100%-owned generator implementing the same
fan-in/fan-out fraud-ring typology AMLSim itself models: "AMLSim-*shaped*, not AMLSim-generated,"
the same distinction this record's own "Enron-*shaped*, not Enron-derived" framing already draws
for the HMP fixture, above. Still synthetic, still no third-party licence, still no personal data —
this record's own governing constraints are unaffected; only the named candidate tooling was not
actually available. `07_BUILD_PLAN.md`'s own Stage 4a entry has the full build record and its four
proven properties.

**Addendum, 26 September 2026 — Fixture Corp's entities now carry a searchable identifier, and
§C5's five resolution scores were re-measured either side of the change. Recorded under owner
ruling R4 of that date, which authorises this edit.**

The finding that prompted it: Fixture Corp could not be demonstrated in the Glass at all. The
working set has one entry point, the search box; `services/api/search.py`'s own scope note states
it is "exact identifier match against the graph, not full text"; `search_nodes` matches only the
identifier fields this ontology declares; and this fixture set none of them. Measured directly
against a real seeded store: **0 of its 65 `Person` nodes carried any of `nino`/`pnc_id`/
`prison_number`, and 0 of its 3 `Organisation` nodes carried `org_ref`** — against 400 of 400 for
the HMP fixture, which is why that one has always been demonstrable and this one never was. Three
of the four interactive checks this section asks for (`explain` on a merged cluster, the
pathfinder, comparing path lengths) were therefore impossible rather than merely undone. The
visual query builder is not a second entry point: it finds them by entity type but, per ADR-032,
deliberately reports the matched set and its count rather than drawing anything.

R4 chose to give the fixture identifiers rather than reopen ADR-032. Every `Person` now carries a
synthetic `nino` and every `Organisation` an `org_ref`, both derived deterministically from the
node id with SHA-256 (not `hash()`, which is salted per process) so a presenter can type a value
from `DEMO_GUIDE.md` and a live spec can assert on it. **`QQ` is load-bearing, not decorative**:
HMRC never issues a National Insurance number beginning with Q, so no value the generator can
produce is capable of colliding with a real person's — the fixture stays synthetic *by
construction*, which is what standing rule 3 and standing rule 9 are about, rather than by
anyone remembering to keep it so. `org_ref` takes a `FIXTURE-` prefix for the same reason.

**The re-measurement, which R4 required rather than assumed.** The five scores were measured with
the identical harness immediately before and immediately after the change — the same
`resolve_entity_type(nodes, PERSON_TYPE)` call `test_fixture_corp_entity_resolution_projections_
differ_by_threshold` uses, not a reimplementation — so that a difference in method could not be
mistaken for a movement in the fixture:

| Pair | Recorded (when built) | Measured 26 Sep, before | Measured 26 Sep, after |
| --- | --- | --- | --- |
| `identical` | 0.999991 | 0.9999906877922944 | 0.9999906877922944 |
| `close_given_name` | 0.981285 | 0.9812853391529271 | 0.9812853391529271 |
| `close_surname_and_given` | 0.867624 | 0.8676242801350367 | 0.8676242801350367 |
| `shared_surname_different_person` | 0.0001 | 9.999999999999999e-05 | 9.999999999999999e-05 |
| `identical_non_latin_script` | 0.999991 | 0.9999906877922944 | 0.9999906877922944 |

**Bit-for-bit identical, not merely equal to the fourth decimal** R4's stop condition named — and
the before-column also reproduces the originally recorded values exactly, so the harness itself is
sound. This is the expected result rather than a lucky one: `Person`'s own `resolution` block
blocks on `soundex(family_name)`/`year(date_of_birth)` and compares
`jaro_winkler(family_name)`/`levenshtein(given_names)`/`exact(date_of_birth)`, naming none of the
identifiers. The point of measuring was that "should not affect it" and "does not affect it" are
different claims, and only one of them had evidence.

`tests/scenarios/test_fixture_corp_shape.py`'s own
`test_every_fixture_corp_entity_carries_the_identifier_search_matches_on` is the test that fails
if this regresses — shown red first against the pre-R4 fixture, and separately against a
non-deterministic generator, since either fault alone would break the demo.

### C6 — IBM AML-Data, conditional

If ever used as data rather than AMLSim as a generator: CDLA-Sharing-1.0 carries a share-alike
obligation on published modifications. It does not reach the code — a data licence, not a code one
— but complicates the single-licence (Apache 2.0) story this repository otherwise tells cleanly.
Recorded as a constraint on a path not currently taken, not a decision to avoid it outright.

### C7 — `make licence-check`'s actual coverage, verified rather than assumed

**Checked directly, both halves.** `scripts/licence_check.py` (Python) runs `pip-licenses` against
the active Python environment and checks each reported package licence string against an allowlist
(`spec/00_ARCHITECTURE.md` §7). `scripts/licence_check.mjs` (Node, `package.json`'s own `licence-
check` script) does the identical check via `license-checker` against `node_modules`. **Neither leg
inspects a data file's own embedded or accompanying licence** — a fixture carrying its own data
licence (C6's CDLA-Sharing-1.0 case, or any future dataset with terms of its own) passes both
scripts unexamined, because neither script's own scope extends past installed-package metadata.

**This is the fourth recorded instance of a gate verifying less than its name implies** — after
`keyboard.spec.ts`'s own no-auto-discovery finding, the fake-backed access-control tests
(`07_BUILD_PLAN.md`'s "Gaps with no owning phase," four instances), and the `axe-core`
`onMouseDown`-only showcase finding (same list). The pattern each of those four entries already
names — found by someone going looking, never by the gate itself failing — holds again here.

**Extending `licence-check` to data files is real, additional work, not a quick fix to either
existing script** (neither `pip-licenses` nor `license-checker` has any notion of a non-package data
file at all — this would need its own small scanner, checking for a `LICENSE`/`NOTICE`/manifest-
declared licence alongside any fixture directory). **Recorded as work with an owning phase: Phase
8**, alongside C1's registry and C5's Fixture Corp, since a shipped fixture's own data licence is
exactly the class of thing C1's `make demo-manifest` output should also be able to report.

### C8 — `DEMO_GUIDE.md`

Amended in this session (see the file itself) with a new provisioning section describing how
internal demo datasets are obtained and placed (`OSPREYFLOW_INTERNAL_DEMO_DATA_DIR`, by reference
from a manifest, never committed) without containing or linking the datasets themselves — the guide
stays in the Apache tree and must describe the mechanism, not the content. The
existing demo table is amended to state each entry's distribution class plainly.

**Cost.** One gitignore entry (done). Two ADR sections (C3, C4) that decline part of what was asked
rather than implement it against a standing rule, with the amendment they would need named as an
open item for the owner. Everything else — the manifest schema, the registry, the packaging gate,
the Glass unavailable-state rendering, `make demo-manifest`, the extended licence-check, and Fixture
Corp itself — is design and ownership only in this session; `07_BUILD_PLAN.md`'s Phase 8 outcome
bullets are amended to claim all of it, so none of it is a second orphaned backlog item the way R24
already was once.

**Revisit if.** The owner amends standing rule 3/standing rule 9 to add an owner-only-demo
exception (C3's own open item) — at which point this record's own `internal` scope for Enron widens
to match, by an edit to this record, not a new ADR.

---

## ADR-036 — Saved-pattern monitor principal identity: accepted as proposed

**Status.** Accepted, 21 September 2026. Accepted exactly as proposed — the saving-analyst
principal, resolved fresh at each evaluation, stop rather than degrade on revocation — with one
condition attached at acceptance, not a change to the reasoning: this record was **contingent on
pattern persistence existing**, since the owning-principal reference this ADR requires had nowhere
to live until a saved pattern was itself a persisted object. **Contingency satisfied, same day**:
Part 3 of this session built that persistence (`services/api/pattern_store.py`'s `PatternStore`,
`SavedPattern.owner_id` in `packages/schemas/domain.py`) — save/load/list/version, no sharing. The
owning-principal reference this ADR needs is `SavedPattern.owner_id`, set to `principal.id` at
save time. This ADR is now buildable end to end; the monitor evaluator itself (reading that field,
applying it per the two halves below) is Stage 6's own still-unbuilt work.

**The gap, as the spec states it.** `02_GLASS_FRONTEND.md` §3.3: "Saved-pattern monitors. A saved
visual query run on a schedule against new data. Matches raise alerts with the same shape as
hotlist alerts." No principal is named. `07_BUILD_PLAN.md`'s Phase 7 outcome bullet ("Hotlists,
saved-pattern monitors, alert inbox with rule and evidence display") names none either. The only
principal-identity precedent anywhere in this codebase for scheduled, out-of-request evaluation is
ADR-025's service principal for the corpus-wide resolution trigger.

**Why ADR-025's own precedent does not transfer, quoted rather than assumed.** ADR-025: "The job
runs under a deployment-level service principal, not the ingesting analyst's own — resolution is
corpus-wide and cross-investigation, and the analyst who happened to trigger a load has no special
claim over every resulting `SAME_AS` edge." That reasoning is specific to a job with no single
owner: resolution runs against the whole corpus on every entity type that declares a
`resolution:` block, on behalf of no one analyst in particular. A saved-pattern monitor is the
opposite shape — one analyst's own saved query, evaluated on a schedule on their behalf, against
data they asked to be told about. ADR-025's own justification argues against reusing its own
pattern here: where resolution's premise is "no analyst has special claim," a monitor's premise is
"this analyst, and only this analyst, has a claim." Evaluating a monitor as a broader service
principal does not merely fail to fit that premise — it inverts it, and produces exactly the leak
the task naming this gap described: the analyst learns of matches against data they cannot see
themselves.

**Proposed answer, first half.** A saved-pattern monitor evaluates as the saving analyst's own
principal, never a service principal. Its query goes through `GraphPort`'s ordinary
access-filtered path exactly as if the analyst issued it themselves at the moment of evaluation —
no new privileged code path, no elevated identity, nothing standing rule 2/standing rule 3 does
not already require of every other read.

**Proposed answer, second half, equally binding.** Access is resolved fresh at each evaluation, not
captured or cached at save time. A monitor that carries "access as it was when saved" is a durable
grant outliving whatever permission produced it — the same shape of defect standing rule 3 exists
to prevent generally, here specific to a stored, re-run query rather than a stored result. What
happens when the saving principal is no longer valid at evaluation time (account disabled,
credential revoked, an `org_unit`/handling reassignment that changes what the saved principal
reference can resolve to)? **Proposed: the monitor stops.** It is not evaluated with degraded or
fallback access, and it is not silently kept running against a stale snapshot of the access that
existed when it was saved. A stopped monitor is surfaced as stopped somewhere the analyst or
another owner can see it (the monitor list, or the alert inbox) rather than silently producing
nothing forever with no visible state change.

**The test that would retire this gap.**
- `test_monitor_never_fires_on_a_match_the_saving_analyst_cannot_see` — save a pattern as
  analyst A under a narrow handling scheme; create a node/edge that matches the pattern but is
  visible only to a broader principal B; run the monitor's evaluation; assert no alert is
  produced and no evidence of the match is observable to A.
- `test_monitor_stops_evaluating_once_the_saving_principal_is_revoked` — save a pattern as
  analyst A; revoke or invalidate A's principal; trigger an evaluation (including against data
  that would otherwise match and that A could previously see); assert no alert fires and the
  monitor's own state reflects "stopped," not silently active.

**Cost.** Needs the saved-pattern persistence path — recorded as an unbuilt gap in ADR-032's own
known-gaps note ("Patterns are saveable, shareable and versioned" is unbuilt) at the time this ADR
was drafted, closed for the save/version/owner third by Part 3 of this same session — to carry an
owning-principal reference, plus a principal-validity check at evaluation time. The persistence
path is now real; the principal-validity check at evaluation time is not, since no monitor
evaluator exists yet (ADR-037 is its own separate, still-unbuilt mechanism).

**Revisit if.** Monitors are ever generalised to be shared or team-owned rather than
analyst-owned — the "shareable" third of ADR-032's own still-unbuilt promise — at which point this
record's single-owner-principal model needs re-examining alongside whatever sharing model is
chosen, not assumed to survive it unchanged.

**Amendment, Phase 7 Stage 6c — this record's own "resolved fresh, not captured" text is narrower
in the built system than as written, and that gap is amended here rather than left as a quietly
unsatisfied ADR.** As accepted above: "Access is resolved fresh at each evaluation, not captured or
cached at save time." Built: access is resolved fresh only when the saving analyst is the
*requester whose own action triggered the evaluation* — a hotlist/monitor owned by anyone else is
skipped for that trigger, not evaluated against stale or cached access, but also not evaluated at
all. An accepted ADR the code does not satisfy is worse than a narrower honest one; this amendment
states what is actually true rather than leaving the original text standing unqualified.

**Why, quoted rather than asserted.** `services/api/auth.py`'s `PrincipalResolver.resolve()` is the
one place a `Principal` is ever constructed in this codebase, and it builds every field —
`clearance`, `org_unit`, `receivable_handling_codes` — from the bearer token's own JWT claims,
verified against a JWKS URL:

```python
def resolve(self, token: str) -> Principal:
    signing_key = self._jwk_client.get_signing_key_from_jwt(token)
    claims = jwt.decode(token, signing_key.key, ...)
    ...
```

There is no id-keyed lookup anywhere alongside it — no table, no directory, nothing that answers
"what is analyst B's current `Principal`" given only `owner_id` and no live token from B. A
scheduled or event-triggered evaluator acting on B's behalf, prompted by A's own action, has no
such token in flight (6b's own finding, restated here because this amendment is the point at which
it stops being a disclosed limitation of an unbuilt mechanism and starts being a disclosed
limitation of a built one). `services/api/evaluation.py`'s `principal_for_owner: Callable[[str],
Principal | None]` returning `None` is this amendment's own mechanism, not a new one: the same
"the monitor stops" behaviour this ADR already specifies for a revoked principal, now also the
behaviour for every owner who is not, in this moment, the one triggering the check.

**What the unamended version would require.** A principal directory — some service or store,
keyed by a stable analyst id, from which a current `Principal` (clearance, org_unit, handling
codes) can be constructed without a live session token. Nothing in this codebase provides one, and
none is planned before Phase 8's own harness work (the same phase already carrying the
Keycloak/identity-provider wiring this system has deferred throughout). Building a synchronous
approximation now (caching a principal from a prior request, say) would reintroduce exactly the
"durable grant outliving whatever permission produced it" failure shape this ADR's own second half
already rejects — narrower-but-honest was chosen over broader-but-wrong.

**Confirmed, not merely suspected, while attempting to wire the corpus-wide resolution trigger
(Phase 7 Stage 6c's own second carry-over): resolution has no live principal for *any* caller, not
only the cross-analyst case above.** `services/api/resolution_trigger.py`'s own `resolve_now`
docstring: "Always submits a job, never runs synchronously." `run_resolve_entity_type_job`'s own
fixed `JobWorker` dispatch signature carries no principal at all, for the automatic post-ingest
trigger or the manual "resolve now" route alike — both cross the identical job/worker boundary
before resolution ever executes, so even the same-analyst-owns-the-monitor case this amendment's
own narrowing otherwise permits cannot reach resolution's own producer today. Ingest and manual
assertion (`app.py`'s `run_studio_recipe`/`link_resolution_route`) both retain a live requester and
are wired; resolution is not, pinned by
`test_a_monitor_does_not_fire_on_a_match_created_by_resolution_with_no_new_ingest`
(`tests/services/api/test_evaluation.py`) rather than left unverified.

**Consequence for Scenario B, stated here and at the exit criterion itself
(`07_BUILD_PLAN.md`'s own Phase 7 outcome), not only in this record.** B12/B13/B14/B20 pass for the
walkthrough as `08_ACCEPTANCE_SCENARIOS.md` narrates it — one analyst, start to finish — because
that analyst is both the one who set the hotlist/monitor and the one whose later ingest triggers
it, so `owner_id == requester` holds. A hotlist or monitor firing from a *different* analyst's
later ingest — the operational case B13's own CoLP framing is modelled on ("a warrant seizure
logged by a unit other than the one that set the original hotlist entry") — does not fire under
this amendment, and does not silently fire wrong; it is skipped, observably (`Hotlist.status`/
`Monitor.status`, Stage 6c). Owning phase for the general case: **Phase 8**, alongside the
principal-directory dependency this amendment names. **Manifestation two of three of one
consolidated gap** — `07_BUILD_PLAN.md`'s own "Gaps with no owning phase" entry has the other two
(general background evaluation; resolution-triggered monitors) and the combined operational
consequence: as delivered, a monitor or hotlist fires only on its own owner's action.

**Revisit this amendment if.** A principal directory (or equivalent — a service-account credential
an evaluator can present on an owner's behalf, an identity-provider lookup endpoint) is built at
Phase 8 or later — at which point `principal_for_owner` gains a real implementation and this
amendment's own narrowing is lifted, restoring the original "resolved fresh at each evaluation" text
as literally true rather than true-for-one-case.

**Condition met, Phase 8 Stage 1, 22 September 2026 — for ingest and manual assertion, not yet for
corpus-wide resolution.** `06_DECISIONS.md` ADR-043 (OAuth2 Token Exchange) gives `principal_for_
owner` its real implementation; `test_a_hotlist_owned_by_one_analyst_fires_from_a_different_
analysts_own_ingest` (`tests/scenarios/test_phase7_stage6c_watch_routes.py`) proves the narrowing
this amendment describes is lifted for both of `run_studio_recipe`'s and `link_resolution_route`'s
own producers — "resolved fresh at each evaluation" is literally true for any owner, not only the
requester, on those two paths. **Not lifted for corpus-wide resolution — attempted the same day,
found blocked by a different, more precise reason than "no call site" now that one was actually
built, and now scoped outside v1 rather than left inside Phase 8's own backlog.** A real call site
was wired (`run_resolution_for_entity_type` calling `evaluate_monitors_for_entry`, threaded through
to job registration in `app.py`) and reverted, not kept: `JobWorker._process` commits the job's own
transaction only after the handler returns, so the evaluation call — running from inside the
handler — cannot see the very `SAME_AS` write it exists to alert on, confirmed empirically against
a real test build of the wiring, not inferred. ADR-037's own amendment has the full finding — the
`GraphPort` transaction-read shape is disqualified on correctness (a rolled-back job would alert on
a fact that never existed), not merely priced against; the complete fix is a durable-record
consumer, the shape this amendment's own change stream already describes, not a post-commit hook
alone (correct, but loses an evaluation if the process dies before running it). Checked against
`08_ACCEPTANCE_SCENARIOS.md` directly: no Scenario B row needs this, so it is recorded in
`07_BUILD_PLAN.md`'s "Out of scope for v1," not built here and not owed before v1. This amendment's
own text is therefore still not restored to unqualified truth for the general case — narrower than
"any producer," now precisely "any producer whose write is durable before evaluation runs against
it, and only ingest and manual assertion are v1's own scope" — but the gap that remains is
deliberately out of scope, not merely unclosed.

---

## ADR-037 — Monitor trigger model and execution bounds: accepted, amended to a unified change stream

**Status.** Accepted, 21 September 2026, amended. The ingest-delta proposal below is the record as
originally drafted — kept in place rather than rewritten, per this document's own discipline of
showing what changed and why — and is superseded by the amendment at the end of this record, which
is what was actually accepted. **What is actually delivered, as of Phase 8 Stage 1 (22 September
2026), is narrower than "accepted" alone would suggest, and is stated at the point in this record
that finding was made, not only here:** change-triggered evaluation covers ingest and manual
assertion; it does not cover the corpus-wide resolution trigger. An accepted ADR whose own opening
line implies a unified mechanism the product does not have is the same defect class ADR-036 carried
before it was amended to say the same thing about itself — stated here so this record does not
repeat that mistake by omission.

**The finding, stated plainly rather than resolved.** `02_GLASS_FRONTEND.md` §3.3 describes a
saved-pattern monitor as run "on a schedule" *and* "against new data" in the same sentence. These
are two different mechanisms with cost profiles orders of magnitude apart: wall-clock scheduling
re-evaluates a pattern against the full corpus on every tick regardless of whether anything
changed; a delta/event trigger evaluates only against what changed since the last run. The spec
names both without reconciling them, and nothing elsewhere in `docs/` picks one.

**Proposed answer.** Ingest-triggered evaluation against the ingest delta, not wall-clock
scheduling against the full corpus. This makes a monitor structurally identical to a hotlist —
B13's own mechanism ("any ingest that touches a listed identifier raises an alert") is already
delta/event-triggered — so one post-ingest evaluation pass can check both hotlist identifiers and
saved-pattern deltas rather than building two separate mechanisms with two separate cost models.
It bounds cost by ingest volume, which is what this system actually processes continuously,
rather than by corpus size, which "on a schedule" read literally would force re-scanning
regardless of whether any ingest happened at all.

**The cost, stated honestly rather than assumed away.** Delta evaluation misses a match that
becomes true without new ingested data touching it — an edge appearing between two already-
existing nodes as a pure resolution by-product (a `SAME_AS` write with no new node), or a match
created by a deletion (a previously-blocking fact removed makes an existing pattern newly match).
**Whether any acceptance row depends on those cases, checked directly:** B20's own assertion is
"Subsequent matching ingest raises an alert with the same shape as B13" — explicitly ingest-
triggered. No row in Scenario B needs a monitor to catch a resolution-only or deletion-triggered
match. This is a real capability gap against "on a schedule" read literally, disclosed as one, but
it is not a gap Scenario B's own exit criterion exercises.

**Bounds that remain necessary regardless of which trigger model is chosen.**
- **Concurrency.** Whether two evaluations of the same monitor, or evaluations of different
  monitors against an overlapping population, can run at once. Proposed: the same shape ADR-025
  already uses for the resolution trigger — a short-TTL, held-for-duration lock per monitor id,
  not merely a pre-submission check (ADR-025's own addendum on why a checked-once guard was not
  enough for its own overlap case applies here too).
- **Per-evaluation cost cap.** ADR-025's own A2 finding stands unchanged: ArcadeDB has no
  server-side query budget, keeps working past the Conduit's 30-second client-side timeout, and
  runs against a fixed 6GB heap with documented OOM history across this build. A monitor's own
  pattern-match query must therefore be bounded by the scheduler or job layer that submits it, not
  assumed safe because the client will eventually time out — the client timing out does not stop
  the server-side work.
- **Overrun behaviour.** What happens when an evaluation is still running when the next
  ingest that would trigger it arrives. Proposed, mirroring ADR-025's own choice for the
  resolution trigger: skip the redundant trigger rather than queue or error it, relying on the
  concurrency lock above to make the skip safe.

**The test that would retire this gap.**
- `test_monitor_evaluation_is_scoped_to_the_ingest_delta_not_the_full_corpus` — ingest a batch
  that does not touch a saved pattern's own entity types; assert the monitor's evaluation query
  is never issued (or is issued against zero candidate nodes), not merely that no alert results.
- `test_concurrent_monitor_evaluations_for_the_same_pattern_do_not_double_fire` — trigger two
  overlapping ingests that both match the same saved pattern; assert exactly one alert, not two,
  and that the second trigger's own submission was skipped, not queued behind the first.
- A cost-cap test proving an evaluation that exceeds its bound is stopped and recorded as such,
  rather than left to run unbounded against the server.

**Cost.** The post-ingest hook infrastructure ADR-025/Stage 1 already built
(`services/resolve/trigger.py`, the job queue, the worker loop) is the natural place to add a
second job type rather than a second mechanism — real work, but not a second worker process.

**Revisit if.** An acceptance scenario or product requirement ever needs a monitor to catch a
resolution-only or deletion-triggered match — at which point this record's delta-only scope
needs to widen, most likely via a periodic reconciliation pass layered on top of the ingest
trigger, priced as its own addition rather than folded into this one silently.

**Amendment, 21 September 2026 — accepted with the trigger widened from the ingest delta to the
change delta.**

**What changed and why.** The proposal above ties a monitor's evaluation to ingest alone. Checked
against ADR-025's own design rather than assumed compatible: ADR-025's resolution trigger writes
`SAME_AS` edges between nodes that already existed before the triggering ingest — a pattern
requiring exactly that edge becomes newly true with no new node or edge touched by ingest itself.
This is not an edge case of resolution; it is resolution's normal output, on every run that finds
a match. An ingest-only trigger would mean a monitor watching for a pattern that becomes true
through resolution never fires — not occasionally, but routinely, by construction, on every run
where the resolution trigger (ADR-025) is the mechanism that actually completes the pattern. B11's
own manual-link mechanism (`services/api/resolution.py`'s manual assertion, attributed provenance
`asserted`) has the identical property: an analyst's own manual `SAME_AS` write can complete a
pattern with no ingest involved at all.

**The accepted trigger.** Ingest, the corpus-wide resolution trigger (ADR-025), and manual
assertion (B11's mechanism) all publish to one change stream; a monitor evaluates against that
stream, not against ingest alone. The natural substrate is the same Valkey-Streams mechanism
ADR-025's own job queue already uses (`services/api/jobs.py`) — a second stream, not a second
piece of infrastructure, flagged as a proposal at the implementation-detail level since nothing in
this repository has built a corpus-wide (as against per-investigation) event stream before; the
existing `DeltaNotice` mechanism (`03_CONDUIT_MIDDLEWARE.md` §3.2) is per-investigation-scoped and
was already found unable to serve a corpus-wide signal by the still-open status-bar
conflict-count gap this phase's own known-gaps list records — the same limitation would apply here
if reused as-is, which is why this is a second stream rather than a reuse of that one.

**The test that would retire this gap.** `test_monitor_fires_on_a_match_created_by_resolution_
with_no_new_ingest` — save a pattern requiring a `SAME_AS` edge between two pre-existing nodes; run
the resolution trigger (not ingest) so it writes that edge; assert the monitor fires. A second,
parallel case for manual assertion: `test_monitor_fires_on_a_match_created_by_manual_link_with_
no_new_ingest`.

**Attempted, Phase 8 Stage 1, 22 September 2026 — built, run, and found not to work; not left as an
untested call-site gap.** The principal-resolution half of this gap is closed (ADR-043). Closing it
exposed a second, independent blocker this amendment's own text had not yet named. A real call site
was built — `run_resolution_for_entity_type` (`services/resolve/trigger.py`) calling
`evaluate_monitors_for_entry` immediately after publishing to the change stream, threaded through
`try_run_resolution_with_overlap_guard`/`run_resolve_entity_type_job` and bound at job registration
in `app.py`, the identical shape `run_studio_recipe`/`link_resolution_route` already use. Run
against a real test build: the in-handler call found no match and produced no alert for a freshly
created monitor. Diagnosis confirmed, not assumed — a second, manual call to the identical function
made immediately after the test's own `commit_transaction` correctly found the match and fired the
alert, isolating the difference to exactly one variable: whether the `SAME_AS` write was committed
yet. **The reason is transactional.** `services/api/worker.py`'s own `JobWorker._process` begins
the job's transaction, calls the registered handler (where the new evaluation call lived), and
commits **only after the handler returns** — the evaluation call therefore executed *before* the
very write it exists to alert on was committed, and `packages/ports/graph.py`'s own
`GraphPort.match(pattern, principal)` has no transaction parameter, so it cannot see an uncommitted
write from inside the same handler by any route this stage could take. The wiring was reverted
rather than kept half-working — code that silently misses the exact case it exists to catch is
worse than code that is honestly absent.

**The fix shape, and why the obvious alternative is ruled out on correctness, not merely cost.** A
`GraphPort` extension letting `match` read within the caller's own in-flight transaction was the
first shape considered, and is disqualified, not merely expensive: a job's own transaction can still
roll back after the handler returns (a later step failing, a conflict the overlap guard did not
catch) — reading uncommitted state and alerting on it means a rolled-back job can raise a real alert
for a `SAME_AS` edge that, once the rollback completes, never existed. That is an analyst told a
fact the corpus does not contain, not a performance or elegance objection, and it disqualifies the
approach before any discussion of the cost of extending a `Protocol` every adapter implements. **The
post-commit-hook shape is correct but incomplete as an in-process mechanism.** Triggering evaluation
from a hook `JobWorker` calls after its own commit reads only committed state, closing the
correctness objection above — but a process that dies between that commit and the hook running
loses the evaluation entirely, with nothing anywhere recording that it should have happened at all.
**The complete shape is a durable record of the change, with evaluation consuming from it** — which
is what this amendment's own "accepted trigger" paragraph above already described: one unified
change stream, evaluated against, not a synchronous call riding inside the producer's own request or
job. **The synchronous in-request call `_evaluate_watches_best_effort` actually builds
(`run_studio_recipe`/`link_resolution_route`) was a deliberate shortcut, not the design this
amendment describes, and it works for those two producers only because of an ordering property
specific to them: each producer's own write commits before `_evaluate_watches_best_effort` is ever
called, at the route level, well before the HTTP response returns.** That property does not hold
for the job path — `JobWorker`'s own commit happens strictly after the whole handler, including
anything the handler calls, returns — so the shortcut that works for ingest and manual assertion
does not generalise to resolution, and building a third variant of it for the job path would still
carry the roll-back correctness risk above unless it consumed from a durable record rather than
running synchronously inside the handler. Neither the durable-record consumer nor the disqualified
transaction-read shape is built here.

**Owning phase: outside v1, not Phase 8's own unassigned backlog — checked against
`08_ACCEPTANCE_SCENARIOS.md` directly, not assumed.** No row in Scenario B exercises a monitor
firing from resolution alone: B20's own assertion is "Subsequent matching *ingest* raises an alert
with the same shape as B13," the case ingest-triggered evaluation (Stage 1, already unblocked)
already covers; B8/B9/B11 exercise resolution and manual assertion themselves, not a monitor firing
from either with no accompanying ingest. release is gated on both acceptance
scenarios, not on this amendment's own broader "any producer" language — nothing committed to v1
depends on resolution-triggered monitor firing. Recorded in `07_BUILD_PLAN.md`'s "Out of scope for
v1" list rather than left inside Phase 8's own numbered stages, on the same "checked against the
acceptance scenarios directly" standard that list's own other entries already use.

**The bounds, unchanged.** Concurrency, the per-evaluation cost cap and overrun behaviour stand
exactly as already stated above — none of the three is trigger-model-specific, and A2's own
finding (ArcadeDB has no server-side query budget) still means the cap lives in the scheduler
regardless of what publishes to the stream a monitor watches.

**What the change delta still misses, checked rather than assumed.** The original proposal flagged
"a match created by a deletion" as a residual gap. Checked directly against two facts already
established elsewhere in this repository, rather than left open: first, `packages/ports/graph.py`
has no hard-delete method on `GraphPort` — the only removal mechanism this system has is
supersession (`supersede_node`/`supersede_edge`), and a superseded element is excluded from
ordinary reads rather than erased; a supersede call is itself a write, and a write is exactly what
the change stream above already captures. Second, ADR-030's own `PatternQuery` compiler expresses
only positive, present-and-connected shapes — no negation or absence constraint appears anywhere
in its own record or in `01_DOMAIN_MODEL.md` §8.1. A pattern language with no "must not exist"
clause cannot have a match newly created by removing something; removing an edge can only shrink a
pattern's match set, never grow it. Put together: the deletion case the original proposal worried
about does not exist in this system as built, because this system's only removal mechanism is
itself a write the change stream already covers, and its query language has no shape that removal
could ever satisfy. **Revisit if** ADR-030's own "revisit if" is ever exercised (a general
multi-root join, or negation added to the pattern language) — at that point this finding, not
merely the trigger-model proposal above it, needs re-checking.

**Recorded at both absences this argument depends on, not only here — Phase 7 Stage 6b's own
carry-over from 6a.** `01_DOMAIN_MODEL.md` §2.4 (`GraphPort`'s own versioning/no-hard-delete
statement) and §8.1 (`PatternQuery`'s own schema, where negation's absence is checked directly
against `PatternNode`/`PatternEdge`) each now carry a pointer back to this paragraph, stating
precisely what breaks if either absence is removed and naming the test that would need to exist
at that point — `test_change_stream_carries_an_entry_for_a_hard_delete` and `test_monitor_fires_
on_a_match_completed_by_a_negated_clause_no_longer_blocking` respectively. Read the two
statements there before adding either capability; this paragraph's own "revisit if" is the same
trigger, restated at the point a reader of the spec's own delete/pattern-matching sections would
actually be standing when they make the change, not only at the point a reader of this ADR would.

---

## ADR-038 — Hotlist membership and existence: decided, a two-mode deployment policy

**Status.** Accepted, 21 September 2026. The three-option analysis below is the record as
originally drafted — kept in place, not rewritten, per this document's own discipline of showing
what changed and why. The owner's decision, superseding "none is decided" in that analysis, is at
the end of this record: options (a) and (b) are both built, as a deployment-level policy switch,
not a single architectural choice; option (c) is not selected.

**Why this is a contradiction, not merely an unanswered question.** Hotlists hold identifiers, not
entities — `02_GLASS_FRONTEND.md` §3.3: "A list of identifiers with an owner and a review date."
Adding to a hotlist therefore needs no visibility of any graph node at all: an analyst can hotlist
a bare phone number read off a warrant before it resolves to anything they can see. B13
(`08_ACCEPTANCE_SCENARIOS.md`) promises "An alert fires naming the matched identifier, the
triggering document and the rule" on *any* ingest that touches a listed identifier — with no
qualification on whether the triggering document is visible to the hotlist's owner. The feature's
entire purpose is therefore to report that something appeared in data the analyst who set the
hotlist may not be able to see — which is precisely the existence leak standing rule 3
exists to prevent ("An unauthorised principal must not be able to detect a filtered node's
existence via path length, degree count or histogram bucket"). A hotlist alert on a document its
owner cannot open is that same leak, produced by B13's own text working exactly as specified, not
a bug introduced by insufficient filtering. Building B13 literally and honouring rule 3 literally
cannot both be true at once without choosing one of the three shapes below.

**Option (a) — alerts fire only when the triggering document is within the owner's access; the
hotlist silently misses the rest.**
- *What the analyst observes.* Alerts only for matches they could already have found themselves
  by other means; no indication that anything else matched.
- *What leaks.* Nothing — this is the option that costs rule 3 nothing.
- *What it costs to build.* The hotlist becomes materially weaker than B13's literal promise:
  "any ingest" becomes "any ingest the hotlist owner could already see," which may defeat the
  CoLP-derived use case this feature is modelled on — a warrant seizure logged by a unit other
  than the one that set the original hotlist entry.
- *The test that would prove it.* `test_hotlist_alert_suppressed_when_triggering_document_
  outside_owner_access` — hotlist owned by analyst A; a matching document visible only to a
  different principal; ingest runs; assert A receives no alert and no alert record referencing
  that document is readable by A.

**Option (b) — alerts fire with an "a match exists you cannot view" notice: a deliberate,
auditable leak rather than an accidental one.**
- *What the analyst observes.* An alert stub — the rule name, the identifier A already supplied
  (not new information to A), and an explicit statement that access is insufficient to view the
  match — with no document content, no entity detail, no field derived from the inaccessible
  record.
- *What leaks.* The existence of a matching document or event outside A's access, deliberately
  and as an audited disclosure rather than an accidental one.
- *What it costs to build.* A new, visually distinct alert-rendering state, and — the part that
  most needs an owner's call rather than an implementer's — a policy decision that this specific,
  bounded disclosure (existence only, never content) is an acceptable exception to rule 3 for
  this feature, which nothing in `docs/` currently grants.
- *The test that would prove it.* `test_hotlist_alert_shows_access_denied_notice_without_
  disclosing_content` — assert the alert record exists and is readable by A, and assert none of
  its fields beyond the identifier A already supplied are derived from the inaccessible document.

**Option (c) — hotlists carry a handling level and match only within it.**
- *What the analyst observes.* Alerts only for matches at or below the hotlist's own declared
  handling ceiling — symmetrical with how every other read path in this system already enforces
  handling in-query (rule 3).
- *What leaks.* Nothing, and it is the most structurally consistent of the three with how the
  rest of the platform works — but it changes what a hotlist can promise: an analyst who accepts
  a low default handling ceiling on their hotlist (or sets one too narrowly) can miss a real match
  even to a document they personally could see, if the hotlist's own ceiling is lower than their
  own clearance.
- *What it costs to build.* The most schema work of the three — hotlist entries need a new
  handling field, a UI control to set it, and the match/alert path needs to check it — but it
  reuses the existing `HandlingScheme` dominance-order machinery (the same mechanism ADR-025's own
  `SAME_AS`-handling-inheritance already uses) rather than inventing a new concept.
- *The test that would prove it.* `test_hotlist_match_suppressed_above_its_own_handling_ceiling`.

**A second, separately stated question: what does an analyst who does not own a hotlist observe
of it?** Not addressed anywhere in `docs/`. Count, ordering, and whether the list of entries
itself is readable to a non-owner are all unstated. This is the same existence-leak shape as the
alert question above, one level up: hotlist membership itself ("someone is watching this
identifier") could be disclosive independently of whether any match has ever fired. Flagged here
rather than answered, because it is very likely to resolve the same way the owner resolves (a),
(b) or (c) above, not independently of it.

**Decision, 21 September 2026 — a deployment-level policy switch between (a) and (b), named
`strict` and `notify`. Option (c) is not selected.**

**Why a switch rather than a single choice.** Whether a suppressed match or a content-free
existence notice is the right behaviour genuinely varies by the customer's own
information-security regime, not by anything this codebase can determine — a police force running
this platform across units with different clearances and a bank running it across compliance
functions do not answer "should an analyst learn a match exists that they cannot view" the same
way, and neither answer is wrong in the abstract. This is a deployment policy with a safe default,
not an architectural property this system should hardcode one way.

**`strict` (the default).** Option (a) as drafted above: alerts fire only when the triggering
document is within the analyst's access; a match outside it is suppressed, with no observable
trace in the analyst's own inbox.

**`notify`.** Option (b) as drafted above, with its own boundary restated precisely: an alert is
raised stating that a match exists which the analyst cannot view. It carries no identifier
context, no document reference and no jump target — nothing beyond the bare fact that the rule
fired and access was insufficient to show more. This is deliberately narrower than option (b)'s
own first draft above, which allowed the identifier the analyst already supplied to appear on the
stub; restricting `notify` further, to carry no referent of any kind, closes the risk named in
option (b)'s own draft — that a permissive evidence panel could reconstruct the very content the
mode exists to withhold — at the cost of a slightly less informative stub.

**Binding requirements.**
- **Deployment-level, not per-user, and not toggleable by an analyst at runtime.** The mode is
  configuration read once at deployment/service start, the same class of setting the demo
  provider allowlist (`06_DECISIONS.md` ADR-035's own fail-closed provider gate) already is — not
  a per-request parameter, not a per-hotlist setting, not something an API call can change.
- **Fails closed.** An unset, empty or unrecognised configuration value means `strict`. **The
  test that would prove it:** `test_hotlist_policy_defaults_to_strict_when_deployment_config_is_
  unset` — start the service with the policy variable absent, then again with an empty string,
  then again with an unrecognised value; assert all three behave identically to an explicit
  `strict` in every case: a match outside the owner's access produces no alert of any kind.
- **Audited in both modes.** Every suppressed match (`strict`) and every content-free
  notification (`notify`) writes an audit record carrying the principal, the matched identifier,
  and the policy mode in force at the time — the record a customer's security function would need
  to be shown what the system did on their behalf, in either mode, including the mode that
  produces no visible alert at all. **The test:** `test_suppressed_match_and_notify_alert_both_
  write_an_audit_record_with_principal_identifier_and_mode` — run the same out-of-access match
  under both configured modes; assert an audit entry exists for each, differing only in `mode` and
  in whether an alert row also exists.
- **`notify` must not leak through a side channel.** **The test that would catch the leak
  reappearing through the evidence panel:** `test_notify_mode_alert_contains_no_referent_its_
  recipient_cannot_read` — raise a `notify`-mode alert, then attempt every read this system
  exposes against it (the alert's own detail view, its evidence panel, a `GET` by id, an export) as
  the recipient; assert none returns a document reference, entity id, or jump target for the
  underlying match — only the rule name and the bare "match exists, access insufficient" fact.

**Option (c), recorded as not selected rather than silently dropped.** A hotlist-level handling
ceiling remains available as a future refinement layered under whichever mode is active — a
hotlist could, in principle, additionally decline to alert above its own declared ceiling even in
`notify` mode — but it is not required by this decision and is not built here.

**What a second analyst observes of a hotlist they do not own — settled, not deferred.** A
non-owning analyst observes nothing: no count, no ordering, no readable membership. A hotlist that
is not theirs does not appear in their own hotlist listing at all — indistinguishable from it not
existing, the same standing-rule-3 discipline this system already applies everywhere else, and the
same shape ADR-040 (below) applies to a saved pattern nobody has shared with a given principal.
Sharing a hotlist with a second principal is out of scope of this record. **The test:**
`test_hotlist_not_visible_to_non_owning_principal` — create a hotlist as analyst A; list hotlists
as analyst B; assert B's result contains neither the hotlist nor any count derived from it.

**Cost.** Two configured behaviours instead of one, a deployment-level config surface, an audit
write on every match evaluation regardless of which mode is active (not only on a fired alert),
and the non-owner-visibility check on the hotlist list endpoint. Real work, priced here rather than
assumed free because two of the three original options turned out to be "both, switched" rather
than "pick one."

**Revisit if.** A deployment needs per-hotlist granularity rather than one deployment-wide mode —
at which point option (c)'s handling-ceiling mechanism is the natural next layer, not a
replacement for the switch decided here.

**Addendum, Phase 7 Stage 6b — the evaluator's own unscoped read, recorded here as an explicit,
justified exemption rather than left for the next reader to stumble on unexplained.**
`services/api/evaluation.py::evaluate_hotlists_for_entry` reads every touched node with
`service_principal(scheme)` (`services/resolve/trigger.py`'s own corpus-wide identity, reused, not
a second one invented) — a read scoped to nobody, not to the hotlist's owner.

**Why it must be unscoped.** `notify` mode's entire content (`"a match exists you cannot view"`)
is a report about a node the owner *cannot* see. A read already filtered to the owner's own access
would never surface that node in the first place — `strict` and `notify` would become identical,
both silently degrading to option (a)'s behaviour, because the evaluator would never *find* the
out-of-access match `notify` exists to report. Scoping this read to the hotlist owner would not
make the leak this ADR already accepts smaller; it would make `notify` mode a name for a feature
that no longer does anything, unnoticed until an analyst asked why a match they later found by
other means never generated a stub.

**What the only barrier to disclosure is.** Finding the match and disclosing it are two separate
steps, deliberately: `evaluate_hotlists_for_entry` finding a match with the unscoped read commits
this codebase to nothing about what the owner is shown. `alerts.py::record_match`, called
immediately after with the *owner's own* principal (never the unscoped one), is the one and only
place that decision is made — its `strict`/`notify` policy branch is the entire barrier between
"the evaluator saw something" and "the owner learns anything at all." No other check, filter or
gate sits between the unscoped read and this barrier; if `record_match` were ever called with the
unscoped principal instead of the owner's, or skipped, the leak this whole ADR exists to bound
would reopen exactly the way B13's literal text originally implied it must (see this record's own
opening argument).

**`scripts/authorized_query_check.py` does not, and structurally cannot, cover this.** Confirmed
against that script's own detection shape, not assumed: it flags a `self`-first store *method*
whose name contains `"authorized"` and takes a `principal` parameter, when no SQL `SELECT` call in
its own body binds a `principal.<attr>` argument. `evaluate_hotlists_for_entry` is a module-level
function, not a store method; its name contains no `"authorized"`; and its read is not a case of
"took a principal but forgot to scope the query with it" — the exact fetch-then-check shape ADR-041
targets — it is a read built *not* to take the owner's principal at all, by design, for the reason
above. A check built to catch a principal being ignored has nothing to say about a principal being
deliberately absent from a different call three lines above a different one that isn't. The
barrier this ADR relies on is `record_match`'s own policy branch, not anything
`authorized-query-check` inspects, and no future addition to that script's heuristics will ever
reach it without also becoming able to reason about which of two adjacent calls in the same
function is the one that decides disclosure — out of scope for a purely syntactic, single-call
check.

**The test that pins the barrier.** `tests/services/api/test_evaluation.py::test_a_hotlist_match_
outside_the_owners_access_leaks_nothing_in_strict_or_notify` — a node outside the hotlist owner's
access, found only because the read is unscoped; asserts the barrier holds on both sides of it:
nothing produced under `strict`, and a `notify`-mode alert whose serialised form
(`.model_dump(mode="json")`) contains neither the node id nor the matched identifier. If
`record_match` in `evaluate_hotlists_for_entry` were ever called with the unscoped matcher instead
of the owner's own principal, this test would start asserting a full alert leaked instead — the
regression this record depends on that test catching, not merely hopes it would.

**Addendum, 22 September 2026 — cross-reference.** `strict`'s own full-suppression shape is one
instance of the general disclosure principle `06_DECISIONS.md` ADR-048 states: no safe
partial-disclosure shape exists here because any existence signal to this viewer, an authenticated,
actionable principal in this system, is itself the leak rule 3 forbids. See ADR-048 for the
reasoning that also produced ADR-045's opposite answer and ADR-046's same answer for a different
reason.

---

## ADR-039 — Alert inbox lifecycle: accepted as proposed, with two additions

**Status.** Accepted, 21 September 2026. Accepted exactly as proposed — references not copies,
access re-checked at read time — with two additions decided at acceptance, recorded below rather
than folded silently into the original text: what resolves the residual existence question left
open in the original draft, and what happens to an alert's own row on revocation.

**The gap, as the spec states it.** `02_GLASS_FRONTEND.md` §3.3 states what an alert *contains* —
"Every alert names the rule that fired and shows the evidence," and a hotlist alert specifically
carries "the matched identifier, the triggering document, and a one-click jump into a
pre-populated investigation." Nothing states who can *read* an alert, nor what happens to an
already-written alert when the access that produced it is later revoked.

**Proposed answer.** An alert stores references — node/edge/document ids, the rule id — not
copies of evidence content, and access is re-checked at read time against those referents. This is
the same "resolved fresh, not captured" principle ADR-036 proposes for monitor evaluation, applied
to a stored record rather than a re-run query. Revoking access after the alert is written must
make the alert (or at minimum its evidence) unreadable, not merely absent from some default
listing — an alert that still renders full evidence to a principal who has since lost access to
the underlying node is a durable grant outliving the permission that justified it, the exact
failure shape this whole design question exists to prevent.

**The residual question, stated rather than answered.** Once an alert's *contents* become
unreadable under the proposal above, is the alert's own *existence* still disclosive — does a
revoked-access alert disappear entirely from the inbox, or remain listed as "an alert you can no
longer view"? This is the same shape as ADR-038's hotlist contradiction: a list entry can leak
existence independently of its content, and resolving it one way for alerts and a different way
for hotlists, with no stated reason for the difference, would itself be an unexplained
inconsistency. **Proposed: this question is not answered independently here** — it should follow
whichever of ADR-038's three options the owner accepts, applied to alerts by the same logic,
rather than be decided a second, unrelated way in this record.

**Addition 1, 21 September 2026 — the residual question above is now answered, via ADR-038's
decision rather than a separate one.** ADR-038 decided a deployment-level `strict`/`notify` switch
governing whether an alert is created *at all* for a match outside the recipient's own access at
write time. That is precisely this record's residual question, restated for hotlist alerts
specifically: under `strict`, no alert row is ever written for an out-of-access match, so there is
nothing for this record to hide — the question does not arise. Under `notify`, a content-free
stub *is* written and is visible to its recipient by design — that stub's own existence is the
disclosure the mode deliberately makes, not a leak beyond what ADR-038 already accounts for and
audits. Both cases are governed by ADR-038's own mode, not by a second, alert-specific decision —
confirming the original draft's own instinct that these should not resolve independently of each
other.

**The test that would retire this gap.**
`test_alert_unreadable_after_referent_access_is_revoked` — write an alert referencing a node
visible to principal A; revoke A's access to that node (a handling change, an `org_unit`
reassignment); read the alert by id as A; assert the evidence content the alert originally carried
is no longer returned.

**Addition 2, 21 September 2026 — what happens to the alert's own row on revocation, decided
rather than left to Addition 1's logic by default.** Content becomes unreadable per the proposal
above, but the alert **remains visible in the inbox, marked unavailable, rather than vanishing.**
This is deliberately not the same answer `strict` gives at write time: `strict` prevents an alert
existing at all for a principal who never had access, whereas this is an alert the recipient
already had access to and already may have seen — the analyst has already been told the fact the
alert conveyed, so leaving the row in place discloses nothing new to them. A record that silently
disappears from an audit-bearing inbox reads as a defect and undermines trust in the inbox as a
complete record of what fired, which is a real cost of its own, distinct from the access-control
question the rest of this ADR is about. **The test:**
`test_revoked_alert_remains_listed_as_unavailable_not_removed` — write an alert readable by
principal A; revoke A's access to its referent; list A's alert inbox; assert the alert's row is
still present and marked unavailable, and a direct read of it by id returns no evidence content
but does not 404.

**Cost.** Needs the alert store's own reference schema — not yet designed, and dependent on
ADR-036/037's monitor design and on B13's hotlist-alert shape, so not something this record can
price independently of those — plus a read-time access re-check hook on every alert read, and an
`unavailable` display state distinct from a normal alert row, which is real new UI surface, not
only a backend check.

**Revisit if.** ADR-038's own `strict`/`notify` switch is ever replaced or extended in a way that
changes what "an alert exists at write time" means — at which point Addition 1's dependency on
ADR-038 needs re-checking alongside it, the same coupling this record already declares rather than
hides.

---

## ADR-040 — Pattern sharing and query-definition disclosure: proposed, decide nothing

**Status.** Proposed, 21 September 2026. Three options are presented below, in the same shape
ADR-038's own first draft used; none is decided. The owner chooses. **Pattern sharing is not
built until this record is accepted** — Part 3 of this session builds save/load/list/version/owner
only; a saved `PatternQuery` is readable exclusively by its own owner until this ADR settles how,
or whether, that changes.

**The leak, distinct from anything ADR-038 already settled.** ADR-038 governs a *result-time*
leak: whether a match's existence is disclosive to a principal who cannot see the matched data. A
saved pattern is a different object with a different leak surface. `02_GLASS_FRONTEND.md` §3.3's
own compiled shape (ADR-030's `MatchBuilder`) means a saved `PatternQuery` *is* a literal
specification — named entity types, named attribute values, the connecting edge types — the
query's own text says things like "`Person` where `employer` = 'Acme Corp'" regardless of whether
the query ever returns a single matching row. Sharing that object with a second principal
discloses those literal values through the *query definition itself*, independent of whether the
recipient could ever see a node the query matches, or whether it matches anything at all. This is
not covered by any decision this session has already made: ADR-038's modes govern what a
*recipient of a fired alert* observes about a *match*; nothing governs what a *recipient of a
shared pattern* observes about the *pattern's own text*.

**Option (a) — patterns are never shared as query definitions; a share is a saved *view* of a
result (a count, or a redacted result set), never the underlying pattern.**
- *What the recipient observes.* An outcome — "12 potential matches as of &lt;date&gt;" — with no
  visibility into what entity types, attribute values or edge shapes produced it.
- *What leaks.* Nothing about the query definition. The result-count itself can still be
  disclosive in the way ADR-038 already treats existence/count leaks generally, but that is
  ADR-038's own concern, not a new one this option introduces.
- *What it costs to build.* A second object type (a shared *view*, distinct from the pattern
  itself) with its own, narrower schema; the recipient can never refine or re-run the query
  themselves, only re-request a fresh snapshot from the owner — a real capability loss against
  "share a pattern" read literally.
- *The test that would prove it.* `test_shared_pattern_view_never_exposes_underlying_attribute_
  constraints` — share a view derived from a pattern naming a specific attribute value; assert no
  field the recipient can read (list, detail, export) contains that value or any other literal
  from the pattern's own definition.

**Option (b) — the full pattern definition is shared, but only to a principal whose own access
already covers every literal the pattern names.**
- *What the recipient observes.* The full pattern, exactly as the owner built it, including every
  entity type, attribute value and edge constraint — but only ever in a case where the recipient's
  own clearance already entitles them to see equivalent information, so nothing is disclosed to
  them that their own access did not already permit.
- *What leaks.* Nothing new — the share adds convenience (a ready-made query) rather than
  visibility, by construction.
- *What it costs to build.* The most engineering work of the three: a clearance-comparison check
  at share time, comparing the recipient principal's own access against every literal value and
  entity type named in the pattern, using the existing `HandlingScheme` dominance-order machinery
  (the same mechanism ADR-025's `SAME_AS`-handling-inheritance and ADR-038's declined option (c)
  both already reuse) rather than inventing a second one. Needs a precise definition of "covers"
  for an attribute *value* specifically, which the dominance order was designed for node/edge
  *classification*, not literal predicate values — real, undesigned work, flagged as such rather
  than assumed to fall out of the existing mechanism for free.
- *The test that would prove it.* `test_pattern_share_rejected_when_recipient_access_does_not_
  cover_a_named_value` — attempt to share a pattern naming a value outside the recipient's own
  clearance; assert the share is refused, not silently narrowed.

**Option (c) — the full pattern definition is shared unconditionally, to any principal the owner
names, as a deliberate, audited act by the owner rather than a system-enforced gate.**
- *What the recipient observes.* The full pattern, exactly as built, regardless of their own
  clearance relative to its literals.
- *What leaks.* Potentially everything in the pattern's own definition, to whoever the owner
  chooses — deliberately, on the reasoning that the owner (a cleared analyst who already knows the
  values in their own pattern) could disclose the same fact verbally or by any other channel this
  system does not control, so gating the share itself adds friction without closing a leak that
  exists outside the system regardless.
- *What it costs to build.* The least gating logic of the three — no clearance comparison needed
  — but it requires the same audit discipline ADR-038's `notify` mode already established: every
  share recorded with owner, recipient and pattern id, so a security function can be shown what
  was disclosed and by whom, the same "cannot demonstrate to a customer's security function what
  the system did" concern ADR-038 already named.
- *The test that would prove it.* `test_pattern_share_is_audited_with_owner_recipient_and_
  pattern_id` — share a pattern; assert an audit record exists naming the owner, the recipient
  and the pattern id, independent of whatever access either principal holds.

**Cost.** None of the three is built. This record is design and ownership only, the same shape
ADR-038's own first draft used before the owner decided between (a) and (b) there.

**Revisit if.** Not applicable in the ADR-025 sense — this record decides nothing, so there is
nothing yet to revisit. Whichever option the owner accepts should carry its own "revisit if" at
that point, the same discipline ADR-038's own decision section applied.

---

## ADR-041 — Structural control for the fetch-then-check authorization bug class: accepted, option (b)

**Status.** Accepted, 21 September 2026, same day it was proposed. **Option (b), the mechanical
check, is what was built** — the two options below are kept as originally drafted, per this
document's own discipline, with the decision recorded near the end rather than rewriting either.
Option (a) (the composition point) stays recorded as the longer-term shape, to build if a
query-builder abstraction over these Postgres control-plane stores ever arrives for other reasons
— not decided against, decided *after*.

**The pattern, and why documentation was tried and has now failed as the control.** A
`get_authorized`-shaped method exists to answer one question — "does this principal own/may this
principal see this row?" — and three times now, independently, someone has written it as: fetch
the row unscoped (`SELECT * FROM t WHERE id = $1`), pull it fully into process memory, then compare
`row.owning_unit` (or `owner_id`) against `principal.org_unit`/`principal.id` in Python, raising
`NotFoundError` on a mismatch. Standing rule 3 states the requirement directly ("Access control
lives in the adapter, injected into the traversal or the `WHERE` clause — never applied in the
Conduit after retrieval") and this table already carries the first fix as a named record's own
history:

1. **`services/api/review.py`'s `ExtractionCandidateStore.get_authorized`** (commit `6189461`,
   19 September 2026) — `SELECT * FROM extraction_candidates WHERE id = $1`, `owning_unit`
   compared after fetch. Fixed to `WHERE id = $1 AND owning_unit = $2`. The fix's own commit
   message states the reasoning that this record now generalises: "the row for a candidate outside
   the caller's unit was pulled into process memory, in full, before anything rejected it."
2. **The fakes that never exercised the query at all** (`07_BUILD_PLAN.md`'s "Gaps with no owning
   phase" — the four fake-double instances). Instance two there is this exact bug class from the
   *test* side: "the twenty-two `review.py` tests that passed identically either side of the real
   `AND owning_unit = $2` fix" — proof that a fake-backed suite cannot catch this class at all,
   since the fake never runs a query for the fix to be present or absent in.
3. **`services/api/pattern_store.py`'s `PatternStore.get_authorized`, this week** — `SELECT ...
   FROM saved_patterns WHERE pattern_id = $1`, `owner_id` compared after fetch, in a save/load/
   list/version store built and committed in the same session that already had instance 1's own
   commit message and this exact document's own words describing the correct shape. Found and
   fixed in a follow-up verification pass, not by the authoring session itself.

**Documentation could not have been a stronger control than it already was — it named the bug,
the fix, and the reasoning, in a record instance 3's own author had access to, and the bug still
shipped.** That is the actual argument for a structural control rather than a fourth instance of
"found it, fixed it, wrote it down again."

**A fourth and fifth and sixth instance already existed, found while scoping this record — not
hypothetical, and now fixed the same session as this decision.** Checked directly against every
`*_authorized` method in `services/api/`, not assumed from the three the user named:
`services/api/sites.py`'s `SiteStore.get_authorized`, `services/api/investigations.py`'s
`InvestigationStore.get_authorized`, and `services/api/studio_recipes.py`'s
`StudioRecipeStore.get_authorized` all carried the identical shape — `get()` unscoped, then an
`if record.owning_unit != principal.org_unit: raise` in Python.

**Each checked individually for whether the Python-side comparison was itself correct before the
fix — a hazard is not a leak, and the record should not conflate the two.** In all three, the
comparison was correct and no other caller bypassed it:
- **`SiteStore.get_authorized`** — checked every other caller of `self.get()` in `sites.py`
  (`set_control_points`/`set_grid` both call `get_authorized` first, then `self.get()` again only
  to return already-authorized fresh state) and every route in `app.py` (all go through
  `get_authorized_site`, none calls `sites.get()` directly). **Hazard, not a leak**: a mismatched
  principal was always correctly rejected; the row was pulled into process memory before the
  rejection, not returned past it.
- **`InvestigationStore.get_authorized`** — same check, same result: no other caller of `get()`,
  every route through `get_authorized_investigation`. Exercised live against a real Postgres
  instance after the fix (this store has no direct-Postgres test file of its own — `07_BUILD_PLAN.md`
  should record that as its own gap, distinct from this one). **Hazard, not a leak.**
- **`StudioRecipeStore.get_authorized`** — `list_drafts`/`list_all` are separately, correctly
  `WHERE owning_unit = $1`-scoped in-query already; every mutating method (`update_draft`,
  `update_row_template`, `publish`, `update_schedule`, `create_new_version`) calls
  `get_authorized` first and only re-fetches via `get()` afterward, to return fresh state already
  authorized earlier in the same call. **Hazard, not a leak.**

All three fixed the same shape as instance 1 and instance 3 — `owning_unit`/`owner_id` filtered
into the `WHERE` clause itself — same session, verified against live Postgres
(`tests/services/api/test_sites_store.py`, `tests/services/api/test_studio_recipes_store.py`, and
a direct manual exercise for `investigations.py` in the absence of that store's own test file).
`review.py`'s two methods, `pattern_store.py`'s, and now these three are every `*_authorized`
method in `services/api/` — `scripts/authorized_query_check.py` (below) confirms zero offenders.
Six methods across five files carried this exact bug at one time or another; none does today.

**Option (a) — a composition point: an `*_authorized` method receives its principal predicate
from a shared helper, not from hand-written SQL text.**
- *What it catches.* A structural requirement, not a review discipline: an `AuthorizedQuery`
  (or similarly-named) helper each store's `get_authorized`-shaped method must construct through,
  taking the table, the id column/value, and the principal-scoping column/value as required
  constructor arguments — the WHERE-clause fragment and its bound parameter are assembled once,
  centrally, and a caller cannot get a `fetchrow`/`fetch` out of the helper without supplying the
  principal side of the predicate, the same way a required (not optional) constructor argument
  cannot be omitted at a type level.
- *What it costs to build.* Real design work, not a small change: this codebase's Postgres control-
  plane stores are all hand-written `asyncpg` SQL strings with no query-builder layer to hook
  today (unlike `GraphPort`'s adapters, which already compose through `builders.py`) — this option
  introduces that layer for the first time, for exactly this one shape of query. It also has to
  answer composition questions instance 3 already shows are not free: `PatternStore.get_authorized`
  filters on `pattern_id` *and* `owner_id` *and, optionally, version* in one query — the helper
  needs to compose a principal predicate alongside caller-supplied predicates, not replace them.
- *Which stores need changing.* All six methods across `sites.py`, `investigations.py`,
  `studio_recipes.py` (the three still non-compliant), plus, to keep the codebase in one shape
  rather than two, the three already-compliant ones (`review.py`'s two, `pattern_store.py`'s one)
  retrofitted onto the same helper rather than left as hand-written examples of the pattern the
  helper exists to stop hand-writing.
- *The test that would prove it.* `test_authorized_query_cannot_be_constructed_without_a_principal_
  predicate` — attempt to build the helper's query with the principal argument omitted; assert a
  construction-time (not runtime-query) failure, so the gap this record closes is "the shape is
  impossible to write wrong," not "the shape is checked after being written wrong."

**Option (b) — a mechanical check: a static scan fails any `*_authorized` store method whose SQL
omits the principal parameter.**
- *What it catches.* The literal shape all three instances share: a method named `*_authorized`
  (this codebase's own established naming convention, `git grep`-able today) whose SQL string(s)
  do not reference the principal-scoping bound parameter it is given. A plain script in the shape
  `scripts/schemas_check.py`/`scripts/licence_check.py` already are — an AST walk over
  `services/api/*.py`, not a new runtime dependency — wired into `make ci` as its own target,
  the same "a PR adding a GPL dependency fails the build" discipline Phase 0's own exit criterion
  already established for a different class of thing.
- *What it costs to build.* Small and immediate compared to (a): no change to how any store
  executes a query, no new abstraction every store must adopt — a checker that reads source text
  and fails the build, working against the codebase as it is today. Weaker as a guarantee: it is a
  naming-convention-dependent heuristic (a method renamed off the `*_authorized` pattern is
  invisible to it, the same class of gap `keyboard.spec.ts`'s own hardcoded-walkthrough history
  already taught this codebase about un-discovered new instances) and a text/AST match that a
  principal parameter appears in a query's bound-parameter list does not prove it appears in the
  *right* place (a query could reference `principal.id` for an unrelated column and still pass).
- *Which stores need changing.* None, to add the check — but the check fails immediately against
  `sites.py`, `investigations.py` and `studio_recipes.py` the moment it lands, so adopting this
  option is itself the forcing function that fixes those three, on the same footing instance 1's
  fix already set, rather than fixing them first and adding the check after.
- *The test that would prove it.* A conformance pair against a small fixture store class in each
  shape, the same self-test discipline `test_gpl_rejection.py` already gives `licence_check.py` —
  built the same session as `test_a_principal_predicate_removed_from_the_query_is_flagged` /
  `test_a_principal_predicate_filtered_in_the_query_itself_passes`
  (`tests/authorized_query_check/test_principal_predicate_required.py`, alongside a third case
  proving `app.py`'s own module-level `*_authorized` route dependencies are correctly not flagged
  and a fourth running the checker against the real `services/api/` tree).

**Decision.** Option (b). **Why, stated plainly rather than left to be inferred from the two
option write-ups above:** it works against the codebase as it exists today — a plain AST script,
the same shape `licence_check.py`/`schemas_check.py` already are, wired into `make ci` the same
session it was accepted — where option (a) needs a query-builder abstraction this codebase's
Postgres control-plane stores do not have, and building one to close this one bug class first
would be solving a bigger problem than the one in front of it. Weaker as a guarantee, disclosed in
option (b)'s own write-up above (a naming-convention heuristic; proves a predicate was passed, not
that it was placed correctly) — accepted anyway, on the reasoning that a real, cheap, immediately-
buildable control beats a stronger one that stays unbuilt. **Option (a) is not declined** — kept
recorded above as the longer-term shape, to build if a query-builder abstraction arrives for other
reasons, at which point this bug class becomes one more thing it closes rather than the reason it
was built.

Built the same session: `scripts/authorized_query_check.py` (the checker), `tests/
authorized_query_check/test_principal_predicate_required.py` (its own conformance pair, matching
option (b)'s own named test), wired into `make ci` (`authorized-query-check` target) and `ci.yml`
(`authorized-query-check` job). All three live instances (`sites.py`, `investigations.py`,
`studio_recipes.py`) fixed to the query-scoped shape — see the finding above for which were
hazards versus leaks (all three, hazards). The checker runs clean against the current tree: zero
offenders across all `*_authorized` methods in `services/api/`.

**Cost.** Real, paid this session, not deferred: three store methods rewritten and reverified
against live Postgres, one new script plus its own test file, two CI wiring points. The disclosed
weakness of option (b) (heuristic, not a proof) is now a live property of the codebase's own gate,
not a hypothetical — `06_DECISIONS.md`'s own reader should not mistake a passing
`authorized-query-check` for a semantic proof that every principal predicate sits in the *correct*
place in its `WHERE` clause, only that one is present and bound in the same call.

**Revisit if.** A query-builder abstraction is ever introduced for these stores for other reasons
(option (a) becomes cheap rather than newly-costly, and should absorb this check's own job at that
point) — or if the checker's own naming-convention dependency is ever tripped by a real method
renamed off the `*_authorized` pattern (option (a)'s structural guarantee would not have that
failure mode; that specific incident is the strongest evidence for eventually building it).

---

## ADR-042 — The alpha gate: testers receive a build only after Phase 8's full exit criterion is green; the analyst review is decoupled and not blocked by it

**Status.** Accepted, 22 September 2026.

**The question, found genuinely undecided rather than assumed.** A Phase 8 stage-breakdown pass
this session confirmed, checking rather than assuming, that neither `06_DECISIONS.md` nor
`07_BUILD_PLAN.md` states when a tester receives a build. `06_DECISIONS.md` ADR-034 §B7 requires
two assertions (no private-tree file, no B5 identifier) to exist in the harness's own first
version *before* any artefact reaches an alpha or beta tester — a necessary gate, not a sufficient
one. Nothing before this record connected "the harness exists and passes its own two assertions"
to "testers may now receive a build," and nothing considered the alternative: gating on Phase 8's
own full exit criterion instead of only on the harness.

**Decision.** Testers receive a build only after Phase 8's own full exit criterion is green — both
acceptance scenarios (`08_ACCEPTANCE_SCENARIOS.md`) passing unchanged on `local-lite`. Not after
the harness alone (this record's own stage 2, the packaging pipeline); not after the
product-feature core (this record's own stage 4, assessment/export/the remaining Scenario B
steps) reaches its own exit criterion in isolation. The harness's own B7 gates remain a necessary
precondition, unchanged — this decision adds a second, stricter one on top, not a replacement.

**Why, stated plainly.** A tester evaluates a product, not a component. A build that passes the
harness's own packaging assertions but cannot yet complete Scenario A or B end to end hands a
tester something that looks shippable and is not — the same "narrower-but-honest over
broader-but-wrong" reasoning `06_DECISIONS.md` ADR-036 already applies to a different question.
Gating on the harness alone would let "Phase 8's packaging work is done" stand in for "the
platform is done," which is exactly the two facts this session's own decomposition found nothing
connecting — deciding to connect them at the *lower* bar (harness only) would be choosing the
weaker claim by default, not by reasoning.

**Consequence, stated rather than left implicit.** No external feedback reaches the product before
it is complete. Every stage in this record's own Phase 8 breakdown — principal resolution, the
harness, the documentation refresh, the assessment/export core, the smaller code fixes, the test
infrastructure — finishes before an alpha tester ever opens the product. This is a real cost,
accepted here as the owner's own call: a much longer stretch with zero outside signal than a
harness-only gate would produce, in exchange for never handing a tester a build that fails a core
walkthrough partway through.

**The analyst review is decoupled from alpha, and not blocked by it.** It needs a running dev
instance, not a packaged, tester-safe artefact — none of ADR-034 §B7's assertions apply, since a
dev instance is not distributed to a third party the way a packaged build is. Under the decision
above, it is therefore the *only* external input this build receives before completion: alpha is
gated on the full exit criterion, but a dev-instance analyst review has no such gate and can run
as soon as there is enough of the product for an analyst to usefully react to. **Owner action,
lead time measured in weeks, not a Phase 8 stage** — scheduling and running it is not development
work any stage above produces or consumes, and nothing in this record schedules it.

**Revisit if.** The cost stated above (no outside signal until full completion) turns out to be
wrong in practice — a partial build genuinely would have caught something the analyst review
alone did not — at which point a harness-only alpha gate, or a narrower "early access" tier below
full alpha, becomes the thing to weigh against this record's own stated consequence, not
reintroduced silently.

---

## ADR-043 — Principal resolution for a stored owner_id: OAuth2 Token Exchange (RFC 8693)

**Status.** Accepted, 22 September 2026. Phase 8 Stage 1's own read-first pass (this document's
own companion session note) set out three candidates and priced each without choosing; this record
is the owner's choice among them.

**The gap this closes, restated rather than re-derived.** `services/api/auth.py`'s
`PrincipalResolver.resolve()` is the only place a `Principal` is ever constructed in this
codebase, and it takes a bearer token, not an id — there is no id-keyed lookup anywhere.
`services/api/evaluation.py`'s `principal_for_owner: Callable[[str], Principal | None]` returns
`None` unconditionally for any owner who is not the current requester, which is `06_DECISIONS.md`
ADR-036's own disclosed stand-in for "the monitor stops," not a resolved answer. This record
supplies the missing mechanism.

**Decision: OAuth2 Token Exchange (RFC 8693), candidate (b) from the read-first pass.** The
Conduit's own confidential client exchanges its own credentials for a token minted *as* the target
`owner_id` (RFC 8693's `requested_subject`), and that token is decoded through the **existing,
unchanged** `PrincipalResolver.resolve()` — the identical verification, claims-parsing and
`Principal` construction a live analyst session already gets, not a second implementation of it.

**Argument one, against candidate (a) — the Admin API route needs a second claims-construction
path.** (a) would build a `Principal` directly from Admin API JSON (a user's raw attribute set),
alongside `resolve()`'s own construction from verified JWT claims — two code paths producing the
same security-critical object, which must be kept in sync indefinitely (a new custom attribute
added to one, a claim renamed in the other, a validation rule present in one but not replicated in
the other), with nothing in this codebase gating their divergence. (b) reuses `resolve()`
unchanged: the exchanged token is, from `resolve()`'s own perspective, indistinguishable from a
live session's token, so there is exactly one place a `Principal` is ever built from IdP data, not
two that must agree.

**Argument two, against (a)'s own containment — "parameterise the id, never interpolate" is a
control class that has already failed three times in this exact codebase.** `06_DECISIONS.md`
ADR-041 names all three, independently found: `services/api/review.py`'s
`ExtractionCandidateStore.get_authorized` (fetched unscoped, compared after retrieval, fixed to a
query-scoped `WHERE`); the fake-double instance that let twenty-two tests pass identically either
side of that same fix, because the fake never ran the query the fix changed at all; and
`services/api/pattern_store.py`'s `PatternStore.get_authorized`, the same bug written a third time
in the same session ADR-041's own record of the first two already existed. App-code discipline
("always scope the query," "always parameterise the id") is exactly the control class this
codebase's own history shows fails silently and repeatedly, not a hypothetical risk being
disclosed for the first time here. (b)'s containment sits somewhere structurally different: the
IdP's own claims-mapping pipeline, the same one every live user session already goes through,
which cannot inject the exchanging client's own broader claims into the exchanged token — correct
`requested_subject` in, a token scoped to that subject's own real entitlements out, by the
protocol's own construction, not by an app-code habit this codebase has already shown it cannot
sustain across three independent authors.

**Argument three — RFC 8693 is a standard; the Admin API route is Keycloak-specific, and that is a
commercial constraint bought for no technical gain.** `spec/03_CONDUIT_MIDDLEWARE.md` §6 names
Keycloak as *this deployment's own* choice of IdP, not a commitment this platform makes to every
customer's — a platform sold to run against a police force's or a bank's own existing identity
infrastructure cannot assume every customer's IdP exposes Keycloak's own Admin API shape. (a)
would tie principal resolution to one vendor's proprietary endpoint for a capability RFC 8693
standardises precisely so it does not have to be. Nothing about (a) resolves the gap any more
completely than (b) does; the vendor lock-in is pure cost, not a trade for anything.

**Argument four — candidate (c) (a locally cached/synced principal record) is rejected by
`06_DECISIONS.md` ADR-036's own words, quoted directly rather than re-argued:** *"Building a
synchronous approximation now (caching a principal from a prior request, say) would reintroduce
exactly the 'durable grant outliving whatever permission produced it' failure shape this ADR's own
second half already rejects — narrower-but-honest was chosen over broader-but-wrong."* A
TTL-bounded cache is a durable grant with extra steps regardless of how short the TTL is set; (b)'s
own freshness is bounded by the IdP's own current state at the instant of exchange, not by a sync
interval this codebase would have to choose and defend.

**The trade, recorded honestly rather than left to look costless.** Part of this mechanism's own
containment sits in realm-level IdP configuration — outside this repository, unversioned, and
invisible to `make ci` or any gate this codebase can run. **What that configuration must be:** a
confidential client, scoped by the realm's own token-exchange policy to exchange for an arbitrary
subject *and no broader capability than that* (no realm-admin grant, no scope beyond the specific
custom claims `resolve()` already reads — `clearance`, `org_unit`, `receivable_handling_codes`,
`roles`). **How an operator verifies it, since no repository gate can:** attempt an exchange for a
known, deliberately-scoped test account and confirm the resulting token's claims match that
account's own real, independently-known attributes, not a broader set; and confirm the client's
own exchange grant is actually scoped (attempt an exchange the realm's own policy should refuse,
and confirm it is refused) rather than assumed correct because the happy path worked once. Exact
click-by-click realm configuration is Keycloak-version-dependent and belongs in
`05_DEPLOYMENT.md`'s own operational material, not repeated here; this record states the
requirement the operational guide must satisfy, not the guide itself.

**Blast radius on Conduit compromise is identical under both candidates, and (a) must not be
allowed to look safer than it is in this record.** Under (a), the Conduit itself constructs the
`Principal` object from whatever JSON the Admin API returns — a compromised Conduit process can
already fabricate that JSON, or skip the Admin API call entirely and construct a `Principal`
directly in memory, since nothing after construction cryptographically binds a `Principal` to the
data it claims to represent. Under (b), a compromised Conduit can request an exchange for any
subject its client credentials are scoped to, or — identically to (a) — simply construct a
`Principal` object directly without calling the IdP at all. Neither candidate defends against a
compromised Conduit; both defend, differently, against a *correctly-running* Conduit being
misconfigured or containing a bug that resolves the wrong principal for a *legitimate* evaluation
— which is the property Q4 of the read-first pass actually tested, and the property this decision
is actually about. Recorded here so the record itself does not imply a security property neither
candidate has.

**Cost.** A new `httpx`-based token-exchange client alongside `PyJWKClient`'s own JWKS handling; a
new `ApiConfig` surface (the confidential client's own credentials, the token endpoint URL); every
`principal_for_owner` call site becomes async, since a token exchange is a live network call —
enumerated and changed as Stage 1's own build, not this record's. No live Keycloak exists in this
development environment today (`deploy/compose/dev.yaml` names Keycloak only in a comment on the
eventual twelve-container deployment target, not as a running service) — the test-side proof this
mechanism needs is therefore a local, ephemeral HTTP fixture implementing RFC 8693's token-endpoint
contract well enough to exercise the real request/response/refusal shapes, the identical "real, if
ephemeral, HTTP server rather than a mock" precedent `auth.py`'s own JWKS fixture already
establishes for the same reason. That fixture proves this codebase's own protocol handling; it does
not and cannot prove a real deployed Keycloak realm is correctly configured — the operator
verification above is what closes that remaining gap, and it is a permanent operational step, not
one this build ever retires.

**Proven against a real IdP from 27 September 2026 (round 13cc, owner ruling R8): `make idp-test`.**
`tests/services/api/test_revoked_principal_precheck.py`'s five cases now run in CI
(`token-exchange-idp-test`) and in `make test-all`, against a real Keycloak 26.0 carrying **this
repository's own realm** — rendered by `harness/realm.py` and configured by
`harness/keycloak_admin.py`, the same two modules `harness.apply` uses, rather than a realm built
to suit the test. Until that round those five had **never executed in any tier**, because nothing
set `OSPREY_TEST_KEYCLOAK_URL`; the caveat above about a fixture not proving a real realm was
therefore doubly true, since the only thing standing behind this path was the ephemeral fixture and
the tests written to go beyond it never ran. The amendment's own central finding was re-measured on
that run and still holds: `test_without_the_precheck_the_realm_issues_a_token_for_the_disabled_
subject` passes, so Keycloak does mint for a disabled subject and the Conduit's pre-check is what
refuses.

**Revisit if.** A future deployment's own IdP does not support RFC 8693 (older or non-standard
identity providers exist) — at which point candidate (a)'s own reasoning (a vendor-specific
admin-API route) becomes a real per-deployment fallback to weigh against building a second,
divergent claims-construction path, not dismissed on this record's own general-case reasoning
alone.

---

### Amendment, 24 September 2026 — containment moves into the Conduit. **Accepted.**

**Status of this amendment: Accepted**, 24 September 2026, by the owner directly, as written.
ADR-043 itself is unchanged — candidate (b) stands; this amends where the containment lives, not
which mechanism was chosen. The residual risk below is **accepted for V1** with the pre-check and
ADR-044's stopped-watch reason as its mitigations, and is named for revisit if a realm-level
per-target refusal becomes available.

**The finding, measured against a real Keycloak 26.0 rather than inferred.** This record's own
operator verification asks an operator to "attempt an exchange the realm's own policy should refuse,
and confirm it is refused". Four attempts were run against a real realm with token exchange enabled:

| Attempt | Result |
| --- | --- |
| Privileged client → the disposable test subject | granted |
| Privileged client → a different, in-scope subject | granted |
| Privileged client → a **disabled** subject | **granted** |
| Unprivileged client → a valid subject | refused — "Client not allowed to exchange" |

**Keycloak scopes impersonation by requesting client, not by target subject.** There is no
per-target policy. A bounded attempt to configure one through fine-grained admin permissions on
26.0 failed: `PUT /users/{id}/management/permissions` returns 404 even with
`admin-fine-grained-authz` enabled and reported enabled by the server, enabling authorization
services on `realm-management` leaves its resource endpoints 404, and the realm-level
`adminPermissionsEnabled` toggle is rejected with 400. **The realm cannot refuse exchange for a
specific subject. The Conduit must.**

**Security finding, recorded as one.** A disabled principal is still exchangeable at the realm. A
disabled user is a principal an organisation has revoked, and Keycloak will mint a token for them
on request from a client holding the grant. `06_DECISIONS.md` ADR-044 distinguishes an unreachable
identity provider from a revoked principal on the premise that revocation is observable; **that
premise is restated as "observable by the Conduit's own pre-check", not by the realm.**

**The mitigation, built.** `PrincipalResolver` performs a view-users read of the target principal's
`enabled` status **before** any exchange (`OIDC_ADMIN_USERS_URL`, a grant separate from the
impersonation one on purpose — a pre-check sharing the authority that fails open would be asking
the component that already said yes). A disabled principal raises `PrincipalRevoked`, a subclass of
the existing refusal so every current caller behaves unchanged while ADR-044's revoked-principal
reason becomes available to whatever marks the watch stopped. An unreachable IdP still raises
`PrincipalExchangeUnavailable`: a transient outage must never mark a live analyst's watches revoked.
Unconfigured leaves the pre-check off and the previous behaviour exactly.

**Residual risk, accepted for V1 and named for revisit.** A **compromised Conduit client can
impersonate any user in the realm.** The pre-check is in the Conduit, so an attacker holding the
client's credentials simply does not perform it. This does not make the mitigation pointless — it
closes the far likelier case of a correctly-running Conduit acting for a principal the organisation
has revoked, which is the property this record's own "blast radius" paragraph already says the
decision is actually about. It does mean the realm grant remains the blast radius, and **that is
accepted for V1 and should be revisited** if Keycloak gains per-target scoping or the deployment
moves to an IdP that has it.

**A second defect, found the same way and worth recording separately, because it means this
mechanism had never worked.** `resolve_for_owner_detailed` omitted `subject_token` from its exchange
request. RFC 8693 §2.1 makes it REQUIRED, and a real Keycloak refuses the request outright with
`access_denied` / "Client not allowed to exchange". The identical request with `subject_token`
present is granted — measured both ways. Nothing caught it because the only thing this code had ever
run against was the ephemeral HTTP fixture this record's own Cost section describes, and that
fixture accepted a request the real server rejects. This record already warned that the fixture
"does not and cannot prove a real deployed Keycloak realm is correctly configured"; the warning was
narrower than the problem, which was in the request this codebase sends, not in the realm's
configuration. Fixed, and now covered by a test that runs against a real IdP.

**The verify step asserts three things, not two** (the owner's decision of 24 September 2026),
replacing the two-sided wording in this record and in `07_BUILD_PLAN.md`'s harness entry: success
for the disposable subject with claims matching and nothing broader; refusal of an unprivileged
client by Keycloak; refusal of a disabled subject by the Conduit's pre-check. A fourth, realm-level
refusal of a specific subject, is **not** available — see the bounded attempt above.

---

## ADR-044 — Distinguishing an unreachable identity provider from a revoked principal: accepted, `WatchStatus` stays binary with a separate reason field

**Status.** Accepted, 22 September 2026. Proposed the same day, reviewed rather than rubber-stamped
before acceptance — the reasoning below was checked on its own merits, not carried over unread from
the proposal. Recorded so it is not silently decided in code once ADR-043's own mechanism starts
returning a third kind of failure (unreachable) alongside the two `principal_for_owner` already
distinguishes today (resolved; not this requester).

**The gap, restated from Stage 1's own read-first pass.** `Hotlist`/`Monitor.status` is
`WatchStatus = Literal["active", "stopped"]`, and every path that can make `principal_for_owner`
return `None` today writes `"stopped"` — correct while the only two reasons for `None` were "no
principal directory exists at all" and "this owner is not the current requester." ADR-043 adds a
third: the token-exchange call itself can fail because the identity provider is unreachable, which
is not the same fact as a revoked or insufficient principal, and `WatchStatus`'s own binary has no
room for the difference without deciding something first.

**Decision: keep `WatchStatus` binary; record the reason separately, not as a third status
value.** A third status value changes the exhaustiveness of every existing consumer (`StatusBadge`,
any future status-driven UI or query) for something that, examined honestly, is not a third
*state* of the watch itself — the watch is still, from the owner's own point of view, either
currently able to fire or not. What a third value would really be encoding is *why* it currently
cannot, which is a different axis from *whether* it can. **`"stopped"` also carries a durability
connotation an unreachable IdP does not deserve**: an analyst reading "stopped" reasonably infers
something requires their own action to resume — exactly correct for a revoked principal, actively
wrong for a transient IdP outage that may resolve, unattended, by the very next evaluation. Setting
`"stopped"` for a reachability failure makes `StatusBadge` assert something false until the next
attempt succeeds.

**What an analyst actually needs to distinguish, stated as the two questions "stopped" alone
cannot answer.** (1) *Is this a revocation needing an access review?* — clearance withdrawn, the
account disabled, an `org_unit` reassignment the saved principal reference no longer resolves to
usefully; nothing resolves this without a human changing something about the analyst's own access.
(2) *Is this infrastructure that may resolve unattended?* — the identity provider was unreachable
at the moment of one evaluation; the very next evaluation may succeed with nothing having changed
about the analyst's own entitlements at all. Conflating them risks an analyst either opening an
access-review ticket for what was really a five-minute network blip, or dismissing a genuine
revocation as "the IdP being flaky again" and never investigating it.

**Chosen: a reason field alongside the existing status.** `Hotlist.status_detail:
Literal["revoked", "unreachable"] | None` (or similar), written whenever `status` is set to
`"stopped"`, read nowhere `status` itself isn't already read. Smallest schema change; every
existing consumer of the binary `status` keeps working unchanged, and only a consumer that wants
the finer distinction opts in. **The test, named:** `test_a_revoked_principal_sets_status_detail_
revoked_not_unreachable` and `test_an_unreachable_identity_provider_sets_status_detail_
unreachable_not_revoked` — two evaluations, one where the exchange is refused by the IdP for a
disabled account, one where the exchange call itself errors (connection refused/timeout), each
asserting the row's own `status` is `"stopped"` in both cases but `status_detail` differs.

**Declined, not silently dropped: a third `WatchStatus` value** (e.g. `"unreachable"`, sitting
alongside `"active"`/`"stopped"`), changing what "stopped" itself is scoped to mean (revocation
only) rather than adding a second field beside it. A single source of truth, rather than a status
plus a detail that could, in principle, disagree with each other if a future bug set one without
the other — the real advantage this shape had — but it changes the exhaustiveness of every
existing `Literal["active", "stopped"]` consumer in the codebase for a distinction that is not, on
the reasoning above, a third state of the watch itself. Revisit if the status/detail pair is ever
found to have drifted apart in practice (the exact failure mode this shape alone would prevent
structurally) — at which point the migration cost priced below is the thing to weigh against that
observed drift, not against a hypothetical one.

**Escalation: repeated transient failures do become `"stopped"`, since an identity provider
unreachable indefinitely is not transient by any honest reading of the word.** A single unreachable
evaluation is exactly the case the freshness test already proves resolves itself with nothing to
invalidate — the very next evaluation tries fresh, no cache in the way. But an IdP that stays
unreachable across many consecutive evaluations is, from the owner's own point of view,
indistinguishable in practice from a revoked principal: nothing is being evaluated, and it has been
true for a while — the "may resolve unattended" half of the transient case stops being the honest
read once "unattended" has had ample chance to happen and has not. **Threshold: three consecutive
unreachable evaluations for the same hotlist or monitor.** Disclosed as a reasoned starting point,
not a measurement — the same "conservative and disclosed as a guess" standard this codebase already
holds itself to for `LOCK_TTL_SECONDS`/`MAX_TOUCHED_NODES_PER_EVALUATION` elsewhere, chosen because
a single failure is cheaply explained by ordinary network jitter but a second consecutive one starts
to suggest something more, and evaluations are event-triggered rather than clock-scheduled, so a
consecutive-count threshold needs no wall-clock state to track (a running counter per watch,
already the same shape `set_status` already writes on every attempt) where a time-based threshold
would need one. **Escalation changes `status` only, never `status_detail`** — a `status_detail` of
`"unreachable"` stays `"unreachable"` through escalation, never silently reclassified as
`"revoked"`; the escalation is honest about *what remains unknown* (still, for all this mechanism
can tell, an infrastructure problem) even while surfacing it with the same durability-implying word
a real revocation gets, once persistence alone has earned that word. **The test, named:**
`test_three_consecutive_unreachable_evaluations_escalate_status_to_stopped_while_status_detail_
stays_unreachable` — three evaluations in a row where the exchange call errors (not refuses); assert
`status` is `"active"` (or unset) after the first two and `"stopped"` only after the third, with
`status_detail == "unreachable"` throughout, never `"revoked"`. A companion,
`test_a_successful_evaluation_resets_the_consecutive_unreachable_count`, asserts a single success
between two failures prevents escalation — the counter is consecutive, not cumulative.

**Cost.** One nullable column (`status_detail`), one small counter (consecutive-unreachable, reset
on any success — a new column or a Valkey key, implementation's own choice, not decided here), one
evaluator-side write per attempt. No consumer changes required unless a consumer chooses to read
`status_detail`. Not built here — Stage 1's own scope was principal resolution, not this.

**Owning phase: Phase 8**, alongside Stage 1's own unfinished business (the two fix shapes ADR-037's
amendment names for wiring resolution) — this decision is real and accepted, but implementing it is
separately scoped work, the same "decided, not yet built" gap this document's own discipline already
distinguishes from "undecided."

---

## ADR-045 — Export withheld-item manifest and the recipient outside the boundary: accepted, a deployment-level switch defaulting to disclosure

**Status.** Accepted, 22 September 2026. The three-option analysis below is the record as
originally drafted — kept in place, not rewritten. The owner's decision, superseding "none is
decided" in that analysis, is at the end of this record: a deployment-level policy switch between
option (a) (ships unconditionally) and option (c) (omitted from the artefact), **defaulting to
(a)**. Option (b) is not selected.

**The finding that frames this record, checked rather than assumed.** `03_CONDUIT_MIDDLEWARE.md`
§6 already commits to the manifest's shape: "Exports carry the Osprey mark, the investigation
reference, the export timestamp, the resolution threshold in force, and a manifest of withheld
items by count." Count only, never content or identity — the same shape standing
rule 3 already accepts for the working-set status bar ("6 hidden by handling") and the delta
protocol's `notice` operation (`03_CONDUIT_MIDDLEWARE.md` §3.2: "carries a count and never carries
the withheld content, not even its identifiers"). The exporting analyst has already legitimately
seen this same count, live, in the status bar for the whole session the export is drawn from — the
manifest discloses nothing to them that the platform hasn't already shown them on screen.

**What is actually undecided.** The manifest ships inside the exported artefact, which — unlike a
live Glass session — has no session, no authenticated principal and no access boundary of its own
once it leaves the Conduit. Its reader may be the exporting analyst's own colleague, may be an
external stakeholder, a court, or another agency with no account in this system at all. A count
that was safe to show a principal the platform had already authenticated and filtered for is a
different disclosure once it travels with a file that can be forwarded to anyone. This is standing
rule 3's own concern ("an unauthorised principal must not be able to detect a filtered node's
existence... via degree count or histogram bucket") applied to a reader the system has no way to
authenticate or scope at all.

**Why ADR-038's `strict`/`notify` switch does not apply, checked rather than assumed.** ADR-038
governs disclosure to one *specific, identified* principal — the hotlist owner — at alert-write
time, and its two modes are both keyed to that principal's own access relative to the match. It
has no concept of "the recipient of this specific export," because an export has no analogous
identified recipient at write time — the exporting analyst chooses who eventually reads the file,
often after the export completes, outside anything this system observes. Applying ADR-038's switch
here would require inventing a recipient concept the export pipeline does not have and this record
does not assume into existence.

**Option (a) — the manifest ships unconditionally, exactly as `03_CONDUIT_MIDDLEWARE.md` §6
already states.**
- *What the recipient observes.* A count of withheld items on every exported chart, subgraph and
  report, regardless of who eventually reads it.
- *What leaks.* To a reader of the artefact with no principal in this system: that the underlying
  investigation held more material than the artefact shows, and roughly how much. Nothing about
  which items, their type, or their content.
- *What it costs to build.* Nothing beyond Stage 4c's already-scoped work — this is the shape the
  spec text already commits to; no new mechanism.
- *The test that would prove it.* `test_export_manifest_reports_withheld_count_regardless_of_
  declared_recipient` — export a working set with items filtered by handling; assert the
  artefact's manifest carries the count with no recipient-conditional branch anywhere in the
  export path.

**Option (b) — a recipient-aware gate at export time: the exporting analyst declares an intended
recipient class, and the manifest's presence (or its count) is conditioned on it.**
- *What the recipient observes.* An artefact exported for internal use carries the full manifest;
  one the analyst marks as destined for an external or lower-clearance recipient either omits the
  manifest or reduces it to a coarser signal (e.g. "material was withheld" with no count).
- *What leaks.* Bounded by the analyst's own declaration — but the declaration itself is
  unverified and unenforceable once the file leaves the boundary; a mismarked or dishonest
  declaration produces exactly option (a)'s leak with an added false sense of control.
- *What it costs to build.* A new recipient-class concept on the export request, a second
  manifest-rendering path, and a policy decision (mirroring ADR-038's `strict`/`notify`) for what
  each class is allowed to see — real, undesigned work, and it introduces a control this system
  cannot actually verify once the artefact is out.
- *The test that would prove it.* `test_export_declared_for_external_recipient_omits_manifest_
  count` — export the same working set twice with different declared recipient classes; assert
  the manifest differs exactly as the declared class's own policy states, and that an unset or
  unrecognised class fails closed to the narrowest disclosure, the same fail-closed shape
  ADR-038's own policy switch already uses.

**Option (c) — the manifest is omitted from the artefact entirely; the count is retained only in
the Conduit's own audit record of the export.**
- *What the recipient observes.* Nothing about withheld material at all — an artefact that looks
  complete to anyone who reads it, whatever their access.
- *What leaks.* Nothing to the artefact's reader — but it also silently drops the honesty
  guarantee `02_GLASS_FRONTEND.md` §2's own rule 4 states for the live product ("the status bar
  never lies... an analyst must never mistake a filtered picture for a complete one"), extended to
  the exported artefact: a reader with no way to know material was withheld cannot apply the same
  caution an analyst using the live Glass is given by design.
- *What it costs to build.* The least new mechanism of the three — drop one field from the export
  payload — but it is a real behavioural regression against `03_CONDUIT_MIDDLEWARE.md` §6's own
  already-written commitment, which would need to be corrected alongside this ADR if chosen, not
  left contradicting it.
- *The test that would prove it.* `test_export_artefact_carries_no_withheld_count_but_audit_
  record_does` — export a working set with handling-filtered items; assert the artefact's own
  payload contains no manifest field, and a corresponding audit-stream entry for the same export
  carries the count.

**Decision, 22 September 2026 — a deployment-level policy switch between (a) and (c), named
`disclose` and `omit`. `disclose` is the default.**

**Why disclose is the default, not omit.** An artefact that silently omits material misleads its
reader by omission. A recipient treating a chart or a report as complete when items were in fact
removed is a more serious failure than disclosing a count, because the count discloses only that
something exists, while the silence disclaims a completeness the artefact does not actually have.
In an evidential context — which is what every export from this platform is — the duty runs to the
recipient: a reader relying on the artefact to make a decision is owed the knowledge that the
picture in front of them is partial, even where they are not owed the content that was withheld.

**The counter-argument, recorded fairly rather than only as the position that lost.** The
artefact's eventual recipient may hold no principal in this system at all — an external
stakeholder, a court, another agency — and a disclosed count is information about data they have no
established right to know exists: the exact existence-leak shape standing rule 3 exists
to prevent, applied here to a reader this system cannot authenticate or scope at all. `omit` costs
this argument nothing — it is available, not merely theorised, for exactly the deployment that
weighs this risk above the misleading-by-omission risk the default is built around.

**Why a switch rather than either option alone, and why its fail-closed direction is not
ADR-038's own.** Which risk a given deployment should optimise against — misleading a recipient by
silent omission, or disclosing a count to a recipient with no established right to know it — is a
genuine trade a customer's own information-security regime should make, the same reasoning
ADR-038 already used for its own two-mode decision. `disclose` is the default because, on the
reasoning above, an artefact that lies by omission is judged the worse failure absent a
deployment's own explicit instruction otherwise — **the opposite fail-closed direction from
ADR-038's own `strict` default, and deliberately so.** ADR-038's default optimises against
disclosing a third party's existence to a principal *in this system*; this default optimises
against misleading a reader relying on an artefact *outside it* as a complete picture. The two
switches answer different questions, and there is no reason their safer defaults should point the
same way.

**Binding requirements, the same shape ADR-038's own switch already established.**
- **Deployment-level, not per-user, and not toggleable by an analyst at export time.**
  Configuration read once at deployment/service start, the same class of setting ADR-038's own
  policy mode already is.
- **Fails closed to `disclose`.** An unset, empty or unrecognised configuration value means
  `disclose`, not the reverse — the reasoning above treats silent omission as the more serious
  default failure. **The test:** `test_export_manifest_policy_defaults_to_disclose_when_
  deployment_config_is_unset` — start the service with the policy variable absent, then empty,
  then unrecognised; assert all three produce an artefact carrying the manifest.
- **Audited in both modes**, the same discipline ADR-038's `strict`/`notify` audit requirement
  already establishes: every export writes an audit record and, per ADR-047's own Gap 2 decision,
  a compliance-ledger entry, carrying the policy mode in force whether or not the artefact itself
  carries a manifest.

**If the owner overrules this default, recorded here so the reversal is not a silent edit to this
record: the default inverts — `omit` becomes the default, `disclose` the deployment opt-in — and
the reasoning above (duty to the recipient, silent omission as the more serious failure) becomes
the recorded counter-argument to that reversed default, in exactly the shape this record gives the
counter-argument here.** This paragraph is written to stay true either way, rather than requiring
this record to be rewritten if the owner's own call goes the other way.

**Cost.** A deployment-level config surface (the same class ADR-038's own mode already is); a
fail-closed default check; an audit/ledger write recording the mode in force on every export
regardless of which mode is active.

**Revisit if.** A future deployment introduces any notion of a tracked, authenticated export
recipient (a delivery/handover workflow rather than a downloaded file) — at which point option
(b)'s recipient-class mechanism becomes enforceable rather than declarative-only, and this
record's own reasoning against it (an unverifiable declaration) no longer holds.

**Addendum, 22 September 2026 — cross-reference.** `disclose`'s own default is one instance of the
general disclosure principle `06_DECISIONS.md` ADR-048 states: a safe, inert partial-disclosure
shape exists here (a count, never a referent), and this viewer typically cannot leverage it inside
the system at all, so the surface's own implicit claim of completeness — an exported artefact reads
as a finished product — is the duty that governs. See ADR-048 for the reasoning that also produced
ADR-038's opposite answer and ADR-046's opposite answer for a third, distinct reason.

---

## ADR-046 — Assessment evidence lifecycle: accepted, option (a), with one addition and an export requirement

**Status.** Accepted, 22 September 2026. The three-option analysis below is the record as
originally drafted — kept in place, not rewritten, per this document's own discipline of showing
what changed and why. The owner's decision, superseding "none is decided" in that analysis, is at
the end of this record: option (a) is accepted; option (b)'s own export-time check is folded into
the decision as a requirement rather than kept as a discarded alternative; option (c) is declined.
One question the three options never themselves asked — what a judgement looks like to a viewer
who cannot read its own evidence — is also settled there.

**What the spec already answers.** `01_DOMAIN_MODEL.md` §5 states the content-change trigger:
"When a supporting node is later split, corrected or retracted, every judgement resting on it is
flagged for review." This rests on the same non-mutation discipline `03_CONDUIT_MIDDLEWARE.md` §3
already states for edges — correction goes through `supersede_node`/`supersede_edge`, never an
in-place rewrite, "for the same reason a `Person` is never overwritten: `Judgement.supporting`/
`contradicting` can cite a[n] [id] directly, and a correction must leave that citation resolvable
to something rather than silently rewriting what it pointed at." A judgement's citation always
resolves to *something*, and a content change to what it resolves to trips the review flag.

**What the spec does not answer.** ADR-039 settled the access-change question for alerts:
references not copies, access re-checked at read, an alert whose referent access is later revoked
stays listed but goes unreadable ("marked unavailable, rather than vanishing"). Nothing in `docs/`
states whether a judgement's cited evidence is re-checked for access the same way. ADR-039's own
text is scoped to alerts throughout — it never claims to cover assessments, and inheriting its
answer silently would be exactly the "an answer given only in conversation... not fixed in the
spec" failure standing rule 11 exists to catch.

**Why assessments are the harder case, not a smaller version of the same question.** An alert is
transient — it fires, is read or not, and its own operational relevance fades once the
investigation moves on. A judgement is durable by design: `01_DOMAIN_MODEL.md` §5 calls the
assessment "the analytical product," the thing this platform exists to produce, and it is meant to
outlive the investigation that produced it — read by a reviewer, cited in a later assessment,
exported into a report that itself leaves the system boundary (ADR-045, above). An
access-re-check-at-read answer that is sufficient for an alert someone glances at once may not be
sufficient for a citation a reader returns to months later, or one that has already been baked
into an exported artefact where no re-check is even possible (ADR-045's own finding: once
exported, "no principal re-checks anything ever again").

**Option (a) — apply ADR-039's mechanism unchanged: reference not copy, access re-checked at every
read, unavailable-but-listed on revocation.**
- *What the analyst observes.* A judgement whose cited evidence they can no longer access shows
  its own statement and probability band, with the specific citation rendered as unavailable
  rather than removed — the same shape ADR-039 Addition 2 gives a revoked alert.
- *What it costs to build.* Extending the existing read-time recheck hook (once built for alerts)
  to judgement/gap/assumption citations — the smallest, most consistent option, reusing a
  mechanism rather than inventing a second one.
- *The test that would prove it.* `test_judgement_citation_becomes_unavailable_after_referent_
  access_is_revoked` — write a judgement citing a node visible to principal A; revoke A's access
  to that node; read the judgement as A; assert the judgement's own statement and band still
  render but the citation is marked unavailable, not silently dropped from `supporting`.

**Option (b) — option (a), plus an independent evidence re-verification at export time, specific
to assessments.**
- *What the analyst observes.* The same in-session behaviour as (a); additionally, exporting a
  judgement whose cited evidence the exporting analyst's own access no longer covers is refused or
  flagged by the export handling gate (Stage 4c) the same way a `consult_originator` item is —
  named specifically, not silently included.
- *What it costs to build.* Everything option (a) costs, plus a second check inside the export
  gate that walks every assessment's own citations, not only the canvas selection — real,
  additional work inside Stage 4c, priced here rather than assumed to fall out of (a) for free.
  Justified by ADR-045's own finding that export is the one point after which no further recheck
  is possible — belt-and-braces at the last controllable moment, not a duplicate of (a)'s ongoing
  in-session check.
- *The test that would prove it.* `test_export_refuses_a_judgement_citing_evidence_outside_the_
  exporting_analysts_access` — a judgement citing a node the exporting analyst cannot see; attempt
  export; assert it is blocked and the judgement is named, the same shape A15's own
  `consult_originator` assertion already uses.

**Option (c) — capture cited evidence as a copy at judgement authorship time, not a reference.**
- *What the analyst observes.* A judgement's evidence is exactly as it was when cited, regardless
  of any later access change to the source node — the judgement's own evidentiary basis can never
  become unavailable or contradict itself under a later correction.
- *What leaks.* This directly reopens the failure ADR-039 was written to prevent: "a durable grant
  outliving the permission that justified it." A principal who later loses access to a node would
  still be able to read that node's content forever, frozen inside every judgement that ever cited
  it — the same shape ADR-039's own proposal explicitly rejected for alerts, here with a
  durability problem, not a smaller one.
- *What it costs to build.* Cheap to build, expensive to have built: no read-time recheck needed,
  but it is inconsistent with ADR-039's own accepted reasoning and would need its own
  justification for why assessments are exempt from a principle just accepted for alerts.
- *The test that would prove it.* `test_judgement_evidence_copy_remains_readable_after_referent_
  access_is_revoked` — the test that would prove this option was chosen, and the one a reviewer
  should treat as a regression if option (a) or (b) is chosen instead.

**Decision, 22 September 2026.** Option (a) is accepted for the live read path: a judgement's
cited evidence is a reference, not a copy, and access is re-checked at every read — the same
mechanism ADR-039 already built for alerts, extended here rather than duplicated. Option (c) is
declined for the reason already given above: it reopens the exact failure ADR-039 exists to
prevent, and a judgement's own durability is a reason to take that failure more seriously, not a
reason to accept it.

**One question the three options above did not themselves ask, settled here: what does a judgement
look like to a viewer who cannot read at least one of its own `supporting` references?** Two shapes
are possible — the judgement renders with its statement and band intact and the unreadable citation
marked unavailable (option (a) as drafted), or the judgement itself does not render to that viewer
at all. **Decided: hidden, not shown with its basis missing.** A judgement is this platform's own
analytical product — a stated conclusion, not a data record — and a conclusion a viewer cannot
verify is not a weaker version of the same conclusion, it is an unsupported assertion wearing the
same formatting as a supported one. Displaying it invites exactly the deference the evidence-link
requirement (`01_DOMAIN_MODEL.md` §5: "a judgement cannot be saved without at least one supporting
reference") exists to prevent — a viewer who cannot check the basis but sees the conclusion anyway
is worse off than a viewer who never saw it at all, because the former has been handed a conclusion
with no way to weigh it and every reason, in the platform's own presentation of it, to trust it
regardless. **A judgement is hidden from a viewer, in full, when that viewer's access does not
cover at least one of its own `supporting` references.** An unreadable `contradicting` reference
does not hide the judgement — a contradicting item's own absence does not remove the basis for the
stated conclusion, only a possible qualifier to it — but is recorded distinctly, flagged for review
the same way a content change already is (`01_DOMAIN_MODEL.md` §5), since a reviewer with fuller
access should know a counter-consideration existed that this viewer could not see.

**The test.** `test_a_judgement_is_hidden_from_a_viewer_who_cannot_read_at_least_one_of_its_
supporting_references` — write a judgement citing two supporting nodes, one visible and one not to
principal B; list judgements as B; assert the judgement is absent from B's own list entirely, not
present with a placeholder or an "unavailable" marker in its place. A companion,
`test_an_unreadable_contradicting_reference_does_not_hide_the_judgement`, asserts the same
judgement, with its `contradicting` list (not `supporting`) carrying the inaccessible node instead,
still renders in full to the same viewer.

**Export, stated rather than left to option (b)'s own conditional framing.** `06_DECISIONS.md`
ADR-045's own finding applies here without qualification: once an assessment is exported, "no
principal re-checks anything ever again," so a judgement whose citation the *recipient* cannot
verify has left the boundary carrying exactly the same problem this record's own hidden-not-shown
decision exists to prevent in the live product — with the one control that could catch it (the
read-time recheck) structurally unavailable on the far side of the boundary. **The only remaining
control point is the export gate itself, before the artefact is produced** — option (b) restated as
a requirement rather than a discarded alternative: the export handling gate (Stage 4d) must
independently verify every exported judgement's own `supporting` citations against the *exporting
analyst's* own access, and refuse or name the judgement — the same shape a `consult_originator`
block already takes — if any citation falls outside it. This does not, and cannot, solve the
recipient's own, potentially different access: the recipient may hold no principal in this system
at all (ADR-045's own finding). It guarantees only that the exporting analyst themselves could see
everything they are about to hand someone else — the one fact this system can still verify at the
one remaining moment it has any control at all.

**The test.** `test_export_refuses_a_judgement_citing_evidence_outside_the_exporting_analysts_
access` — a judgement citing a node the exporting analyst cannot see; attempt export; assert it is
blocked and the judgement is named.

**Cost.** The read-time recheck hook, extended from alerts to judgement/gap/assumption citations;
the hidden-not-shown filter on every judgement list read, keyed to the viewing principal;
review-flag wiring extended to an unreadable `contradicting` reference, not only a content change;
the export-gate citation walk (Stage 4d's own scope to build, not priced here beyond naming it).

**Revisit if.** Option (a) or (b) is chosen and a real case surfaces where a judgement's own
evidentiary basis needs to survive a later correction to remain legally or operationally
defensible (e.g. a tribunal record) — at which point a fourth option, an immutable audit-grade
snapshot taken independently of the live citation (distinct from option (c)'s silent copy, and
itself access-controlled), is the shape to design, not a reason to fall back to (c).

**Addendum, 22 September 2026 — cross-reference.** The hidden-not-shown decision is one instance
of the general disclosure principle `06_DECISIONS.md` ADR-048 states, but not for ADR-038's own
reason despite landing on the same full-suppression shape: no rule-3 existence leak is at stake in
showing a judgement with a redacted citation, but showing the conclusion's full authority while
silently removing its own support misrepresents the assertion's warrant, which this record judges
worse than either full suppression or full disclosure of the gap. See ADR-048 for the reasoning
that also produced ADR-038's identical shape for a different reason and ADR-045's opposite answer.

**Addendum, 27 September 2026 — owner ruling R7. TENTATIVE: the owner has recorded this as
subject to revisiting after their own usability walkthrough, and it is written down here in that
state deliberately rather than held back until it firms up, because a ruling that lives only in a
conversation is lost by the next session (standing rule 11).**

**What produced it.** Running Scenario A against a rendered deployment through the analyst's own
door for the first time (`tests/scenarios/test_phase8_exit_over_the_wire.py`, owner ruling R5)
found a composition neither rule showed on its own:

- `01_DOMAIN_MODEL.md` §5 and `08_ACCEPTANCE_SCENARIOS.md`'s own additional assertion both say a
  judgement whose supporting node is retracted "is flagged for review". The flag **is** written —
  `flag_judgements_citing_superseded_node`, proven by `tests/services/api/test_assessments.py`.
- This record's hide-in-full rule then removes that judgement from the Judgements tab entirely,
  because a retraction supersedes the node with a **new id** and the citation's old id no longer
  resolves, which `judgement_visible_to` reads as an unverifiable citation.

Measured through the deployed Conduit: before the retraction the judgement lists with
`flagged_for_review: false`; after it, the list is empty. The analyst is never shown the flag this
platform's own specification promises, and no test could see it because the only test of the flag
called the flagging function directly and re-read the store, never the route — standing rule
12's shape exactly.

**The ruling (owner, R7, 27 September 2026, tentative), verbatim:**

> retraction becomes two steps. In the Glass an analyst marks a node for suppression — immediate,
> reversible, shown as a marker on the node and in the inspector. The suppression takes effect
> only when its evidence is supplied through the Ingest Studio: a retraction record ingested and
> mapped to the node like any other source, so every suppression is evidence-backed and
> auditable. A judgement citing a marked or suppressed node remains visible to its author, flagged
> for review, with the citation resolved to the successor for display; ADR-046's hide-in-full
> applies to citations the principal is not permitted to verify, not to citations the system
> itself superseded.

**Two separable parts, and only the second one narrows this record.**

1. **Retraction becomes two steps — a new design, not a clarification.** Marking is a reversible
   Glass-side state with its own marker on the node and in the inspector; *effecting* the
   suppression requires a retraction record ingested and mapped through the Ingest Studio, exactly
   like any other source. The point is that a suppression is never an unevidenced click: it has a
   document behind it and an audit trail through the same path all other evidence takes. **This
   depends on owner ruling R6** (ingest for a rendered deployment works through the Studio), so
   the two rulings are coupled and R6 has to land first — a retraction record cannot be ingested
   through a Studio that has no way to reach a file.
2. **Hide-in-full is narrowed, not reversed.** Full suppression remains correct for a citation the
   viewer's access does not cover — the case this record analysed and decided — and does not apply
   to a citation the system's own non-mutation discipline replaced. The two were never
   distinguished because `_unverifiable_citations` asks only whether the id resolves for this
   principal, and both cases answer "no" for reasons that have nothing in common. A marked or
   superseded citation resolves to its successor for display; an unreadable one still hides the
   judgement in full.

**Built, 27 September 2026 (round 13bd) — parts 2 and 3; part 1 is not built.**

| R7's part | State |
| --- | --- |
| Hide-in-full narrowed; a superseded citation resolves forward | **Built**, proven in-process and over the wire |
| Mark a node for suppression — reversible, markered, keyboard-reachable | **Built** (`02_GLASS_FRONTEND.md` §9.5) |
| The suppression takes effect when its evidence arrives through the Studio | **Not built** — see below |

**Why the third part is not built, and what it would take.** It is not effort: it is two real
decisions this record should make before anyone writes the code.

1. **The recipe engine cannot supersede anything.** Checked directly: `services/ingest/engine.py`
   calls `upsert_nodes`, `upsert_edges` and `find_node`, and nothing else. Making a publish apply
   a suppression gives *ingest* the power to mutate existing records for the first time.
   `09_INGEST_STUDIO.md` §9 does not forbid it, but its own framing is adjacent — "joining at
   ingest bakes a decision into storage and is the same mistake ADR-006 rejects" — and the
   silence is a gap rather than permission.
2. **A retraction record needs a type to be.** R7 describes "an Event of a retraction type
   carrying the target node's identifier and the reason". No such entity type exists in
   `packages/ontology/default.yaml`, so this needs an ontology addition and therefore an
   `ontology_version` bump, which every recipe, `apply_schema` call, conformance fixture and
   generated TypeScript type moves with.

Both are decisions, not tasks, and this ruling is **tentative** — the owner is revisiting it after
a usability walkthrough, and the ingest half is the part such a walkthrough is most likely to
revise. Recorded here so that whoever builds it starts from the decision rather than rediscovering
the two obstacles.

**The test that fails if this is violated**, per rule 12: `test_scenario_a_over_the_wire`'s own
retraction step, which now asserts R7's behaviour rather than pinning the old one. It pins
what the analyst sees now and says in place that the day this is implemented it must change in the
same commit as `08_ACCEPTANCE_SCENARIOS.md`'s sentence. Implementing R7 is not this record's own
change — it is queued work, and this addendum is the decision it will cite, in whatever form it
holds after the owner's walkthrough.

---

## ADR-047 — The Osprey export mark, and the durable record of what left the boundary: accepted, both gaps

**Status.** Accepted, 22 September 2026. Two related gaps, both in what happens once an export
permanently leaves the system boundary. Gap 1 (the mark's own content) is decided: option (b), a
mark that encodes handling, not only provenance. Gap 2 (the durable record) is decided separately,
as its own decision rather than folded into Gap 1's, per this record's own original framing: option
(b), a compliance-facing export ledger independent of the audit stream. Both analyses below are
kept as originally drafted; both decisions are recorded at the end of this record.

**Gap 1 — the Osprey mark is named once and defined nowhere.** `03_CONDUIT_MIDDLEWARE.md` §6
states that "Exports carry the Osprey mark, the investigation reference, the export timestamp, the
resolution threshold in force, and a manifest of withheld items by count" — checked directly, this
is the only occurrence of the phrase anywhere in `docs/`. What the mark contains, and what it is
for, is undefined. Four questions an acceptance answer must settle, not a code default:

- **Does it encode handling or classification, or is it purely provenance?** A mark that states
  the artefact's own handling level is a control a recipient can act on (know not to forward it
  further); a mark that only records where the artefact came from (Osprey, this investigation,
  this timestamp) is an attribution, not a control. `docs/` never says which.
- **What does it look like on each of the three exportable artefact shapes named in
  `07_BUILD_PLAN.md`'s Phase 8 outcome bullet — chart, subgraph, report?** A chart is an image; a
  subgraph is structured data (presumably JSON or a graph interchange format); a report is prose
  plus embedded evidence. A visible watermark suits an image; a structured artefact needs the same
  information as a field, not a rendered mark; a report needs both — one mark shape does not fit
  all three without saying how.
- **Is it machine-readable?** A visible mark a human reads is sufficient for A15's own literal
  assertion; a mark a receiving system could parse (to auto-apply a handling policy on ingest
  elsewhere, for instance) is a materially larger commitment. `docs/` states neither.
- **Is an artefact without a mark distinguishable from one that never had one?** If the mark can
  be stripped, cropped out of an image, or omitted by an older export path, nothing states whether
  a recipient (or this system, reading an artefact back in) can tell an unmarked file was never
  exported through the handling gate at all, versus one that was and lost its mark afterward.

**Gap 2 — nothing specifies a durable record of what left the boundary, independent of the
Conduit's own audit stream.** Standing rule 4 and `03_CONDUIT_MIDDLEWARE.md` §6's
audit paragraph both require every export to be recorded in the audit stream — principal,
timestamp, resolved query, result cardinality, and the justification where a handling boundary was
crossed. That record is real, but it lives entirely inside the Conduit, readable only by a
principal with access to query it. **Once the exported artefact leaves the boundary, its eventual
reader — an external stakeholder, a court, another agency — has no way to reach that record, and
no way this system can show them what left, by whom, or under what handling, after the fact.**
This is, by the acceptance-scenario doc's own framing of A15, "the operation with the least
reversibility in the product," and it is currently the one operation whose only accountability
record is invisible to everyone except an internal principal who thinks to query the audit stream.

**Options for Gap 1, the mark's content.**

**Option (a) — provenance only: Osprey identifier, investigation reference, export timestamp, τ.
No handling content.**
- *What it costs.* Nothing beyond what §6 already lists — the mark is exactly the four fields
  already named, formalised rather than extended.
- *What it does not do.* Gives a recipient no way to learn the artefact's own handling level from
  the mark itself; a recipient who needs to know how to treat the file must be told out of band.
- *The test.* `test_export_mark_carries_provenance_fields_and_no_handling_value` — export an
  artefact containing an `S2` item under an approved override; assert the mark's own fields never
  include a handling or classification value.

**Option (b) — provenance plus the artefact's own highest handling level, rendered and
machine-readable.**
- *What it costs.* A defined mark schema (not just a rendered watermark), a renderer for each of
  the three artefact shapes, and a decision about what "highest handling level" means for an
  artefact assembled from items at mixed levels — real design work `docs/` does not currently
  scope.
- *What it buys.* A recipient, or a downstream system ingesting the artefact, can act on the mark
  directly rather than needing the originating investigation's own context.
- *The test.* `test_export_mark_reports_the_highest_handling_level_present_in_the_artefact` —
  export a selection mixing two handling levels; assert the mark's own machine-readable field
  carries the higher of the two, and that a chart, a subgraph and a report export of the same
  selection all carry the same value in their own shape's own mark location.

**Options for Gap 2, the durable record.**

**Option (a) — extend the existing audit stream's own export entries with a compliance-queryable
view, no new store.** A role (not the investigation's own analyst population) can list every
export by principal, artefact type and handling level, without needing per-investigation access to
read individual audit entries.
- *The test.* `test_a_compliance_principal_can_list_every_export_without_investigation_access` —
  export from two different investigations as two different analysts; list exports as a principal
  holding only the compliance role; assert both appear with principal, timestamp and handling, and
  that the principal cannot read either investigation's own graph content.

**Option (b) — a separate export ledger, independent of the audit stream, written transactionally
with the export gate.** Its own store, its own retention policy (potentially longer than the audit
stream's), explicitly designed to survive an investigation's own deletion or archival.
- *The test.* `test_export_ledger_entry_survives_investigation_deletion` — export from an
  investigation; delete or archive the investigation; assert the ledger entry for that export
  still exists and is still readable by a compliance principal.

**Decision, Gap 1 — 22 September 2026. Option (b): the mark encodes handling, not only
provenance.** A provenance-only stamp (option (a)) tells a recipient where an artefact came from
and nothing about how to treat it — and the mark is the *last* control that applies once the file
is outside the system (`06_DECISIONS.md` ADR-045's own finding: "no principal re-checks anything
ever again"). A control that expires at the one moment it would matter most is not a control worth
building only halfway.

**What it encodes.** The four provenance fields §6 already names (Osprey identifier, investigation
reference, export timestamp, τ) plus the artefact's own highest handling level present at export
time. "Highest" because an artefact assembled from mixed-handling items must be treated at the
level of its most sensitive component by whoever receives it — the same dominance-order reasoning
`HandlingScheme`'s own machinery already applies elsewhere (ADR-025's `SAME_AS`-handling
inheritance, ADR-040's declined option (b)), reused rather than a new rule invented for export.

**What it looks like on each shape.**
- **Chart.** A visible footer or watermark carrying the human-readable fields, *and* the same
  fields embedded as machine-readable image metadata (a PNG text chunk or the export format's own
  equivalent) — visible to a human reading the picture, and parseable by a system that ingests it
  without OCR.
- **Subgraph.** A top-level field on the structured payload itself — not a rendered mark at all,
  since the artefact has no visual surface to render one on. The same field names and values as the
  chart's own embedded metadata, so a consumer reading either shape finds the mark the same way.
- **Report.** Both: a visible header/footer stamp on the document (the chart's own convention) and
  the same embedded structured field the subgraph carries, since a report is prose plus embedded
  evidence and needs to be readable by a person and machine-checkable by a downstream system at
  once.

**Machine-readable: yes, in every shape, not only human-visible.** A rendered watermark alone would
satisfy A15's own literal assertion but not a downstream system trying to auto-apply a handling
policy on ingest — exactly the capability a provenance-only mark (option (a)) would have foreclosed.

**Distinguishable from never having had one: only from this system's own side, not
unconditionally.** The export pipeline is changed so that it **never produces an artefact without a
mark** — the mark is written by the gate itself as part of producing the artefact, not an optional
step an export path could skip, so nothing this system exports is ever genuinely unmarked. What
this decision does **not** solve, recorded honestly rather than implied solved: a recipient holding
a file with no mark cannot tell "this never passed through the gate" apart from "the mark was
stripped or cropped out after export" without cryptographic signing, which is a real escalation
this record does not decide.

**The test.** `test_export_mark_carries_handling_and_is_machine_readable_on_every_artefact_shape` —
export the same selection as a chart, a subgraph and a report; assert each artefact's own mark
carries the same handling value, that the chart's and report's own visible rendering agrees with
their embedded metadata, and that the subgraph's field is present with no visual rendering
expected. A companion, `test_the_export_pipeline_never_produces_an_artefact_with_no_mark`, asserts
every code path that can produce an artefact writes one.

**Decision, Gap 2 — 22 September 2026. Option (b): a separate export ledger, independent of the
audit stream.** The recommendation this record adopts: a compliance-facing log, its own store, not
an extension of the Conduit's own audit stream (option (a)) — because the audit stream's entire
value to an *investigation* is that it is scoped to that investigation's own access, and the
durable record's entire value to *compliance* is that it must be readable by someone who is not,
and should not need to be, a principal on any investigation at all. Folding the two into one store
with a second access path (option (a)) risks the compliance view quietly inheriting an
investigation-scoping assumption the audit stream was never built to shed; a separate store never
has that assumption to shed in the first place.

**Retention, named rather than left to the store's own default.** The ledger is explicitly designed
to survive an investigation's own deletion or archival — the reason a durable record exists at all
is to answer "what left the boundary" after the investigation itself may no longer be queryable, so
tying its lifetime to the investigation's would defeat its own purpose.

**The test.** A companion to the one already named above,
`test_a_compliance_principal_can_list_every_export_without_investigation_access`, asserts the
ledger's own read path needs no per-investigation grant at all.

**Cost.** A new store (schema, retention policy, its own access-control role distinct from any
investigation's own principals); the mark-writing change to every export code path, for both gaps
together; the mixed-handling "highest level" computation reusing `HandlingScheme`'s existing
dominance order rather than a new one. Real, additional Stage 4d work, priced here rather than
assumed to fall out of the export gate's own existing scope for free.

**Revisit if.** Either gap surfaces a real customer requirement this record did not anticipate (a
specific regulatory retention period, a specific machine-readable marking standard already in use
by a customer) — at which point that requirement, not this record's own options, should drive the
final shape. Tamper-evidence against a stripped mark specifically (Gap 1's own residual, above) is
its own trigger: a signed mark, or a hash recorded in the Gap 2 ledger, is the shape to design then,
not assumed into this decision now.

---

## ADR-048 — The disclosure doctrine: what makes "something was withheld" safe, unsafe or required to be visible

**Status.** Accepted, 22 September 2026. A reconciling record — it decides nothing new. ADR-038,
ADR-045 and ADR-046 each already answered, independently, the same underlying question for a
different surface, and this record states the principle that generated all three, rather than
leaving three pairwise-consistent defaults to be re-derived by inference. Cross-referenced from,
and cross-references, all three.

**The question, restated once rather than three times.** For a given surface, when something has
been withheld from a given viewer, does that viewer learn that anything was withheld at all?
Three surfaces in this build already answer it, and the three answers are not the same:

| | Surface | Viewer's answer | Disclosure shape |
| --- | --- | --- | --- |
| ADR-038 (`strict`) | A hotlist owner's own alert inbox | Learns nothing — no alert, no trace | Full suppression |
| ADR-045 | An exported artefact | Learns a count of withheld items | Disclosed (count only) |
| ADR-046 | A judgement in the Judgements tab | Learns nothing — the judgement itself does not render | Full suppression |

Two of the three suppress fully; one discloses. Stated as a bare table, this looks like an
inconsistency waiting to be found by anyone who reads more than one of these records — exactly the
kind of question `06_DECISIONS.md`'s own discipline of cross-referencing exists to answer before a
customer's security function has to ask it.

**Why a single axis — "internal viewer vs. external viewer" — does not explain the table.** ADR-038
and ADR-046 both suppress fully, but their viewers are not the same kind of outsider: ADR-038's
viewer (the hotlist owner) is a fully authenticated principal *in this system*, on their own
session, looking at their own inbox; ADR-046's viewer (a fellow analyst) is also a fully
authenticated principal *in this system*, on their own session, looking at the same investigation's
own Judgements tab. Both are as "internal" as a viewer gets. Meanwhile ADR-045's viewer may hold no
principal in this system at all — the most "external" viewer of the three — and is the one who gets
told something. A rule built only on "is this viewer inside or outside the system" predicts the
opposite of what these three records actually decided. The real distinction runs along three
different questions, asked together, not one:

**1. What does the surface itself already claim about its own completeness, independent of this
decision?** An alert inbox (ADR-038) is, by its own nature, a personal, scoped notification
surface — nothing about "receiving alerts" ever implied "a census of everything in the corpus,"
so a viewer never formed a completeness expectation this decision could break. An exported artefact
(ADR-045) is, by its own nature, presented as a finished product — a chart or report handed to a
reader carries an implicit claim of completeness unless stated otherwise, precisely because it has
no status bar, no live session, no ongoing view an analyst already knows is partial. A judgement
(ADR-046) is, by its own nature, an assertion — not a data view at all, but a stated conclusion
that, if shown, claims to be supportable. Each surface's own implicit claim is the thing this
decision must not let become false.

**2. What could this viewer do with an existence signal, given who they are and their relationship
to the system?** ADR-038's viewer holds an ongoing, actionable relationship to this system — they
could escalate, ask a colleague, re-request access, or simply keep trying, all *within* the system,
turning a bare existence signal into a live investigative lever against an access boundary rule 3
exists to hold. ADR-046's viewer holds the identical kind of relationship — the same actionable,
in-system position — which is why its own answer echoes ADR-038's, not ADR-045's. ADR-045's viewer,
often, cannot act on the signal *inside this system at all*: an external reader with no session, no
principal and no way to query further gains nothing actionable from a bare count beyond the one
thing they are owed — that the picture in front of them is not the whole one.

**3. Is there a safe partial-disclosure shape, or does any disclosure at all collapse into full
leak (or into false completeness)?** ADR-045's count is a safe partial shape precisely because it
discloses a fact (something exists) without disclosing anything actionable about it (what, where,
which) — the same shape standing rule 3 already accepts for the status bar and the
delta protocol's `notice` op, extended once more here. ADR-038 has no safe partial shape available
to it at all: any existence signal to an in-system principal *is* the leak rule 3 forbids, so
nothing short of full suppression avoids it — this is `strict`'s own reasoning, unchanged.
**ADR-046 is the case worth naming most carefully, because it is not the same kind of "no safe
partial shape" as ADR-038's.** A judgement shown with an unreadable citation is not a leak in
rule 3's sense at all — no unauthorised existence is disclosed by rendering a statement and a
probability band. It fails for a different reason: the *conclusion itself* keeps its full
presentational authority while the one thing that would let a viewer weigh it has been silently
removed, which is worse than either extreme — worse than full suppression, because a viewer who
never sees the judgement forms no false belief, where a viewer who sees an unweighable conclusion
may defer to it anyway; and worse than full disclosure of the gap, because "conclusion, evidence
redacted" still reads as an authoritative assertion in a way "N items withheld" never claims to be
one. Hiding the judgement in full is therefore not ADR-038's rule applied a second time — it is a
different rule (protect the integrity of an assertion, not the existence of a record) that happens
to land on the same disclosure shape.

**The principle, stated once.** *A surface must not let a viewer form a false belief about
completeness, and it must not let a viewer, or a third party the viewer can reach, learn something
this system owes no one but an authorised principal the right to learn. Where those two duties
conflict, resolve toward whichever failure is worse for **this** surface, decided by what the
surface itself already claims to be (a scoped view, a finished product, or an asserted conclusion),
what the viewer could do with a bare existence signal, and whether a safe, inert partial-disclosure
shape (a count, never a referent) actually exists for this case or collapses into one of the two
failures regardless.* Where a safe partial shape exists and the viewer cannot leverage it inside
the system, disclose (ADR-045). Where no safe partial shape exists because any signal is itself
the leak, suppress (ADR-038). Where no safe partial shape exists because showing anything at all
would misrepresent an assertion's own warrant, suppress the assertion whole (ADR-046) — not for
ADR-038's reason, but to the same visible effect.

**A sharper, single-test restatement of factors 1 and 2 together, checked against all three cases
rather than assumed to fit.** Disclosure is owed where the viewer has no other means of knowing
the view in front of them is incomplete; it is not owed where they already do. An in-session
analyst has the working-set status bar and its own "N hidden by handling" convention, trained
across every other surface of this same product, in the same session — they already carry a
standing expectation that any given view may be partial, before this decision ever renders
anything. A recipient holding an exported file has no such training: no prior exposure to this
product's own conventions, no session, nothing that would tell them a chart or report can be
partial at all. **This crisply explains ADR-038 against ADR-045 — the two cases with the same
kind of viewer (an authenticated, in-session principal) is not what distinguishes them; whether
that viewer's own general experience of this product already discloses partiality is.** `strict`'s
own silence costs nothing new, because the hotlist owner already knows, from using the rest of the
product, that a view being partial is normal; the export's own manifest is owed precisely because
its reader has never seen this product's own conventions at all.

**Where this single test does not reach, and why that is not a gap in it.** ADR-046 is not decided
by this test — a fellow analyst reading the Judgements tab *does* have the same in-session
training as ADR-038's own viewer, so this test alone would predict silence is safe there too, and
it is not. The reason, restated from factor 3 above: ADR-046's failure is not a viewer mistaking a
partial *view* for a complete one — it is a viewer trusting a *conclusion* whose own presentation
claims a warrant it cannot demonstrate having. The "does the viewer know views can be partial"
test answers a question about the surface (a list, an inbox, an artefact); it has nothing to say
about a surface whose content is itself an assertion. Both tests are needed, and applying only the
sharper one to every future case would silently drop the assertion-integrity case this document
already had to name separately to get ADR-046 right.

**Applying this to a future surface, so the next one is derived rather than guessed.** Ask, in
order: (1) what does this surface already claim about its own completeness? (2) who is the viewer,
and what could they do inside this system with a bare existence signal? (3) does a count-only,
referent-free disclosure exist for this case that is actually inert, or does any disclosure here
collapse into a leak or a false endorsement? The answer to (3), given (1) and (2), is the
disclosure shape — not a fourth option invented per-surface, and not an assumption that whatever
the last surface decided is the default for the next one.

**Cross-references.** `06_DECISIONS.md` ADR-038's own `strict`/`notify` decision, ADR-045's own
disclose-by-default decision, and ADR-046's own hidden-not-shown decision each carry a short
addendum pointing back to this record, added alongside this one.

---

## ADR-049 — The harness / packaging pipeline: `osprey.yaml` as the single source, and Phase 8's Stage 2 §1–§7

**Status.** **Accepted**, 24 September 2026, by the owner directly, after rulings on all seven open
objections, the correction narrowing D1, and the settlement of the four follow-on items — every one
of them recorded below rather than folded in silently. Binding on the same footing as every other
accepted record: `07_BUILD_PLAN.md`'s Stage 2 §1–§7 entries are the plan, not a proposal.

**Build state at acceptance.** `Stage 2 §1` is under construction in the session that recorded this
acceptance; §2–§7 are not started.

**Amended 24 September 2026 to record the owner's rulings.** Each ruling is recorded under the
objection it answers, in "Owner's rulings" below, and the consequential edits each requires have
been applied to the sub-stages above it rather than left as a note to act on later. The sub-stage
labels changed in the same pass — see ruling 1.

**Why this record is ADR-049 and not ADR-044.** The design this record writes up arrived numbered
ADR-044. `06_DECISIONS.md` already has an ADR-044 (*Distinguishing an unreachable identity provider
from a revoked principal*, accepted 22 September 2026) and runs to ADR-048; the status register
above stopped at 041 and would not have shown it. Corrected here, and the register's own lag closed
in the same change — recorded rather than silently renumbered, because the near-miss is the second
instance of the same failure this document has already had to record once.

**Scope.** This record is documentation. It amends no accepted decision on its own authority; where
it disagreed with one it said so and stopped, and the owner has since ruled. The one such case —
the `decision_record` field on `scripts/real_data_exceptions.py` — is now an owner decision (ruling
3) and is recorded here as required work, **not built by this record**.

**A gate this record turned red, and the fix, both recorded.** On first writing, `make
decision-log-publication-check` reported two violations — "ADR-049 cites ADR-034", "ADR-049 cites
ADR-042" — and it was correct to. **This record is PROCESS-classified** under ADR-034 §B10's own rule
("a decision about how this build was scoped, phased, released or published — the project's own
management, not the product's behaviour"): it divides a phase into sub-stages, sets their exit tests,
and concerns release packaging. `scripts/decision_log_publication_check.py`'s `PROCESS_ADR_NUMBERS`
gained `"049"` on 24 September 2026, with two fixture cases each shown red against the pre-change
source first — one for the false positive the omission caused (an ADR-049 section citing ADR-034 and
ADR-042 must not be flagged), one for the false negative (a PRODUCT ADR citing ADR-049 must be). The
pre-existing case citing ADR-034 from ADR-006 passes identically either way, which is why neither new
case reuses its shape — standing rule 15's second clause. Nothing was allowlisted: the allowlist
is for known debt that shrinks to zero, and a correctly-classified record is not debt. **Two other
gates were already red on a clean `HEAD` before this record existed, and are not this record's:**
`make route-coverage-check` (six undocumented routes) and `make test-file-coverage-check`
(`tests/scenarios/test_phase8_exit_criterion_end_to_end.py` wired into neither job) — verified by
running both against a stashed tree.

**A property of that gate worth naming once, since this is the first new ADR written since it
shipped.** `PROCESS_ADR_NUMBERS` is a hand-maintained set inside the script. Every new PROCESS ADR
must be added to it by hand, and the gate's failure mode on omission is the *safe* direction — it
fires — which is why this was caught immediately rather than silently. Recorded so the next author of
a PROCESS record expects the step rather than reads the failure as a defect in their own citations.

### The three owner decisions this design rests on — all three confirmed

- **D1 — owner's decision, 24 September 2026, confirmed NARROWED.** The packaged artefact is
  container images for **each deployable service** — not each service directory — **plus** the
  bundle tarball (manifests, the `osprey.yaml` schema, `LICENSE`/`NOTICE`, documentation), built by
  a repository script of the `osprey bundle` shape, runnable in CI and by the harness; `--images`
  for air-gapped install.

  **Corrected by the owner directly, and the correction is recorded rather than folded in
  silently.** An earlier "see D1" was read here as confirming D1 *unnarrowed*, and ruling 5 was
  derived from that reading. That was not the owner's intent. D1 is narrowed to "each deployable
  service", and **`Stage 2 §5`'s first task enumerates the six service directories, states which
  are deployable, and builds the missing Dockerfiles as Stage 2 work — not as debt owed by earlier
  phases.** Ruling 5 is re-derived below from the narrowed decision; the superseded derivation is
  left visible there rather than deleted, because this record's own previous version was pushed and
  read.
- **D2 — owner's decision, 24 September 2026.** The real-data exceptions list is a **panel on the
  Governance screen**, not a seventh screen. This matches `05_DEPLOYMENT.md` §2.1's table, which is
  explicitly "Six screens". `07_BUILD_PLAN.md`'s Phase 8 outcome bullet said the opposite in as many
  words ("**A new screen, added 23 September 2026**: managing the real-data exceptions list") and is
  amended in the same change that records this — see ruling 4.
- **D3 — owner's decision, 24 September 2026; the widening is deliberate.** Stage 2's exit is three
  named tests (below), and its entry states in one sentence that this is not ADR-042's alpha gate.
  This widens the stage's existing exit criterion, which was one test ("a `backup` → `restore` cycle
  reproduces the graph from staged Parquet"); the golden-path deploy and the packaging assertions
  were described in that same entry as "testable too" and "mechanical and testable", never as exit
  criteria. Recorded as a deliberate widening rather than a drafting tidy — see ruling 7.

### The principle, kept as proposed

The harness is a headless engine first and a browser application over it second. Every screen has a
CLI equivalent (`05_DEPLOYMENT.md` §2.3) because they share one implementation, not because two were
written. §2.5's three constraints bind throughout: no state beyond the repository, never sees a
secret, not a privileged long-lived process.

**One place the design as submitted broke its own principle — now fixed by ruling 2 — and one place
it risks breaking it.** The ADR-043 preflight check required the harness to *use* a confidential
client's secret, not merely reference it; the owner has moved that check to the post-launch verify
step, which resolves it. And `python -m harness.bundle` would be a second module claiming the command
shape `scripts/osprey_bundle.py` already occupies — "they share one implementation, not because two
were written" applies to this design's own modules first (amendment 12).

---

### The sub-stages as amended

**Labelled `Stage 2 §1` through `Stage 2 §7`, per ruling 1**, replacing the `2b`–`2h` the design
arrived with. That earlier scheme collided with `2a`, which `07_BUILD_PLAN.md` defines as a *sibling*
stage (ArcadeDB stability, closed), not a sub-stage of this one; `2a` keeps its label and its
meaning, and the sub-stages no longer look like its continuation.

**Always written in full — `Stage 2 §5`, never a bare `§5`.** This document, `05_DEPLOYMENT.md` and
`07_BUILD_PLAN.md` all use `§N` for a *specification section*, and several of those references sit in
the same sentences as these labels ("`05_DEPLOYMENT.md` §5's `verify`" beside "Stage 2 §5", the
packaging sub-stage). The full form is the only thing keeping the two apart, so it is a rule of this
record rather than a style preference. Commits and reports written before 24 September 2026 cite the
old `2b`–`2h` labels; the mapping is `2b`→`Stage 2 §1`, and so on in order to `2h`→`Stage 2 §7`.

#### Stage 2 §1 — `osprey.yaml` as the single source

A Pydantic schema in `packages/schemas` for `osprey.yaml` covering profile, components, models,
governance (including the real-data exceptions reference, D2), geospatial and cluster hosts. A
generator (`harness/render.py`) that renders the deployment's real compose file for `local-lite` and
`small`, and Kubernetes manifests for `cluster` (ADR-011: not a toggle; a different renderer). Drift
detection and a change preview before writing (§2.1, §2.4). `deploy/compose/dev.yaml` is **not**
replaced; it stays the test convenience its own header already says it is — confirmed against that
header, no finding.

**Amendment 1 — the renderer must emit four artefacts, not two.** `05_DEPLOYMENT.md` §2.1 names them
exactly: "compose or Kubernetes manifests, environment files, `versions.lock` with every image digest
pinned, and `RUNBOOK.md` written for *this* deployment with the real hostnames, ports and paths
filled in." The design listed the first only. `versions.lock` is separately load-bearing: §5 makes
rollback depend on it ("`deploy/versions.lock` records every digest that has been live, so there is
always a known-good target") and §7 requires "digests pinned in `deploy/versions.lock`". Checked
directly — no such file exists; `deploy/` holds `cluster/.gitkeep`, `compose/dev.yaml` and
`compose/litellm_config.yaml`.

**Amendment 2 — the two `RUNBOOK.md`s are different files and the design conflated them.** §2.1's is
*generated per deployment* and is a Stage 2 §1 output. §6's `deploy/RUNBOOK.md` states the recovery time for
each path and is written, not generated (Stage 2 §4). Phase 8's own outcome bullet names the first —
"Generated Kubernetes manifests **and the per-deployment runbook**."

**Amendment 3 — the schema must reuse `packages/schemas/mapconfig.py`, and must not invalidate the
committed file.** The root `osprey.yaml` today contains a `map:` key and nothing else — no profile,
components, models, governance or cluster hosts — and `services/api/mapconfig_loader.load_map_config`
reads it as an unguarded `raw["map"]`, with `tests/test_demo_osprey_config_is_tier_1_only.py`
asserting against it. A document-level schema that requires the other sections breaks both. The
committed file's own header already states its status ("A real deployment's own `osprey.yaml` is
generated by the harness (Phase 8)… this file is committed so the platform is demonstrable with zero
configuration"), so Stage 2 §1 must decide explicitly what that file is under the new schema rather than
discover it.

**Exit test, amended.** Rendering a fixture `osprey.yaml` is byte-stable across runs; a hand edit to
a generated file is reported as drift; the diff names every changed path — **for all four artefact
kinds**, each with its own planted drift of the real generated shape (rule 15's second clause). The
unamended test was vacuous in a specific, checkable way: byte-stability, drift detection and
"names every changed path" are all green over a renderer that never emits `versions.lock` or the
per-deployment `RUNBOOK.md` at all.

**Amendment 4 — file-against-file is not §2.4's drift detection.** §2.4: "the harness compares **the
running deployment** against `osprey.yaml` and shows any divergence." Comparing generated output
against what is on disk is a different, easier check. Both are wanted; only the second was specified.
The running-deployment comparison is the one §2.4 names and the one that catches `kubectl edit`.

#### Stage 2 §2 — Preflight, headless

`harness/preflight/`, one module per check, each returning `{status, what is wrong, what to do,
re-checkable}`. `python -m harness.preflight` runs all or one.

Checks as proposed: memory against the profile floor; disk against projected staging volume; GPU
presence and driver; port availability per declared service; container runtime version; cluster
connectivity to every declared host; and the four rehearsal-derived checks (the interpreter is the
project venv; every service's bind address is consistent and printed; the basemap is built and served
over HTTP, not `file://`; the DuckDB lock holder is not running when seeding is requested).

**Amendment 5 — `05_DEPLOYMENT.md` §3's reduced variant is missing, and it is squarely install-path
material.** *(Ownership confirmed by the owner, 24 September 2026, against a brief that had placed it
in `Stage 2 §1`: the **offer** lives here, in Preflight; `Stage 2 §1` only has to be able to
**render** the reduced variant when asked. The split is deliberate — §3's own words are "It is
**offered**, not applied silently", which is a Preflight behaviour, not a renderer one.)*
"If Preflight finds less than 16 GB it offers a reduced variant that drops OpenSearch and
falls back to PostgreSQL full-text, stating the trade-off on screen: search quality degrades and
semantic search is unavailable… **It is offered, not applied silently.**" A memory check that only
compares against the profile floor fails a 16 GB laptop — the exact clean-laptop case the milestone
is defined by — instead of offering the path the spec already specifies. Its own exit test: a
preflight run under a below-floor memory reading offers the reduced variant and does not apply it.

**The ADR-043 token-exchange check is not a pre-launch check and is not in this sub-stage's list.**
Ruling 2 moved it out; the owner's settlement of 24 September 2026 then placed it as the final step
of `Stage 2 §3`'s golden-path deploy (amendment 26 there), with `Stage 2 §7` keeping the Re-check
surface for an operator re-running `verify` later. The reason it cannot live here is unchanged and
worth keeping stated: running it before Launch would need the harness to hold and *use* a
confidential client's secret, against §2.5's "never sees a secret", at a moment when no Keycloak is
running to exchange against. Preflight still *renders* it — as a post-launch item with its own
Re-check and the exact operator wording `07_BUILD_PLAN.md`'s stage entry gives verbatim ("token
exchange is not correctly configured on your identity provider; watches will appear stopped for every
owner but the analyst who triggered them until this is fixed") — it simply does not gate Launch on
something that cannot run before Launch.

**Exit test, as proposed and accepted.** Every check has a red-then-green test whose planted failure
takes the shape the check actually reads, and `launch` refuses while any check is red. (Note the
CLI's own name: §2.3 calls this `osprey apply`, not `osprey launch`.)

#### Stage 2 §3 — Scripted golden-path deploy

`python -m harness.apply`: fresh checkout → render (Stage 2 §1) → preflight (Stage 2 §2) → start stack → wait for
health → seed if requested. The checker's own scripted bring-up from 24 September 2026 is retired
into this once it exists; until then it stays (since removed — see the phase plan's Stage 2 §3
entry).

**Amendment 6 — "ordering enforcement" is `05_DEPLOYMENT.md` §2.4's term for something else, and
reusing it here hides a missing guard.** §2.4's ordering enforcement is: "A profile switch with live
data cannot skip backup and restore. The harness greys out Launch until a current backup exists, and
states why." Stage 2 §3's ordering concern — seeding precedes any lock-holding service, the database is reset
first (stage 2a's cause five) — is real and belongs here, but it is not that guard, and a reader
ticking off §2.4's five guards would score it as covered. Renamed here to **seed-ordering
enforcement**; §2.4's guard is amendment 7's business.

**Amendment 7 — two of §2.4's five guards appear nowhere in Stage 2 §1–§7, and Phase 8's outcome bullet
claims all five** ("Harness-driven orchestration (`05_DEPLOYMENT.md` §2.4): target confirmation,
drift detection, change preview, enforced backup-before-switch, and downgrade capacity checks against
the existing data volume"). Missing: **target confirmation** (the resolved Docker context, or the
Kubernetes cluster, context and namespace, shown before every action and re-confirmed when it differs
from the last one) and the **capacity check** (a downgrade's preflight run against the *existing data
volume*, not the empty case, refusing if it will not fit). Also absent: the destroy path's own
asymmetry (typing the environment's name; stating what is not recoverable from backup, the audit
stream in particular). Target confirmation belongs in Stage 2 §3, alongside the thing it guards; the capacity
check and the backup-before-switch guard belong with Stage 2 §4, which is where a backup exists to check for.

**Amendment 8 — the component list is unstated, and one component the milestone-blocking preflight
check depends on does not exist anywhere.** §3 names what a `local-lite` launch must produce: "the
workspace, one Conduit, three workers, ArcadeDB, DuckDB in-process, Valkey, MinIO, OpenSearch
single-node, PostgreSQL, Keycloak, Ollama, and a faster-whisper container. Twelve containers."
`deploy/compose/dev.yaml` stands up four and names Keycloak only in a comment. The ADR-043 check
below cannot run until Stage 2 §1 renders a Keycloak service and this sub-stage starts it — which is
precisely why it is the *last* step here rather than a check anywhere earlier.

**Amendment 9 — §3's "The seeded demo credentials are displayed once and written nowhere" is a §2.5
property with no named test.** It belongs on this sub-stage's seed step.

**Amendment 26, from the owner's settlement of 24 September 2026 — ADR-043's two-sided
token-exchange check runs here, as the final step of the golden-path deploy.** Pulled forward from
`Stage 2 §7`, where the first draft of ruling 2 had left it: the post-launch `verify` step runs as
this deploy's last action, so **"reaches a health-checked stack" includes a verified token-exchange
grant**. `05_DEPLOYMENT.md` §2.5 is respected without exception, for the reason the owner gives:
it runs *after* Keycloak is up, against the deployment's own credentials, so the harness never holds
the secret. `Stage 2 §7` keeps the Re-check surface, for an operator re-running `verify` from the
admin console later. The check itself is unchanged — success for a disposable verify-only subject,
refusal for a deliberately out-of-scope one, with `07_BUILD_PLAN.md`'s stage entry's verbatim
operator wording on failure.

**The consequence this settles, which is the whole point of the pull-forward.** The earlier
placement left the grant unverifiable at the milestone, because `Stage 2 §7` is not
milestone-blocking. Folding it into this sub-stage's own exit test makes it milestone-blocking, since
this is Stage 2 exit test #2. That closes open item 2 as stated rather than deferring it.

**A reading flagged and then confirmed.** The owner's settlement named "Stage 2 §4's golden-path
deploy"; the golden-path deploy is **Stage 2 §3**, and `Stage 2 §4` is backup and restore. This
record read it as §3 — on the grounds that the phrase quoted in the same sentence, "reaches a
health-checked stack", is this sub-stage's own exit test verbatim, and that a token exchange has no
place in a backup→restore cycle — and flagged the reading rather than applying it silently. **The
owner confirmed §3 on 24 September 2026**: "The 'Stage 2 §4' in my previous message meant the
golden-path deploy; your reading of §3 is correct and stands." Kept here as a record of a
correction that was caught by flagging rather than by a later audit.

**Exit test, amended.** From a fresh clone, one command reaches a health-checked stack on
`local-lite`, **with ADR-043's two-sided exchange green as its final step**. **The CI half must name
its own stopping point** — which services must be healthy and which health checks must pass without
Ollama — because "runs in CI as far as CI can without Ollama" cannot fail: any CI failure is
attributable to "as far as CI can". Whether CI can reach the exchange at all depends on whether a
Keycloak container runs there, which the stopping point must state either way. This is Stage 2 exit
test #2.

#### Stage 2 §4 — Backup and restore

`python -m harness.backup` writes to `backups/<UTC-timestamp>-<profile>-<git-sha>/` with a
`manifest.json` naming every file, its checksum and the schema versions. `python -m harness.restore
<dir>` rebuilds the graph store from Parquet into an empty store and restores PostgreSQL.
`deploy/RUNBOOK.md` is created, stating the recovery time for each path (§6), measured on
`local-lite`.

**Amendment 10 — the backup set is short of §4's.** §4 step 1: "staged Parquet, **object store
contents**, Postgres dump, ontology, handling scheme, and `osprey.yaml`." The design listed staged
Parquet, a PostgreSQL dump and "the configuration". Object store contents (MinIO) is a distinct,
named item, not configuration. §6 additionally makes audit data an explicit exception — "not
rebuildable and… not deletable. Replicate it separately" — and Stage 2 §4 must state its disposition, because
§2.4's destroy confirmation depends on that being true.

**Amendment 11 — restore has no dry run, and §4 requires one.** "Restore opens with a dry run showing
the row count and a projected duration, and **will not proceed until that estimate is acknowledged**.
A national-scale replay is measured in days and must be planned, not discovered."

**Exit test, amended — the unamended one passes while the restore has lost everything that matters.**
"Node and edge multisets equal, a fixed query sample returns identical results" compares identity,
not payload. Three specific holes:

1. **Handling, provenance and assessment objects are first-class (ADR-010) and are what the adapter
   filters on (standing rule 3).** A restore that drops every `handling` marking passes a multiset
   comparison unchanged — and would silently widen access on the restored deployment.
2. **`SAME_AS` edges are scored, and resolution is a query-time projection over those scores
   (ADR-006).** A multiset of node/edge *pairs* that ignores edge properties passes while every
   projection changes. `ADR-035` §C5 already requires Fixture Corp to exercise τ 0.99/0.95/0.80
   producing visibly different projections; the restore test should compare those three projections,
   not a single query sample.
3. **The target store must be asserted empty.** §4 step 3 is "launch the new environment empty";
   nothing in the stated test distinguishes a restore into an empty store from a no-op against the
   source store.

This is Stage 2 exit test #1 and the stage's already-stated criterion.

#### Stage 2 §5 — split into §5a and §5b, owner's decision, 24 September 2026

**Why the split, in the owner's own reason: `Stage 2 §3` cannot start a stack whose images do not
exist.** The golden-path deploy's exit test is "from a fresh clone, one command reaches a
health-checked stack" — and the rendered compose file named `ghcr.io/ospreyflow/api:0.1.0` and two
siblings that no registry publishes. Packaging sat after §4 in the original ordering, so the one
thing §3 depends on would have been built two sub-stages after it.

- **`Stage 2 §5a` — runs now, before `Stage 2 §3`.** The deployable-service enumeration; the
  standing rule 8 repayment (a Dockerfile for whatever the enumeration finds deployable and
  lacking one); a Dockerfile for `apps/workspace`; and local image builds, so `docker compose
  build` produces every OspreyFlow-owned image with no registry involved.
- **`Stage 2 §5b` — stays after `Stage 2 §4`.** The bundle itself, ADR-035 §C1's distribution-class
  registry, and the ADR-034 §B7 / ADR-035 §C2 artefact scans. None of it is needed to start a
  stack, and all of it needs the backup/restore work §4 produces.

**Stage 2's three exit tests are unchanged** — the split reorders work, it does not re-scope the
stage. Test #3 ("each planted violation fails the bundle") remains §5b's.

#### Stage 2 §5a — the images the golden-path deploy needs

**BUILT, 24 September 2026, and its enumeration corrected a decision recorded in this record three
messages earlier.** `07_BUILD_PLAN.md`'s Stage 2 §5a entry has the full table, the build results and
the two findings raised as Proposed in `05_DEPLOYMENT.md` §3. The correction, because it is this
record's own: ruling 5 and amendment 20 state that `extract`, `resolve`, `compute` and `geocoder`
are "a violation of rule 8 by the phases that created them". **They are not.** The enumeration —
which the owner directed to run before any image was built, for exactly this purpose — finds all
four are libraries or an empty placeholder with no process entrypoint of any kind; they ship inside
the Conduit's image and never owed one of their own. Standing rule 8 says "each **service** gets its
Dockerfile", and a package that only ever runs inside another service's process is not a service in
that sense. **The one real rule 8 debt the enumeration found is `apps/workspace`** — the Glass, a
deployable process with no image from Phase 4 until this sub-stage — and it is repaid here. The
earlier wording is left in place above rather than edited away, because it was accepted and acted
on, and this is what correcting it looks like.

#### Stage 2 §5b — Packaging (the `osprey bundle` shape; D1, narrowed)

Builds the images for **each deployable service** and the bundle tarball; `--images` for air-gapped
install.

**This sub-stage's first task, before any packaging code: the service enumeration.** Enumerate the
six `services/` directories plus `apps/workspace`, state which are deployable and on what evidence,
and build the Dockerfile and `trivy image` CI job for each one that is deployable and lacks them —
as Stage 2 work, per the owner's narrowed D1 of 24 September 2026. The harness's own image
(`ghcr.io/ospreyflow/harness:latest`) is built here too, since `Stage 2 §6` cannot be bootstrapped by
its own documented `docker run` until it exists. Amendment 20 below has the starting evidence and
the `05_DEPLOYMENT.md` §3 "three workers" conflict the enumeration has to resolve; ruling 5 has the
standing-rule-8 exception this creates and which is flagged, not written.

**Amendment 12 — wrap `scripts/osprey_bundle.py`, do not write a second one.** It already exists, is
tested (`tests/test_osprey_bundle.py`, both directions), loads `osprey.yaml` through
`services/api/mapconfig_loader.load_map_config`, and raises `NonRedistributableProviderError` naming
every refused provider — `00_ARCHITECTURE.md` §1.2's "the bundle step refuses to package tiles or
gazetteers whose profile says `redistributable: false`, and names them." Its own docstring already
says: "The real `osprey bundle` command wraps `bundle_map_providers` below in Phase 8." Note also the
invocation convention: every existing operational module runs as `python -m scripts.<name>`
(this build's own Conventions); `python -m harness.<name>` is a second convention and should be adopted
deliberately, with `harness/__init__.py`'s own existing docstring as the warrant, rather than by
accident.

**Amendment 13 — ADR-035 §C1's registry is an input Stage 2 §5 cannot start without, and nothing builds it.**
Checked directly: `make demo-manifest` does not exist in `Makefile` or `package.json`; neither does
the `shipped`/`internal` manifest schema, the fail-closed registry, or the Glass's "dataset not
provisioned" state. `scripts/demo_guide_check.py`'s `DEMO_REGISTRY` is, in its own words, "a stand-in
for ADR-035's own still-unbuilt fail-closed registry, not the real thing". ADR-035 §C1's two
fail-closed tests are already named there and are Stage 2 §5's first deliverable, not a dependency it may
assume: `tests/demo_registry/test_fail_closed.py::test_a_manifest_with_no_distribution_field_is_
excluded_from_a_shipped_build` and `test_an_unrecognised_distribution_value_is_treated_as_internal`.

**Amendment 14 — §C2 names two required tests and the design's exit test covers one shape.** Both, per
C2's own words ("both required"): `tests/packaging/test_internal_demo_exclusion.py::test_reclassifying_
an_internal_demo_as_shipped_fails_if_its_data_remains` **and**
`test_removing_the_exclusion_step_itself_fails_the_gate`. The second is a mutation test on the gate
itself; "each planted violation fails the bundle" does not imply it, which is exactly why C2 named it
separately.

**Amendment 15 — there is no `.dockerignore` in this repository, and without one every assertion in
Stage 2 §5 is unenforceable.** Checked directly: no `.dockerignore` anywhere; two Dockerfiles exist
(`services/api/Dockerfile`, `services/ingest/Dockerfile`). ADR-035 §C2 already names the mechanism —
"if a packaging step copies the repository root, `/demo-data/`'s own gitignore exclusion is irrelevant
to what a `docker build` context includes unless the `Dockerfile` also excludes it (`.dockerignore`)".
A test written against the tarball alone goes green while every image layer carries the private tree.

**Amendment 16 — the private-tree exclusion must key off the existing marker list, never a path
prefix, and its test must survive Trigger A.** ADR-034 §B2: "a file's physical location in the private
working tree and its licence/publication status are independent facts about it, and this is the one
file in the tree where they visibly disagree" — `06_DECISIONS.md` lives in `spec/` and never
publishes. §B8: `spec/design/tokens.css` is product source despite sitting under `docs/`. So neither
`docs/` nor `spec/` is the right predicate. `scripts/product_tree_link_check.py` already holds the
authoritative marker list (`06_DECISIONS.md`, `07_BUILD_PLAN.md`, `CLAUDE.md`, `SESSION_HANDOVER.md`,
`NEXT_STEPS_PHASE7.md`, `DESIGN_PROVENANCE.md`, `PRODUCT_DELIVERY.md`, `archive/`), with
`route_coverage_check.py`'s `APACHE_DOC_PATHS` as its complement; Stage 2 §5 imports it rather than restating
it, the same way `product_tree_link_check.py` imports `APACHE_DOC_PATHS` rather than redeclaring it.
**The rule-15 trap this closes:** Stage 2 §5 is built *before* Trigger A, so a planted violation written
against today's `docs/`-rooted paths passes, and then silently becomes a no-op the moment Trigger A
renames the tree — a gate that could not find a violation if one existed. Trigger A's own exit
criterion should re-run Stage 2 §5's assertions for the same reason its existing criterion re-runs the
install.

**Amendment 17 — a new assertion nobody has named: `config/real_data_exceptions.yaml` must never
enter an artefact.** It is gitignored, never committed, names real datasets admitted under standing
rule 3 / standing rule 9 / ADR-035 §C3, and lives on the owner's own device — the same device an
owner-run demonstration build would be produced on. A `docker build .` from the repository root
includes gitignored files. ADR-034 §B7, ADR-035 §C2 and the submitted design all miss it. Its planted
violation is the real file's own shape (a valid entry naming a dataset), not a placeholder string.

**Amendment 18 — `--images` drops two properties §5 states.** "`osprey bundle --images` produces a
**signed** tarball of every image **and weight file** for transfer to a disconnected environment,
where the harness runs from the bundle rather than from a registry. **This path must be tested each
release**, because it is the path that will be needed under time pressure." §7 repeats the signing
requirement ("Images signed and verified at pull"). The design carried neither signing nor weight
files.

**Amendment 19 — `LICENSE`/`NOTICE` are Stage 2 §5's own deliverable, not a red test waiting on Trigger A.**
The design says this assertion "is expected red until that lands" while also making exit test #3 part
of a three-green stage exit — a self-contradiction. And the dependency runs the other way in the
plan's own text: ADR-034 §B7 is "**a blocking prerequisite of Phase 8's own harness/packaging work,
not a follow-up to it**", and for the two files, "the holder name, the licence text itself, and the
files' own presence are not year-dependent and are not deferred." Trigger A is stage 4 in Phase 8's
ordering and explicitly *not* milestone-blocking; stage 2 is. So Stage 2 §5 creates `LICENSE` and `NOTICE`
and builds the third `licence-check` leg the Trigger A entry already specifies — `LICENSE` present
and byte-identical to the canonical Apache 2.0 text, `NOTICE` present and containing "The OspreyFlow
Authors" — and Trigger A's own list records it as discharged early. **Only the copyright year stays
Trigger B's**, exactly as ADR-034 §B6 and the Trigger A entry already say; nothing here touches that.

**Amendment 20, rewritten 24 September 2026 for the narrowed D1 — `Stage 2 §5`'s first task is an
enumeration, and the missing Dockerfiles are this stage's work.** §2/§3's bootstrap is `docker run …
ghcr.io/ospreyflow/harness:latest`; nothing else in Stage 2 §1–§7 builds or publishes that image,
and Stage 2 §6 cannot be exercised by its own documented bootstrap until something does, so the
harness image is `Stage 2 §5`'s too.

**The enumeration task, with the evidence it starts from — checked directly, 24 September 2026, not
assumed from directory names.** `services/` has six directories and `apps/` has one:

| Directory | Dockerfile | Own entrypoint | Imported by `api`/`ingest` |
| --- | --- | --- | --- |
| `services/api` | yes | `app.py` (the Conduit, `uvicorn`) | — |
| `services/ingest` | yes | `__main__.py` (batch job) | — |
| `services/extract` | no | none found | yes |
| `services/resolve` | no | none found | yes |
| `services/compute` | no | none found | no |
| `services/geocoder` | no | none found | no |
| `apps/workspace` | no | a built static bundle, not a process | — |

**What that table settles and what it does not.** It settles that only two directories carry a
Dockerfile today and that `make ci` has `trivy-image-ingest` and `trivy-image-api` and no others. It
does **not** settle which directories are deployable, and this record does not decide it: four of
the six have no entrypoint of any kind today, which makes them library-shaped *as the tree stands*,
not necessarily library-shaped by design. The live tension the enumeration must resolve is named
here so the task starts from it rather than rediscovering it: **`05_DEPLOYMENT.md` §3 specifies that
`local-lite` runs "the workspace, one Conduit, **three workers**" — three worker processes — and the
tree contains exactly one worker entrypoint (`services/ingest/__main__.py`).** Either three of
`extract`/`resolve`/`compute`/`geocoder` become processes with their own images, or §3's component
count is wrong, and the enumeration is where that gets decided.

**Standing rule 8 — owner's decision, 24 September 2026: the rule stands unchanged, and this is a
repayment, not an exception.** An earlier draft of this amendment proposed that rule 8 gain a
recorded exception naming this stage. The owner declined that and ruled the other way, which is the
stronger reading and the one this record now carries. Rule 8 is unamended: "Each service gets its
Dockerfile, and a `trivy image` CI scan, in the phase that creates it — **never batched into Phase
8**."

**The four services without Dockerfiles — `extract`, `resolve`, `compute`, `geocoder` — are recorded
as a violation of standing rule 8 by the phases that created them.** Not a grey area and not a
Phase 8 batching exception: the rule was in force, each of those phases owed an image and a `trivy
image` job, and none delivered one. `Stage 2 §5` remedies it as a **one-time repayment of a recorded
debt**, which leaves the rule's own force intact for every future service — a phase that skips its
Dockerfile is still in violation, and cannot cite this stage as precedent for deferring one.

**The distinction is not bookkeeping.** An exception would have made "batch it into Phase 8" a
legitimate option next time; a repayment records that it was never legitimate and is being paid off
once. The difference shows up the moment a ninth service is created.

**A finding this stage must report before it builds any image.** The enumeration settles
`05_DEPLOYMENT.md` §3's "the workspace, one Conduit, **three workers**" against the tree's single
worker entrypoint (`services/ingest/__main__.py`) and **states which way it resolved** — either
three of the four become processes needing their own images, or §3's component count is wrong and
the specification is corrected. Reported as a finding first, imaged second; building four images
against an unexamined component count would answer the question by accident.

**Superseded, left visible because the earlier version was pushed and read:** this amendment
previously concluded that the missing Dockerfiles were "owed debt from earlier phases" and that
`Stage 2 §5` absorbing them "is the thing rule 8 exists to prevent". That followed from reading D1
as unnarrowed. The owner has corrected D1; the conclusion above replaces it.

`make licence-check` is extended per ADR-035 §C7 to data-file licences in the same pass, with its own
red-then-green in the family `tests/licence_check/test_licence_check_mjs.test.mjs` already
establishes.

**Exit test.** Each planted violation fails the bundle, each violation taking the shape the gate
actually receives at its own real call site. This is Stage 2 exit test #3.

#### Stage 2 §6 — The six setup screens

A browser application over Stage 2 §1–§5, bootstrapped by one Docker command, becoming `/admin` after launch.
Profile, Components and Models write `osprey.yaml` through the Stage 2 §1 schema. Governance writes
access-control/handling configuration and hosts the real-data exceptions panel (D2). Geospatial wraps
`build_local_basemap`, `register_tier4_provider` and the Verify step with progress shown. Preflight
streams Stage 2 §2's checks with per-check Re-check and gates Launch. Before Launch, the generated-artefacts
diff is shown and confirmed.

**The `decision_record` requirement is folded in, in the form ruling 3 gives it: required, validated
for presence and format only, never resolved.** This is the owner's decision of 24 September 2026 and
it removes the contradiction the first draft of this record objected to. Because nothing resolves the
reference, the Governance panel never reads `06_DECISIONS.md` — which is the file `Stage 2 §5`'s own
first assertion excludes from every artefact — so the field works identically on this working tree
and on a customer's deployment, which the resolving version could not.

**What "format only" means — accepted by the owner, 24 September 2026, and therefore the
specification rather than a reading of one:** a non-empty string matching an ADR reference, `ADR-`
followed by three digits, optionally with a section suffix (`ADR-035 §C3`). Presence and shape are
checked; existence, resolvability and correctness are not, and `is_permitted()` fails closed on a
missing or malformed value exactly as it does on any other missing required field.

**Two consequences that follow and are owed work, not discharged here.** `RealDataException`
(`scripts/real_data_exceptions.py`) has six required fields today and this makes a seventh, so any
entry already sitting in an owner's local, gitignored `config/real_data_exceptions.yaml` becomes
invalid until the field is added — a real migration step on a file no clone contains and no gate can
see, which is why it is stated here rather than assumed to be noticed. And the field needs its own
red-then-green: a fixture entry with the field absent, and one with it malformed, each shown to fail
closed. **Not built by this record** — this round amended documentation only.

**Amendment 21 — a new keyboard-driven surface needs its own action registry and spec file, in the
same change.** Standing rule 13, and the machinery that now enforces it:
`apps/workspace/keyboard/actionRegistry.ts`'s `defineActionRegistry`/`ALL_REGISTRIES`, a per-surface
`*.spec.ts` calling `assertAllCovered`, and `registryCoverage.test.ts`. (This sentence also named
`check-registry-coverage.mjs` until 25 September 2026. **No such file has ever existed** — the
static half it described is `registryCoverage.test.ts`, which does exist and does that job. The
citation was carried here from `actionRegistry.ts`'s own docstring, which had it too.)
Six screens with Launch, destroy, Re-check and diff-confirm actions is a new surface, and the design
names none of this. **The precise failure mode, because it is not the obvious one:**
`registryCoverage.test.ts` proves that every *declared* registry has an `assertAllCovered` call
somewhere — a surface that declares **no** registry is invisible to it. That is the same gap one
level up that the registry itself was built to close, and it is exactly the shape rule 12 names.

**Amendment 22 — every read path gets an access-control test, and `/admin` is a read path.**
Standing rule 4 / rule 2: "No exceptions for internal endpoints." `/admin` serves the
governance configuration, the handling scheme, the real-data exceptions panel and the
generated-artefacts diff — which carries real hostnames, ports, paths and credential *references*.
Stage 2 §6 must state which principal may open it and test that an unauthorised one cannot observe it or
infer its existence. Separately, §2.5's third constraint has no named test: "During setup it needs
the container socket; the admin console it becomes afterwards does not, and runs with the same
non-root, read-only-root posture as every other component (§7)." The privilege drop at the
setup→console transition is a testable invariant and nothing in the design tests it.

**Amendment 23 — the round-trip exit test misses the two properties §2.1 says make these screens
worth building as a UI at all.** "Every later screen filters its options to what is valid here" and
"**Consequences are shown, not described** — choosing `cluster` renders the machine count, the
components that appear, and the estimated memory footprint, updating as later screens change." Also
absent: "a persistent summary rail showing what has been decided and what is outstanding". A
round-trip through `osprey.yaml` is green with every option offered at every profile and no rail at
all.

**Amendment 24, from ruling 6 — `02_GLASS_FRONTEND.md` §6's accessibility floor applies to this
surface; §5's performance budget does not.** The owner's split, and the right one: §5 is defined
"against a 50k-node / 250k-edge working set" and measures canvas interactions a setup wizard does not
have, while §6 is written as a floor rather than a workload ("Not negotiable and cheaper to build in
than to retrofit"). The parts of §6 that reach these screens: every action reachable by keyboard with
Tab and Shift+Tab behaving like any other control and no focus trap; focus as a 2px brass outline at
2px offset, never suppressed; colour never the sole carrier; `prefers-reduced-motion` honoured; and
the contrast floor met in both themes, "verified with automated checks in CI, not by eye". The
canvas-specific bullets — the Matrix view as the screen-reader-navigable alternative, the ring-walk
key bindings — are about the canvas and do not transfer.

**It gates `make ci`, and it runs against the real screens — the owner's settlement of 24 September
2026, closing open item 1.** `Stage 2 §6` adds the harness's own accessibility test to `make ci`'s
target list, **never against a showcase page**. That second half is not a stylistic preference: this
build has already recorded an `axe-core` finding where the spec exercised a *showcase* page rather
than the real surface, and a harness a11y spec pointed at a mock of the six screens would repeat it
exactly — passing while saying nothing about what an operator actually meets.

**The precedent to copy, stated correctly — an earlier version of this paragraph got it wrong and
the correction matters.** `make glass-a11y` runs `apps/workspace/a11y/a11y.spec.ts`, an axe-core
DOM-rule check. This paragraph previously said that target is "not currently in `make ci`'s own
target list", implying the Glass's accessibility floor might not be gated in CI at all. **It is
gated**: `.github/workflows/ci.yml`'s own `glass-perf-a11y-keyboard` job runs `npm run test:a11y`
(alongside `test:perf` and `test:keyboard`) on every run. What is true is narrower and is a different
finding — `make ci` and `ci.yml` diverge on these three targets — and it is recorded where it
belongs, as a Stage 6 finding in `07_BUILD_PLAN.md`, not as a caveat on this sub-stage. The harness
needs its own spec rather than an extension of the Glass's, being a separate application, and under
this settlement it is wired into **both** `make ci` and the workflow, so the divergence is not
reproduced for a third surface.

**Exit, two parts, stated separately.** *Test:* every screen round-trips its answers through
`osprey.yaml`; the rendered output matches Stage 2 §1's fixture for the same answers; option filtering
by profile is asserted; the new surface's action registry is declared and asserted covered; `/admin`
has its access-control test; and `02_GLASS_FRONTEND.md` §6's floor is asserted against the real
screens by this surface's own a11y spec (ruling 6). `02_GLASS_FRONTEND.md` §5's performance budget is
explicitly **out of scope** for this surface, per the same ruling. *Judgement:* a usability pass by
someone other than the builder, recorded as the plan already words it — "Whether the six setup
screens are actually usable by an operator who has never seen them is a judgement, not a test."
Retained unchanged; no finding.

#### Stage 2 §7 — Post-launch admin console operations

Rolling upgrade and rollback to a previous digest (`05_DEPLOYMENT.md` §5). **Not milestone-blocking
— still Phase 8.** The design said "explicitly AFTER the milestone", which is right about the
milestone and wrong about the phase: Phase 8's own outcome bullet claims "the backup, restore,
**upgrade and verify** screens", and §5's `verify` is a capability nothing else in Stage 2 §1–§7
provides — "the port conformance suite against the **running** deployment rather than a test
fixture". Worded here the way the plan words every other such stage. Note also that Stage 2 §7's
rollback consumes `versions.lock`, which is amendment 1's business in Stage 2 §1, not Stage 2 §7's.

**Amendment 25, rewritten 24 September 2026 — this sub-stage keeps the Re-check *surface* for
ADR-043's two-sided check; the check's own first run moved to `Stage 2 §3`.** Ruling 2 moved the
check out of pre-launch Preflight into `verify`; the owner's settlement then pulled `verify`'s
ADR-043 pair forward to run as the last step of the golden-path deploy, so the grant is verified
before the milestone rather than after it. What stays here is the post-launch re-run: an operator
opening the admin console can trigger `verify` again — after a realm change, an IdP upgrade, or a
`"stopped"` watch nobody can explain — and see the same two results. The check is the same one, run
from the same code, at a later moment; it is not a second implementation.

**Why `verify` is the right home for the mechanism either way.** It runs against the **running**
deployment, where a Conduit holding the confidential client's credentials already exists — so the
harness never handles the secret and §2.5's second constraint holds without exception. That property
is what made the pull-forward safe rather than a reversal of ruling 2.

**Its own exit test** (owned by `Stage 2 §3`, where it first runs, and exercised again here): both
sides red-then-green against an ephemeral RFC 8693 token-endpoint fixture — the same "a real, if
ephemeral, HTTP server rather than a mock" precedent ADR-043 sets, and for its own stated reason,
since a mock cannot exercise the refusal path the containment actually rests on.

---

### Stage 2's exit (D3 — owner's decision, 24 September 2026)

Tests #1, #2 and #3 green. **This is Stage 2's own completion, not ADR-042's alpha gate, which
additionally requires both acceptance scenarios green on `local-lite`; no build goes to a tester on
Stage 2 alone.**

---

### Owner's rulings on the seven objections — 24 September 2026

All seven answered by the owner directly, in their own words, the same day the objections were
written. Each ruling below states what was decided and what it changed above; none is a paraphrase
standing in for a decision the owner did not make. **Two were answered by pointing at a D-decision
rather than by restating one** (4 → D2, 5 → D1), which resolves them because both objections were
written as disjunctions — confirming the D-decision as stated picks one horn and eliminates the
other. That inference is recorded here rather than applied silently, so it can be corrected in a
line if it is not what was meant.

1. **Labels — ruled: the harness sub-stages are `Stage 2 §1`–`Stage 2 §7`; `2a` stays as the closed
   sibling stage.** Applied throughout this record and `07_BUILD_PLAN.md`. The collision the
   objection named is gone: `2a` keeps both its label and its meaning as an independent stage, and
   nothing now reads as its continuation. **One thing the new scheme costs, handled rather than
   absorbed:** `§N` already means "specification section" in all three of these documents, and the
   two forms collide in sentences that carry both. The sub-stage form is therefore always written in
   full (`Stage 2 §5`, never a bare `§5`), stated as a rule of this record at "The sub-stages as
   amended" above. Old-label mapping, for commits and reports predating this ruling: `2b`→`Stage 2 §1`,
   and so on in order to `2h`→`Stage 2 §7`.

2. **The ADR-043 two-sided exchange — ruled: approved; move it to the post-launch verify step,
   surfaced through Preflight's Re-check after launch; amend the plan's stage entry.** Applied.
   The check is out of `Stage 2 §2`'s pre-launch list; its implementation is amendment 25 under
   `Stage 2 §7`'s verify capability; its surface stays the Preflight screen, as a post-launch item
   with Re-check and the stage entry's own verbatim operator wording. `07_BUILD_PLAN.md`'s stage
   entry is amended in the same change, as the ruling directs. §2.5's "never sees a secret" now holds
   without exception, because the exchange runs where the credentials already are. **The consequence
   this creates is recorded at `Stage 2 §2`, not buried here:** `Stage 2 §7` is not
   milestone-blocking, so the milestone can now be reached with the ADR-043 grant unverified. That
   follows from the ruling; pulling this one check forward, if wanted, is a separate call.

3. **`decision_record` — ruled: it stays a required field, validated for presence and format only,
   never resolved.** Applied at `Stage 2 §6`. This answers the objection rather than overriding it:
   problem (a), the one the objection actually turned on, disappears entirely, because a field that
   is never resolved never reads `06_DECISIONS.md` and so never depends on a file `Stage 2 §5` is
   required to exclude. The mechanism now behaves identically on this working tree and on a
   customer's deployment. Problems (b) and (c) are not objections any more but consequences the owner
   has accepted, and both are recorded as owed work at `Stage 2 §6`: the seventh required field
   invalidates any entry already in a local `config/real_data_exceptions.yaml` until it is added — a
   migration on a file no clone contains and no gate can see — and the field needs its own
   fail-closed red-then-green for the absent and the malformed case. **Not built by this record.**
   What "format" means is this record's own reading (`ADR-` plus three digits, optional section
   suffix), flagged as such at `Stage 2 §6` so it is corrected rather than inherited if wrong.

4. **The "a new screen" contradiction — ruled: see D2.** D2 stands as written, so the exceptions list
   is a panel on Governance. `07_BUILD_PLAN.md`'s Phase 8 outcome bullet is amended from "**A new
   screen**, added 23 September 2026: managing the real-data exceptions list" to the panel wording,
   in the same change as this record. `05_DEPLOYMENT.md` §2.1's "Six screens" table needed no edit —
   it already said six, which is why the objection existed.

5. **Standing rule 8 and D1's scope — re-derived 24 September 2026 from the owner's correction to
   D1; the first derivation is superseded.** The owner's original "see D1" was read here as
   confirming D1 *unnarrowed*, which eliminated the objection's second horn and left the first:
   "the missing Dockerfiles are owed debt from the phases that created those services". **That was
   not the intent, and the conclusion is withdrawn.** D1 is confirmed **narrowed** — "each
   *deployable* service" — which takes the *other* horn: **`Stage 2 §5`'s first task enumerates the
   six service directories, states which are deployable, and builds the missing Dockerfiles as
   Stage 2 work, not as debt owed by earlier phases.** The enumeration's own starting evidence —
   which directories carry a Dockerfile, which have an entrypoint, and the live conflict between
   `05_DEPLOYMENT.md` §3's "three workers" and the single worker entrypoint in the tree — is
   tabulated at amendment 20 above rather than repeated here.

   **Settled 24 September 2026, and the other way round from how this record first proposed it.**
   An earlier draft asked for standing rule 8 to gain a recorded exception naming this stage. The
   owner declined: **rule 8 stands unchanged, and the four services without Dockerfiles —
   `extract`, `resolve`, `compute`, `geocoder` — are recorded as a violation of it by the phases
   that created them, remedied in `Stage 2 §5` as a one-time repayment.** That keeps the rule's
   force intact for every future service, which an exception would have quietly spent. Amendment 20
   above has the reasoning and the finding the enumeration must report before it builds anything.

6. **The two Glass gates — ruled: `02_GLASS_FRONTEND.md` §6's accessibility floor applies to the
   harness application; §5's performance budget does not.** Applied as amendment 24 at `Stage 2 §6`,
   with the floor in that surface's own exit test and the budget named as explicitly out of scope.
   Two practical notes recorded with it, both checked: `make glass-a11y` is not in `make ci`'s own
   target list today, so "the floor applies" leaves the separate question of whether the harness's
   equivalent gates CI; and this build has already recorded an `axe-core` finding where the spec
   exercised a showcase page rather than the real surface, which is the failure the harness's own
   a11y spec must not repeat.

7. **D3's widening — ruled: confirmed; the widening is deliberate.** Stage 2's exit is tests #1, #2
   and #3, not the single backup→restore criterion the stage entry carried before. Recorded at
   "Stage 2's exit" above and in `07_BUILD_PLAN.md`'s stage entry, in both cases as a deliberate
   widening rather than a clarification of what was already there.

### The four open items — all settled by the owner, 24 September 2026

Each was listed as open by the previous version of this record; each is closed here by the owner's
own settlement, not by this record deciding it.

1. **The harness accessibility test gates `make ci`** — `Stage 2 §6` adds it, run against the real
   screens, never a showcase page. Applied at amendment 24. Separately, and recorded where it
   belongs rather than as a caveat here: **`make glass-a11y` is not in `make ci`'s target list,
   while `.github/workflows/ci.yml`'s `glass-perf-a11y-keyboard` job does run it** — a `make
   ci`/`ci.yml` divergence covering `glass-perf`, `glass-a11y` and `glass-keyboard`, filed as a
   Stage 6 finding in `07_BUILD_PLAN.md`. Worth its own entry because the `Makefile`/`ci.yml`
   reconciliation is already recorded as *built* (22 September 2026, pulled forward from Stage 6),
   and these three targets fell outside it.
2. **The ADR-043 two-sided check is pulled forward** — the post-launch `verify` runs as the final
   step of the golden-path deploy, so "reaches a health-checked stack" includes a verified grant, and
   the check becomes milestone-blocking through that sub-stage's own exit test #2. `Stage 2 §7` keeps
   the Re-check surface. §2.5 holds because it runs after Keycloak is up, against the deployment's
   own credentials. Applied at amendment 26, with one reading flagged there: the settlement names
   "Stage 2 §4's golden-path deploy" and the golden-path deploy is `Stage 2 §3`.
3. **The Dockerfile question** — settled by the correction to D1, re-derived at ruling 5 and
   amendment 20. Not debt; `Stage 2 §5`'s own first task.
4. **The `decision_record` format reading** — `ADR-` plus three digits, optional section suffix —
   **accepted by the owner as written.** No longer this record's reading; it is the specification,
   and `Stage 2 §6` states it as such.

**What remained after those four — one item, now also settled.** The narrowed D1 appeared to need an
exception to standing rule 8. The owner ruled on 24 September 2026 that **rule 8 stands unchanged**
and the four undockerised services are a recorded rule-8 violation by their own creating phases,
repaid once in `Stage 2 §5`. Nothing under this heading is open; the record was accepted the same
day.

**Cost.** Documentation across three sessions. If accepted, `Stage 2 §5` grows three deliverables it
did not have (ADR-035 §C1's registry; `LICENSE`/`NOTICE` and the third `licence-check` leg; the
service enumeration and the Dockerfiles it finds missing, including the harness's own image),
`Stage 2 §1` grows two artefact kinds, `Stage 2 §2` grows the reduced-variant offer and loses the
ADR-043 check, `Stage 2 §3` grows that check as its final step, `Stage 2 §3` and `Stage 2 §4` grow
three of §2.4's guards between them, `Stage 2 §6` grows an action registry, a spec file, an
access-control test and a CI-gating a11y spec, and `Stage 2 §7` keeps the Re-check surface. Only the
Dockerfiles are newly-claimed scope, and that is the correction to D1 doing its work deliberately —
everything else is already claimed by `05_DEPLOYMENT.md`, by Phase 8's own outcome bullets, or by an
accepted ADR;
the amendments move it from claimed to sub-staged.

**Revisit if.** Standing rule 8 gains (or is refused) the recorded exception the narrowed D1 needs,
`Stage 2 §5`'s enumeration settles which services are deployable, or the owner promotes this record
to Accepted — each is written so settling it is a targeted edit to this record and its
`07_BUILD_PLAN.md` stage entry, not a new ADR.

---

## ADR-050 — Sign-in for the Glass: OIDC authorization code with PKCE

**Status: Accepted, 25 September 2026, with five amendments. Milestone-blocking.** The owner's
ruling of 25 September 2026: the three blocking objections below (1, 2, 3) are upheld and resolved
as each one's own entry now records, and two amendments are accepted — the "no refresh token,
re-fetch on expiry" design of objection 5, and the reworded rule-4 test of objection 7. Objections 8
and 9 are not addressed by this ruling and remain open, tracked below; neither is one of the three
blocking objections, so neither holds up acceptance.

**Not built. No part of this record has been implemented.** The ruling accepts the design; it does
not build it. The sign-in stage entry in `07_BUILD_PLAN.md` is where that work is scoped.

### Context: what is actually there today

Measured against the tree on 25 September 2026, not assumed:

- `apps/workspace/src/App.tsx` reads `import.meta.env.VITE_DEV_BEARER_TOKEN ?? ""` and sends it as
  a bearer on every call. Its own comment has said since Phase 4 that this is "a stand-in until a
  real sign-in screen exists, not a production auth path". **No phase has owned the replacement.**
- The rendered realm (`harness/realm.py`) contains exactly two clients, `osprey-conduit` and
  `osprey-unprivileged`. **Both are confidential** (`publicClient: False`) and **both have
  `standardFlowEnabled: False`** — there is no browser flow in the realm at all.
- It contains two users, `osprey-verify-probe` (enabled) and `osprey-verify-revoked` (disabled).
  **Neither has a `credentials` block.** They exist to be impersonated through token exchange.
- The Conduit verifies a token with `jwt.decode(..., options={"verify_aud": self._config.
  oidc_audience is not None})`, and the rendered deployment sets no `OIDC_AUDIENCE`, so
  **audience verification is off**.
- The delta WebSocket authenticates from a `?token=` query parameter, because a browser's native
  `WebSocket` cannot set a header. `_authenticate_websocket`'s own docstring names the resulting
  log exposure and names a ticket exchange as "the production hardening this phase does not
  implement".
- Keyboard coverage is no longer the hardcoded walkthrough standing rule 13 describes. There is a
  per-surface `defineActionRegistry` / `registerCovered` / `assertAllCovered` mechanism, plus
  `registryCoverage.test.ts`, a Vitest case in the fast tier that fails when a declared registry
  has no assertion reaching it.

### Decision

**Flow.** OIDC authorization code with PKCE (S256) against the deployment's own realm, the Glass
registered as a **public** client — no secret in the browser. The redirect URI is the workspace's
own origin, which since §2.6.1 is also the Conduit's origin, so one value covers both.

**Tokens.** The access token is held in memory only. **No refresh token is stored anywhere** — see
objection 5 for why the original "sessionStorage only if rotation is on" is rejected. Re-authentication
uses a silent `prompt=none` authorization request against the Keycloak session cookie, which keeps
the long-lived credential in the IdP's own cookie rather than in storage the page can read.

**Claims.** The Glass reads `sub`, `clearance`, `org_unit`, `roles` and `receivable_handling_codes`
— the four custom claims the realm already maps, plus `sub` — and displays the principal's identity
and clearance in the workspace chrome. **It never derives access from them.** Standing rule 3
stands unchanged: the adapter-level filter is the only enforcement and the Glass's display is
informational. A Glass that hid a control because `roles` lacked an entry would be enforcement in
the wrong tier; a Glass that showed one it should not is not a leak, because the Conduit refuses.

**Expiry — amended by the owner's ruling, 25 September 2026.** No refresh token is held in the
browser; expiry is a fresh authorization-code round (the `prompt=none` silent request against the
Keycloak session cookie, above). On expiry the Glass preserves only identifiers — the
**investigation id, the selection and the view state** — and **re-fetches** the working set from
the Conduit rather than preserving it; see objection 6. No silent loss and no silent continuation on
a stale token. The delta WebSocket re-authenticates on reconnect.

**Relation to ADR-043, stated so the two are never conflated.** The Glass sends **the analyst's own
token**. ADR-043's token exchange is for **watch owners only** — the Conduit acting as a principal
who is not present — and is never used for the interactive caller. They are different mechanisms
answering different questions, and the only thing they share is the realm. ADR-043's amendment
(the Conduit's own view-users pre-check for a disabled subject) applies to the exchange path only;
an interactive sign-in by a disabled user is refused by Keycloak's own login, which is a refusal the
realm *does* enforce.

**ADR-044's distinction carries to the Glass.** A failed re-authentication because the IdP is
unreachable must not present as "your access was revoked". The Glass distinguishes *cannot reach
the identity provider* from *the identity provider said no*, for the same reason ADR-044 does
server-side: one is an outage and the other is a decision about a person, and telling an analyst
the second when the first is true is a false and alarming statement.

**Dev token.** The `VITE_DEV_BEARER_TOKEN` path survives **only** for `npm run dev`. A production
build with it set fails the build.

**Sign-out.** Clears memory and any session storage the Glass owns, then ends the Keycloak session
via `end_session_endpoint` with `id_token_hint` and a registered `post_logout_redirect_uri`.

### What the realm renderer must gain

None of this exists today and all of it is rendering work, not Glass work:

1. A third client — public, `standardFlowEnabled: true`, `attributes: {"pkce.code.challenge.method":
   "S256"}`, with the four claim mappers the Conduit's client already has.
2. `redirectUris` and `webOrigins` for the workspace's origin. **The renderer does not know that
   origin today** — the published port comes from `OSPREY_WORKSPACE_PORT`, an environment override
   read at `docker compose` time, not from `osprey.yaml`. See objection 2.
3. `post_logout_redirect_uris` for sign-out.
4. `OIDC_AUDIENCE` in the deployment's environment, and the client's own audience mapper. See
   objection 1.
5. A subject that can actually sign in. See objection 3.

### Tests owed

- **Rule 3, restated as a test rather than a promise**: the Glass displays `clearance` and never
  branches on it. The test that fails if this is violated is a case asserting that a principal with
  a *lower* clearance sees the same controls, and differs only in what the Conduit returns.
- **The Glass's reaction to a 401**, which is the new behaviour: an unauthenticated load presents
  the sign-in, not an error page and not an empty workspace. See objection 7 on why the
  design's original wording for this was vacuous.
- **Rule 13**: the sign-in screen is a **new keyboard-driven surface** and needs its own
  `defineActionRegistry` with `assertAllCovered`, not entries in `CANVAS_ACTIONS`.
  `registryCoverage.test.ts` fails otherwise.
- **The accessibility floor** (`02_GLASS_FRONTEND.md` §6) on the sign-in screen.
- **Rule 15 on the dev-token fence**: plant `VITE_DEV_BEARER_TOKEN` in a production build and
  assert the build fails. The planted value must take the shape the real pipeline receives — an
  environment variable present at `vite build` — not a source edit.
- **The golden path's Glass leg becomes**: apply, open the printed URL, sign in, see the seeded
  investigation. It replaces the dev-token step used for the last time on 25 September 2026,
  in that day's own internal rehearsal record.

### Open objections

**Blocking — the design cannot be built as written until these are settled.**

**1 (blocking). The Conduit does not verify the audience, and a public client is what makes that
reachable.** `OIDC_AUDIENCE` is unset in every rendered deployment, so `verify_aud` is `False` and
the Conduit accepts **any token the realm signs**. Today that is survivable because the only
clients are two confidential ones we control. A public client changes the reachable set: and
`harness/realm.py` says in its own words that "a production realm is the operator's", so the
expected production case is a **shared** realm. In one, a token minted for an unrelated application
in the same realm is accepted by the Conduit as a principal — it has a `sub`, and if the operator's
realm maps the four claims for its own reasons, it resolves to a `Principal` with a clearance. That
is an access-control hole that ADR-050 would open, and the remedy is small: render `OIDC_AUDIENCE`,
add an audience mapper to the Glass client, and make the resolver's `verify_aud` unconditional.
**It should be fixed before sign-in ships, and arguably before that, on its own merits.**

**Resolved, 25 September 2026 (owner's ruling).** The remedy above is accepted as written: the
Conduit verifies audience in every rendered deployment — `OIDC_AUDIENCE` set to the Conduit's client
id, an audience mapper on the Glass client, `verify_aud` on. A token the realm signs for another
client is refused.

**2 (blocking). The renderer cannot know the redirect URI.** A public client's `redirectUris` must
match the browser's origin exactly, and Keycloak refuses a mismatch — correctly, because a loose
redirect URI is how authorization codes get stolen. The workspace's published port comes from
`OSPREY_WORKSPACE_PORT`, an environment variable read by `docker compose`, and the realm is
rendered before that is known. Three ways out, none chosen: move the published ports into
`osprey.yaml` so the renderer knows them (cleanest, and it makes `05_DEPLOYMENT.md` §3's table a
rendered artefact rather than prose); render a wildcard for `local-lite` only (Keycloak permits
`http://localhost:*` patterns, and it is exactly the looseness that makes this dangerous
elsewhere); or configure the client after import, the way `keycloak_admin.py` already grants the
service-account roles a realm import cannot express. **The third is most consistent with what the
harness already does and is the recommendation, but it is the owner's to take.**

**Resolved, 25 September 2026 (owner's ruling) — none of the three above; a fourth.** The realm is
rendered at apply time from the resolved environment, not before it — `osprey.yaml` gains
`network.public_origin`, and the redirect URI derives from it. No wildcard redirect URIs.

**3 (blocking). The exit test as designed cannot pass: the subject it names cannot sign in.** The
design says "sign in as the disposable analyst subject the realm already renders".
`osprey-verify-probe` has attributes and **no credentials** — it is not a login, it is an
impersonation target. Giving it a password means writing a password into the rendered realm
document, and `05_DEPLOYMENT.md` §2.5 and §7 are categorical that the harness "never sees a secret"
and that secrets are "never in `osprey.yaml`, never in an image". A generated-at-apply-time password
written into the gitignored environment file, as the client secret already is, is the shape that
fits — but it is a **new** subject, not this one, because of objection 4.

**Resolved, 25 September 2026 (owner's ruling) — the shape above, as a named apply flag.** Apply
gains `--demo-analyst`: a disposable analyst account with an apply-time password in the env file,
absent by default. The exit test and the demo use it. This is the new subject objection 4 calls
for, not `osprey-verify-probe` — objection 4 is resolved as the same side-effect.

**Non-blocking, but each changes the design.**

**4. Reusing the verify subject for interactive sign-in conflates two things ADR-043's amendment
deliberately separated.** `osprey-verify-probe` exists to make the three-sided verify's assertion 1
meaningful. If the same subject also becomes the demo analyst, then any change to its clearance or
handling codes — a perfectly reasonable thing to want for a demonstration — silently changes what
verify asserts. They should be two subjects with two purposes. The cost is one more rendered user.

**5. "Refresh token in sessionStorage only if Keycloak's refresh rotation is on" is a condition the
Glass cannot evaluate, and the wrong lever.** Whether rotation is on is a realm setting; the Glass
would have to discover it, and a deployment against an operator's realm may not know. Worse, the
conditional puts the decision in the wrong place — **we render the realm**, so rotation is ours to
set, not to detect. And rotation reduces the value of a stolen refresh token without removing it;
`sessionStorage` is readable by any script on the origin, which after §2.6.1 is the same origin
that serves the API. The amended design above stores **no refresh token at all** and re-authenticates
silently against the IdP session cookie instead. That is a real change to the design, made because
I am confident of it; say so if you disagree.

**Accepted, 25 September 2026 (owner's ruling).** No refresh token is held in the browser; expiry is
a fresh authorization-code round, as amended in the Decision's own Expiry paragraph above.

**6. Preserving the working set in `sessionStorage` risks a quota failure at the worst moment.**
`sessionStorage` is about 5 MB and the working set is capped in the thousands of nodes with
provenance, handling and assessment objects on each. A `QuotaExceededError` during a token expiry
would lose the working set **and** throw, which is the "silent truncation" rule 2 forbids wearing a
different hat. The amended design preserves the investigation id and the selection — both small and
both sufficient to restore the view — and re-fetches the rest. If preserving the working set
verbatim is wanted, it needs IndexedDB and a size policy, which is its own decision.

**Resolved, 25 September 2026 (owner's ruling).** The amended design stands, with view state added
to what is preserved: investigation id, selection and view state, re-fetching the rest — see the
Decision's own Expiry paragraph above, and `00_ARCHITECTURE.md` §1.3's amended expiry sentence,
where the contested mark comes off.

**7. The rule-4 test as worded is vacuous, and it is not rule 4.** "An unauthenticated Glass request
to any `/v1` route is refused" is the **Conduit's** behaviour and is already covered for every read
path; a test written to that wording would pass without a single line of ADR-050 existing. The
assertion that has content is the second half — *the Glass shows the sign-in* — which is a Glass
test, not an access-control test. Rule 4's name on it invites someone to satisfy it by testing the
Conduit and moving on. The tests-owed list above splits them.

**Resolved, 25 September 2026 (owner's ruling).** The rule-4 test is reworded as proposed here, so
that it cannot pass without the sign-in code: the tests-owed list's second bullet (the Glass's
reaction to a 401) is the access-control assertion with content, not the already-covered Conduit
behaviour.

**8 (raised, not resolved). Sign-in is when the token in the WebSocket URL stops being a
development concern.** Measured on 25 September 2026 during the same-origin verification: the full
access token appears in the workspace's nginx access log, and §7 puts a TLS-terminating reverse
proxy in front of that, which will log it again. `_authenticate_websocket` already names a
short-lived single-use ticket as the fix and says this phase does not implement it. **ADR-050 is
the phase where a real analyst's token starts travelling that path**, and the recommendation is to
build the ticket exchange as part of it. It is listed as an objection rather than folded into the
decision because it enlarges the scope meaningfully and that is the owner's call.

**9 (spec gap, not an objection). `02_GLASS_FRONTEND.md` does not describe the workspace chrome
element this design puts the principal's identity and clearance into.** Adding a Glass surface by
ADR rather than by specification is the thing standing rule 11 exists to prevent. Either §2 of
that document gains the element, or this design should not name it.

### Consequences

**Accepted as amended, 25 September 2026:** the dev-token path is fenced and then deleted, the
milestone's Glass leg becomes demonstrable for the first time, and the audience hole in objection 1
is closed as a side-effect. The realm renderer grows a third client, a second subject
(`--demo-analyst`) and a post-import configuration step.

**Before this ruling, objections 1–3 each independently prevented the exit test from passing** —
1 would have shipped a deployment that accepts tokens it should not; 2 would have failed the flow
at the redirect; 3 would have left the exit test unrunnable. Each is resolved above.

**Revisit if:** `02_GLASS_FRONTEND.md` gains the chrome element of objection 9 (still open — this
ruling does not address it). Objection 8 (the WebSocket ticket exchange) is resolved by the
addendum below — built, 25 September 2026. Each is written so that settling it is a targeted edit
to this record and its `07_BUILD_PLAN.md` stage entry, not a new ADR.

**Addendum, 25 September 2026 — built, this round, against the design above; `07_BUILD_PLAN.md`'s
Stage 2c entry has the full built/remaining breakdown and the exit test's own result.** In one line
each: audience verification unconditional whenever `OIDC_AUDIENCE` is configured, and every rendered
deployment now configures it (`harness/render.py`'s `_render_env`, gated at Launch by
`harness/preflight/oidc_audience.py`); the realm renderer gains the Glass's public PKCE client with
an audience mapper naming the Conduit, and `--demo-analyst` renders and passwords a disposable
sign-in-capable subject, separate from the verify probe; the Glass gains a real OIDC authorization-
code-with-PKCE flow (`oidc-client-ts`, Apache-2.0), the sign-in screen, the identity/clearance chrome
(objection 9, **closed** — `02_GLASS_FRONTEND.md` §2 now names it, rather than this ADR being the
only place it was decided), and the dev-token build-time fence; the delta WebSocket re-authenticates
on every reconnect, keyed to the current token.

**Objection 8 (the WebSocket ticket exchange) — BUILT, 25 September 2026, the owner's own decision
of that date to build it before the closing pass.** `POST /v1/ws-ticket` (authenticated the
ordinary way) mints a random, single-use, 30-second value bound to the calling principal
(`services/api/ws_ticket.py`), stored in Valkey rather than in process memory for the same
statelessness reason the delta channel's own pub/sub already lives there. The stream opens with
`?ticket=...`; a bearer token in that URL is now refused outright, not merely deprioritised —
`_authenticate_websocket` reads a `ticket` query parameter, and there is no `token` fallback left
to fall into. Redemption is `Valkey.GETDEL`, an atomic get-and-delete: single-use is a property of
the operation, not a policy a second caller could race past. Named tests: a reused ticket refused
(`test_a_reused_ticket_is_refused`, live Valkey), an unauthenticated mint refused
(`test_an_unauthenticated_request_is_refused`), a bearer token in the stream URL refused
(`test_a_bearer_token_in_the_url_is_refused_not_merely_deprioritised`, planted as the literal
request shape Checkpoint 2's own client used to send), and removing the redemption check's own
`None`-check verified red (a fallback principal in place of the refusal) before being restored
green. `07_BUILD_PLAN.md`'s Stage 2c entry has the full built/remaining account.

**One design point this ADR's own text left unsettled, decided during the build and recorded
honestly rather than silently:** how the Glass, whose bundle carries no baked address for the
Conduit, locates the identity provider for OIDC discovery. `00_ARCHITECTURE.md` §1.3 already
states two separately reachable origins ("Only the workspace and the identity provider"), so the
identity provider is reached **directly at its own published origin**, not proxied through the
workspace's nginx — `apps/workspace/src/auth/oidcConfig.ts` derives it from the browser's own
hostname plus `05_DEPLOYMENT.md` §3's default Keycloak port (8081), overridable at build time via
`VITE_OIDC_ISSUER_ORIGIN` for a deployment that has moved it. Folding Keycloak's own login pages
behind the same-origin proxy the Conduit uses was considered and rejected for this round: it would
need `KC_HTTP_RELATIVE_PATH` set to match on the server side too, touching every existing internal
Keycloak URL this codebase already has, for a benefit (one fewer published port) this round did not
need.

**The exit test — run for real, five iterations to green — is green, with both named mutations
proven.** `07_BUILD_PLAN.md`'s Stage 2c entry has the full account, including five real defects the
apply run and the Playwright walkthrough found that no unit-level test had a way to reach: a realm
field Keycloak does not define (`postLogoutRedirectUris`), an audience mapper that needs to sit on
the Conduit's own client and not only the Glass's, an investigation-id-persistence effect gated on
auth when it should not have been, Keycloak's own default profile-completion wall on a fresh
admin-API subject, and two access-control attributes (handling code, `org_unit`) the demo analyst
needed and did not have. Each is fixed, each has a named test.

## ADR-051 — Sign in first, then show the interfaces the role allows

**Status: Accepted, 29 September 2026, by the owner's ruling (Option C, with E1). Design only: the
sign-in flow, the second demo account, the Admin console's enforcement and the launcher's
role-filtered tiles are not built.** What is built is listed under "State of the build" below and
nothing else in this record is implemented.

### Context: what was seen

The launcher (`make launch`, `scripts/launch.py`) offers three interfaces: the Glass, Ingest Studio
and the Admin console. It shows all three to anyone who reaches it. The owner asked that the user
be asked to sign in first, and shown only the interfaces their role allows. Measured on 29 September
2026:

- The realm has no sign-in for the launcher and no administrator subject. Only `osprey-glass` is a
  public browser client; `osprey-demo-analyst` holds roles `analyst`, `source_author`,
  `source_approver` and `loader`, and no `osprey-admin`.
- The Admin console (the harness on port 7000) has `require_admin_role`, but in its setup mode it is
  unauthenticated and loopback-only by design. A launcher that merely hid its tile would leave the
  address itself open to anyone on the machine.
- ADR-050 already rules that the Glass never derives access from roles; the Conduit enforces. A
  launcher that hides tiles is therefore a convenience for the person signed in and **is not an
  access control**. Any recommendation that made it one was wrong, and one made earlier in this
  work (Option B, below) was withdrawn on exactly that ground.

### Decision

**1. Sign in first (Option C).** The launcher shows a start screen before sign-in and a role-filtered
page after it. Sign-in is OIDC authorization code with PKCE against the deployment's own realm,
using a new **public** client, `osprey-launcher`, redirecting to the launcher's own loopback origin
(port 7070). No secret is held by the launcher's browser page. The shared OIDC code lives once, in
`harness/oidc.py`, and the launcher and the Admin console both use it.

**2. Which role shows which tile.**

| Tile | Shown to |
| --- | --- |
| The Glass | any signed-in user |
| Ingest Studio | a user holding any Studio role (`source_author`, `source_approver` or `loader`) |
| Admin console | a user holding `osprey-admin` |

The tile filter is a courtesy. The claim it reads is the `roles` claim the realm already maps.

**3. A second demo account.** `osprey-demo-admin`, holding `osprey-admin` only, is added beside
`osprey-demo-analyst` so the demonstration can show both views. Its password is generated at apply
time and written to `deployment.env` as `OSPREY_DEMO_ADMIN_PASSWORD`, exactly as the analyst's is.
Neither the launcher nor its page ever states a password.

**4. The Admin console enforces `osprey-admin` itself (E1).** The harness gets its own public
client, `osprey-harness`, and a session cookie. Every Admin route requires `osprey-admin`. It is
open only in bootstrap, meaning no rendered realm exists yet, because there is nothing to sign in
to; and it **fails closed** when the realm exists but the identity provider cannot be reached. Per
ADR-044, "the identity provider is unreachable" and "the identity provider said no" are distinct
outcomes and must be reported as such. `ADMIN_ROLE` becomes canonical in `harness/realm.py` and
`webapp_auth` imports it rather than repeating the string.

### Alternatives rejected

- **A: keep one page and hide nothing.** Rejected: it does not answer the request.
- **B: hide tiles and treat the launcher as the gate.** Rejected and withdrawn. It contradicts
  ADR-050: the launcher would hold an access decision the Conduit is meant to own.
- **E2: keep the Admin console open and rely on the launcher.** Rejected: the console's address stays
  reachable directly.
- **E3: a shared secret handed from the launcher to the console.** Rejected: it invents a second
  credential the realm does not know about and cannot revoke.
- **Glass restricted to a Glass-only role.** Rejected by the owner: any signed-in user may open it.

### What this costs

The harness's setup mode no longer means "anyone on the machine may act" once a realm exists. An
operator who loses the demo admin's password has to use the identity provider's own administrator
console to recover, which is the correct place. The realm import runs only at the identity
provider's first start, so a deployment already running needs a one-time registration of
`osprey-launcher`, `osprey-harness` and `osprey-demo-admin` through the admin API; the render alone
does not reach it.

### What would make it wrong

If the harness ever runs somewhere the identity provider is not reachable from the operator's browser,
fail-closed locks the operator out and a break-glass path becomes necessary. Amendment 22 of the
harness and packaging decision (setup mode unauthenticated and loopback-only) is narrowed by this
record, not contradicted: bootstrap stays open, and only the post-realm state closes.

### Tests owed (standing rules 4, 12 and 15)

Each names the failure it would catch, and the fake identity provider must model refusals and an
unreachable state rather than only success:

- Realm: the `osprey-launcher` and `osprey-harness` clients are public with PKCE S256 and the exact
  loopback redirect URIs; `osprey-demo-admin` exists with `osprey-admin` and not the Studio roles;
  the demo analyst does not hold `osprey-admin`; `ADMIN_ROLE` has one definition. These are written
  in `tests/harness/test_realm.py` and currently fail, as they should.
- Every Admin route, one test per route: no session, a session without `osprey-admin`, an expired
  token and an unreachable provider each refuse; a valid admin passes.
- The launcher: no tile before sign-in; the tile sets above; no password or token in the page or in
  `/status`; the pre-login start screen carries no role-only content.
- One real-Keycloak test in the `idp-test` style, because rule 15 says a first green against a fake
  is untested.

### State of the build

Built and committed locally: the launcher (`762a569`), the runbook port defect (`c07d612`) and the
launcher's design-system styling (`1318c75`, not yet pushed). Not built: everything in decisions 1
to 4 above.

### Amendment 1 (29 September 2026): what building decision 4 fixed

Written while building, so the record says what the code does. None of it changes the ruling.

- **Enforcement is decided when the console starts.** A console started with no rendered realm stays
  open for its lifetime; the next start enforces. The alternative (deciding per request) would lock
  the operator out the moment the Launch they are running renders the realm. The cost: a console
  left running through a Launch stays open, on loopback, until it is restarted.
- **It covers every route, pages included**, and is tested from the real route table so a route
  added later is covered without anyone remembering to. Refused API calls answer `401`
  (`sign_in_required`), refused pages redirect to `/login`. These are not `404`: the console's
  existence is not a secret to someone who can already reach its port, unlike console-mode
  `/admin`, which keeps its `404` and its bearer token.
- **Two refusals are told apart** (ADR-044): "the sign-in service is not running" (with what to do)
  and "sign-in was refused" or "this account is not an administrator". An account that signs in but
  lacks the role is not given a session, and is offered a sign-out that also ends the provider's
  session, since signing in again would otherwise re-use the same account silently.
- **One way in:** a server-side session behind an opaque cookie (HttpOnly, SameSite=Lax, host-only,
  eight hours absolute, in memory). A bearer token is not accepted. A state-changing request with a
  foreign `Origin` is refused, as is any host name other than `localhost` or `127.0.0.1` on the
  console's port; `127.0.0.1` is redirected to `localhost`.
- **The session is not re-checked against the provider**, so removing a role takes effect at the
  session's expiry, not immediately.
- **Port 7000 only when enforced**, because the client registers one exact redirect.
- **The `docker run` bootstrap cannot sign in once a realm exists** (it reaches the provider as its
  own `localhost`). The supported route after the first Launch is the host (`make launch`). Recorded
  in `05_DEPLOYMENT.md` §2.5.1.
- **The identity used is the ID token**, whose audience is the client's own id; the launcher and
  console clients carry no Conduit audience, so their tokens are refused by the Conduit.

**State of the build after this amendment.** Built: the realm clients and demo admin, their
registration on a running Keycloak (`make register-sign-in`), the shared sign-in code, and the Admin
console's enforcement. **Not built:** the launcher's own sign-in and role-filtered tiles (decisions 1
and 2), and a test against a real Keycloak (the provider in the tests is a stand-in that models the
refusals, per rule 15, and has not been checked against Keycloak itself).

### Amendment 2 (29 September 2026): the launcher's sign-in, built

Decisions 1 and 2 are built. What the code does, where the ruling left room:

- **Open until a deployment is rendered, decided at start-up**, as for the Admin console. The stack
  start is the one thing allowed **before** sign-in, because the identity provider is part of the
  stack and nobody can sign in to something that is not running; before sign-in the launcher shows a
  single tile, **Start OspreyFlow** or **Sign in**, and names no interface and gives no address.
- **After sign-in, the tiles follow the rulings:** the Glass for any signed-in account, the Ingest
  Studio for any one of the Studio's three roles (the set is read from the Studio's own definition),
  the Admin console for `osprey-admin`. The filter is applied on the server to the page, the tile
  fragment and `/status`, so a hidden interface is absent, not merely not drawn.
- **The one control here is starting the Admin console**, which needs an `osprey-admin` session and
  the page token. Everything else the launcher does was already available before sign-in.
- **Any signed-in account gets a launcher session**, including one with no roles (it sees the Glass).
  The Glass's own tile hint no longer tells a signed-in person to look up a demo password.
- **One implementation of the callback** (`harness.oidc.handle_callback`) serves the launcher and the
  Admin console: the state must equal the cookie set by the browser that started the sign-in, and is
  single-use; unreachable and refused stay apart.
- **The launcher must be on port 7070 when sign-in is required**, for the same exact-redirect
  reason as the console on 7000; it refuses to start otherwise.
- **A known limit:** cookies are per host name, not per port, so the launcher's and console's
  session cookies are sent to any other service on `localhost` (the Glass, for one). They are
  HttpOnly and eight-hour, and this is a machine the operator owns; recorded, not fixed.

**State of the build after this amendment.** All four decisions are built. **Not done:** a test
against a real Keycloak (the tests use a stand-in that models the refusals); and the harness's
browser end-to-end specs were not run against an enforced console.

### Amendment 3 (29 September 2026): the demo admin also holds the analyst and Studio roles

**Status: Accepted, by the owner's ruling, after signing in as `osprey-demo-admin` and finding no way
to the Ingest Studio.** This supersedes one detail of the second-demo-account decision above, which
kept that account to `osprey-admin` alone so that the analyst account stayed unprivileged and the two
differed in more than name. Nothing else in the record changes.

- **What is decided.** The disposable demo admin (rendered only with `apply --demo-analyst`) holds
  `osprey-admin` and every role the demo analyst holds: `analyst`, `source_author`, `source_approver`
  and `loader`. One demonstration login can therefore open the Admin console, the Glass and the
  Ingest Studio. Its clearance and handling attributes match the analyst's, so the seeded
  investigation is visible to it. The analyst account still does not hold `osprey-admin`.
- **What is not decided or changed.** No role permits anything new. The Conduit still enforces each
  role on each request (ADR-050), and the launcher's tile is still a convenience, not an access
  control. `osprey-admin` did not become a Studio role: that would let every real administrator
  author, approve and load sources, and approve their own, which changes the Studio's separation of
  duties and would need its own record. A real administrator gets only what their organisation's
  provider grants.
- **Why the tile alone was not the answer.** Showing the Ingest Studio tile to an account without a
  Studio role would open a Studio that refuses it at the first step, which reads as a defect.
- **What it costs.** The demonstration no longer shows an account that can administer but cannot
  analyse or approve. `09_INGEST_STUDIO.md` §8 already allows one principal to hold several roles,
  and the analyst account already holds author and approver together, so the demonstration
  already shows one person doing both; this adds administration to that. Where the separation
  matters, sign in as an account that holds one role.
- **On a running Keycloak** the change reaches an existing demo admin by re-running
  `make register-sign-in`, which brings the account's attributes up to the current set. Roles are
  read at sign-in, so the person signs out and in again.

### Amendment 4 (29 September 2026): first run against a real Keycloak, and the sign-in page's look

**What running it found.** The tests use a stand-in identity provider; this was the first time the
work met a real Keycloak, on the owner's deployment. Three things surfaced. None changes a ruling.

- **A custom user attribute is discarded silently unless the realm allows it.** The `roles` claim
  the launcher and the Admin console read is a user attribute. `register-sign-in` created the demo
  admin on a realm where custom attributes were off, so the account signed in with no role and the
  launcher offered only the Glass. `register-sign-in` now switches the setting on first and restores
  the attributes of an account that already exists without them. The stand-in now discards
  attributes as Keycloak does, so the tests can see this.
- **A refused administrator password is the usual sign of two renders disagreeing.** Each `apply`
  writes fresh generated passwords into `deployment.env`; a Keycloak started from an earlier render
  refuses the new one. The error now says so and names the recreate command instead of a bare
  `401`. Keycloak keeps nothing between recreations, so accounts created after its first start do
  not survive one. (Recorded already for the demo analyst; the demo admin is restored by
  `register-sign-in`.)
- **A failed `apply` still rewrites `deployment.env`.** Preflight runs after the files are written,
  so an apply stopped by a busy port or the wrong interpreter leaves new passwords in the file while
  the running stack still has the old ones. Not fixed here; noted so the next operator is not
  surprised.

**Decision: Keycloak's sign-in page is restyled with the design system.** The stock grey page,
under the realm's name in capitals, appeared in the middle of an otherwise designed journey. A login
theme is generated from `apps/workspace/src/design/tokens.css` (the authoritative source: no colour
of its own is introduced, and a test enforces it). `apply` writes it beside the compose file;
compose mounts it into Keycloak **beside** Keycloak's own themes, never over them; the realm names it
and calls itself "OspreyFlow". It extends Keycloak's own login theme, so password reset and error
pages still exist. It changes appearance and wording only. **Nothing about who may sign in or what
they may do is touched.** Like `realm.json` and `litellm.yaml` it is a service's own config, not one
of the deployment's four rendered artefacts. A running Keycloak sees it only after it is recreated
from a compose file that mounts it; `register-sign-in` names the theme in the realm only when
Keycloak lists it, because naming a theme that is absent risks a sign-in page that will not render.

**State of the build after this amendment.** Seen working against a real Keycloak, by the owner in a
browser: sign-in, and the launcher's role-filtered tiles for the demo admin (the Glass and the Admin
console, before Amendment 3's roles reached it). **Not yet seen:** the restyled sign-in page; the
demo admin's Ingest Studio tile; the Admin console opening from the launcher and admitting the
demo admin; the analyst account's view. **Still not done:** the harness's browser end-to-end specs
against an enforced console, and the Docker-backed `apply` test, which has not been run since these
changes. The theme was written against Keycloak 26's sign-in markup without its own stylesheet list
to hand, so it may need a second pass once it has been seen.


## ADR-052 — Who may open a case, and at what level: Author, Editor, Viewer

**Status: Accepted on the owner's rulings of 29 September 2026 for the design as a whole. Four
points are marked "Proposed" and wait for the owner's confirmation. Design only: nothing here is
built.** Until it is built, the current rule (any account in the case's owning unit may do anything to
it) is what the Conduit does, and `03_CONDUIT_MIDDLEWARE.md` §3 still describes it truthfully.

### Context: what was seen

The owner asked that an analyst be shown, before the Glass starts, the cases they have access to
("Fixture vs Enron"), and that an administrator be able to say which analyst has access to which
case, at three levels. Measured on 29 September 2026:

- Access to a case is `owning_unit` only: `InvestigationStore.get_authorized` filters
  `WHERE id = $1 AND owning_unit = $2`. Everyone in the unit is equal on every case, and nobody can be
  made read-only.
- There is no route that lists cases. The Glass therefore cannot offer a choice: it creates a new,
  empty case on every load unless given `?investigation=<id>` (`02_GLASS_FRONTEND.md` §2.1). That is
  why the owner's Glass showed "0 nodes".
- A case has no name, only an identifier, so there is nothing to show in a list.
- 33 routes take a case identifier through `AuthorizedInvestigationDep`, and further stores (sites,
  studio recipes, patterns, alerts, assessments) check ownership of their own records.
- The Conduit has no directory of accounts. Accounts live in the identity provider.
- The real Enron corpus is internal and is never admitted (ADR-035); Fixture Corp is the shippable
  synthetic demo.

### Decision

1. **Three levels, each including the one below it.**
   - **Viewer** browses and queries a case. Nothing they do changes it.
   - **Editor** does everything a Viewer can, and updates the case, adds data to it, and edits the
     settings of its nodes.
   - **Author** does everything an Editor can, and manages access to the case and renames it.
2. **A grant is required, and a grant never widens what an account may see.** A principal opens a
   case only if they hold a level on it. The unit check (`owning_unit`), the clearance check and the
   handling-code filter of ADR-041 still apply on top, unchanged and in the same query. A grant can
   only be made to an account in the case's own unit. The level decides what the account may *do*;
   the existing rules alone decide what it may *see*. A level that does not allow an action is
   refused with the ordinary refusal, and an account with no grant on a case
   receives the same 404 as for a case that does not exist (ADR-041's existence-leak rule, not a 403).
3. **Roles still apply.** A level is necessary, not sufficient: adding data still needs the `loader`
   role, and Studio work its own roles. An Editor without `loader` cannot load.
4. **Who creates and administers.** Whoever creates a case is its first Author. A case's Authors
   manage its access. `osprey-admin` may also manage any case's access as a safety net (so a case
   whose Authors have left is not stranded); that account is **not** thereby able to read the case's
   contents, because reading still needs a level, and the clearance and handling rules are not
   suspended. Every change of access is recorded in the case's history (who, what, to whom, when),
   and cannot be restored away.
5. **Existing cases.** On migration the creator becomes Author and the rest of the unit becomes
   Viewer, until an Author changes it. Because the Conduit has no directory to list "the rest of the
   unit", this is stored as a **unit-wide level on the case** (`viewer` for migrated cases, none for
   new ones), not as one grant per person. An Author may set it to none, viewer or editor.
6. **Cases gain a name.** Required when created (the Glass proposes one), changed by an Author. The
   picker shows names, and never the identifier alone.
7. **The Conduit's surface.** `GET /v1/investigations` lists the cases the caller holds a level on
   (name, their level, counts; nothing the caller may not see). `GET`, `PUT` and `DELETE` on
   `/v1/investigations/{id}/access` read, set and remove grants and the unit-wide level (Author, or
   `osprey-admin`; a Viewer or Editor sees only their own level). Each existing route declares the
   level it needs, and a route with no declared level fails the route-coverage check.
8. **The level each existing route needs.** Read, query and preview routes need Viewer. Routes that
   change the case need Editor. `POST /v1/investigations` needs no grant (the caller becomes Author).
   Access routes need Author. The route-by-route table lives in `03_CONDUIT_MIDDLEWARE.md` §3 once
   built, and the coverage check enforces it.
9. **The Glass** shows a case picker before the workspace opens, listing only cases the account holds
   a level on, and a Share panel for Authors. For a Viewer it hides edit controls; it does not
   enforce anything (ADR-050: the Conduit enforces). Opening `?investigation=<id>` without a level
   shows the ordinary "not found" state.
10. **An Admin console screen for `osprey-admin`** to see and correct access across cases is wanted
    later and is not part of this ADR's first build.

**Proposed, for the owner to confirm** (each is fail-closed until confirmed):

- **P1 — Branching a case** needs Editor on the source, and the caller becomes Author of the copy.
  The alternative, Viewer, lets a read-only account take an editable copy.
- **P2 — Export** (ADR-045, 047) needs Editor as well as its own gates, because it carries data out
  of the boundary. The alternative, Viewer, is looser than the owner's "browse and query".
- **P3 — Naming a grantee.** The Conduit has no account directory, so an Author names the person by
  the account name the identity provider knows them by, and the grant takes effect when that account
  signs in. A mistyped name grants nothing to anyone. A pick-list of accounts needs the identity
  provider's user list and is a separate decision.
- **P4 — Seeding.** The synthetic demos are seeded with the demo analyst as Editor and the demo admin
  as Author, and Fixture Corp is offered by name. The Enron corpus is not seeded and not listed.

### What this does not change

Sign-in (ADR-050, ADR-051), the launcher's tiles (a convenience, not an access control), the clearance
and handling model, the existence-leak rule, and which roles exist.

### Build plan (each stage tests first, with planted faults, and its own commit)

1. Store: names, grants and the unit-wide level; migration; level checks in the authorised-case
   dependency; every route against every level (`route_coverage_check`), including the existence-leak
   404 and that a grant never widens unit, clearance or handling.
2. The listing route and the access routes, with history entries.
3. The Glass picker and Share panel.
4. The seed's grants (P4), and the acceptance rows in `08_ACCEPTANCE_SCENARIOS.md`.

### State of the build

Nothing built. Spec pointers added to `02_GLASS_FRONTEND.md` §2.1 and `03_CONDUIT_MIDDLEWARE.md` §3.

### ADR-052, Amendment 1 (29 September 2026) — the owner's answers to the four proposed points

- **P1 (branching needs Editor on the source) — confirmed.**
- **P2 (export needs Editor, as well as its existing gates) — confirmed.**
- **P3 (an Author names the grantee by account name; a typo grants nothing) — confirmed.**
- **P4 (demo seeding) — not confirmed.** The owner asked for the Enron corpus to be seeded as well.
  That conflicts with the standing rule against admitting a real dataset and with ADR-035, which
  keeps the real corpus `internal` and never seeds it. Nothing has been changed: the seed stays as
  ADR-052 describes it (Fixture Corp, the synthetic Enron-shaped demo, by name; no real corpus) until
  the owner rules on that conflict explicitly. Stage 4 waits on it; stages 1 to 3 do not depend on it.


## ADR-053 — Seeding the real Enron corpus on the owner's own machine only: local, opt-in, never shipped

**Status: Accepted, 29 September 2026, on the owner's explicit ruling. Design only: no loader exists,
no corpus is provisioned and nothing here is built.**

### Context: what was seen

The owner asked, when ADR-052's seeding point was put to them, for the Enron corpus to be seeded
as well as the synthetic demos, and chose to lift the rule against admitting a real dataset "for your
own machine only", provided the corpus stays `internal` and can never enter a shipped build.

What already exists, checked directly rather than assumed:

- ADR-035 §C3 records the owner's own admission of Enron for local development, scale testing and an
  owner-run demonstration on the owner's own secured device, through a local, gitignored list
  (`config/real_data_exceptions.yaml`, managed by `python -m scripts.real_data_exceptions`). Its
  module says plainly that no loader exists yet and that whatever loader is built must call
  `is_permitted()` first and refuse when there is no entry.
- ADR-035 §C1 and §C2: a demo is `shipped` or `internal` (fail-closed), internal datasets are
  provisioned to a gitignored directory named by `OSPREYFLOW_INTERNAL_DEMO_DATA_DIR` and never
  committed, and a packaging gate refuses any artefact that contains one, including inside image
  layers. `.dockerignore` excludes `demo-data/`.
- The deployment's seeds are `hmp`, `fixture-corp` and `scenarios`, all synthetic. There is no Enron
  seed, and the registry (`scripts/demo_registry.py`) has two entries, both synthetic.

### Decision

1. **The rule is lifted for one dataset, on one machine, for the uses ADR-035 §C3 already lists.** It
   is not lifted for any other real dataset, and each of those still needs its own entry and its own
   decision. Nothing in this record changes ADR-035; it builds what §C3 said must be built.
2. **A new seed name, `enron`, is opt-in.** `python -m harness.apply --seed enron` (alone or with the
   others) never runs by default and is never implied by another seed. It refuses, with a sentence
   naming what is missing, unless **all** of these hold:
   - the exceptions list has an entry for the Enron corpus permitting `owner_run_demonstration`
     (checked with `is_permitted()`; the entry names this machine, so a copied checkout on another
     machine is refused);
   - the corpus is present under `OSPREYFLOW_INTERNAL_DEMO_DATA_DIR` (no default, so absence means
     "not provisioned", never a search elsewhere);
   - the seed is being run from a checkout, as the other seeds are (a distributed bundle has no seed
     scripts to run).
3. **The corpus is provisioned by the owner, never fetched by the build or by Claude.** The
   owner places the files under the internal directory. Nothing downloads them, nothing copies them
   into the repository or an image, and the seed reads them in place.
4. **It stays `internal` in the registry.** A third manifest, `distribution: internal`, names its
   paths under `demo-data/`. ADR-035 §C2's packaging gate keeps refusing any artefact containing
   them, and the existing test that reclassifying an internal demo as shipped is still refused
   covers this manifest too. A build that leaves the owner's machine has no Enron seed script in it
   (the seed modules are not in the image), so the opt-in cannot even be attempted there.
5. **Access follows ADR-052.** The seeded case is named for what it is ("Enron corpus (real data,
   this machine only)"), has no unit-wide level, and grants the demo admin Author and the demo
   analyst Editor. It appears in the picker only for an account holding a level on it, and never on a
   deployment where the seed was not run.
6. **The Glass says so when it is not provisioned**, as ADR-035 §C1 already designs: a demo whose
   dataset is absent is shown as unavailable with the reason "dataset not provisioned", not as an
   error. (That display is part of ADR-052's picker stage.)
7. **Tests, named before the code (rule 12).** The seed refuses with no exceptions entry; refuses
   with an entry for another dataset or another use; refuses with an entry but no corpus; refuses
   from a bundle; is never selected by any other seed name; and the registry test proves the
   manifest is `internal` and that flipping it to `shipped` with the data still present is refused by
   the gate. Each is proved to fail by planting the fault it names.

### What this does not change

The rule against real data in the repository and in CI (nothing here is committed or reaches CI, which
has no corpus and no exceptions list), the rule that nothing real is distributed to an attendee, and
the synthetic Fixture Corp, which remains the shippable demo.

### State of the build

Nothing built. The owner has not yet added the exceptions entry or provisioned the corpus; both are
theirs to do on their own machine.


### ADR-052, Amendment 2 (29 September 2026) — P4 settled

**P4 is confirmed as amended.** The demo analyst is Editor and the demo admin is Author on the
seeded demos, Fixture Corp is offered by name, and the real Enron corpus is seeded too, on the
owner's own machine only, opt-in and never shipped, as ADR-053 decides. Stage 4 seeds both.


## ADR-054 — Three folders under one repository: OspreyFlow_Core, OspreyFlow_Build, OspreyFlow_Data

**Status: Accepted in principle on the owner's rulings of 29 September 2026. The layout table below
is proposed and waits for the owner's approval; nothing has been moved.** This is the one exercise for
which the owner lifted the standing rule against restructuring the tree.

### Context: what was seen

The owner asked for the product to be separated from the material that builds and governs it, and
for datasets to have a home of their own. Measured on 29 September 2026:

- 980 tracked files. `tests/` (293), `apps/` (250), `packages/` (195) and `services/` (85) are most.
- The repository already draws this line in one place: `scripts/product_tree_link_check.py` lists
  `process/`, `CLAUDE.md`, `.claude/` and `.graphifyignore` as a private tree that publishable
  documents must not cite. Several large folders (`graphify-out`, `Claude outputs`, `.impeccable`,
  caches) are untracked.
- 412 files outside `spec/`, `tests/` and `process/` cite `spec/` (651 ADR mentions in code and
  docstrings), and 131 cite `process/` or `CLAUDE.md`.
- Eight files in `scripts/` import from `tests/`; four are demo-data generators that the seeds
  call, so the product currently depends on its own test tree.
- Thirty non-test scripts and 45 tests find the repository root from their own location; the
  Makefile, the workflows, `.dockerignore` and the Dockerfiles carry about 210 path references.
- `data/` has no tracked files. It is the Conduit's local analytics store, not a set of datasets.

### Decision

1. **One git repository, whose root is the parent of three sibling folders.** History is kept; files
   move with `git mv`. Nothing is split into a separate repository, and nothing is pushed anywhere
   public.
2. **`OspreyFlow_Core` is the product**: what runs and what is built into an image. It holds no
   dataset and no test. Its Docker build context is the Core folder.
3. **`OspreyFlow_Build` is everything that builds, checks, governs or explains the product**, including
   `spec/`, `tests/` and `process/`, the checks that read them, and the Claude-specific material.
4. **`OspreyFlow_Data` holds datasets, one subfolder per dataset**, plus the Conduit's local runtime
   store in its own subfolder. Core never contains raw data; a deployment finds data through
   `OSPREYFLOW_INTERNAL_DEMO_DATA_DIR`, which now points at this folder. ADR-035 §C1's fixed
   `/demo-data/` is superseded by this location; its rules (internal, never committed, gitignored,
   refused by the packaging gate) are unchanged, and ADR-053's Enron seed reads from
   `OspreyFlow_Data/enron/`.
5. **Citations stay as they are.** `spec/...` and `process/...` in Core files become *logical names*.
   The citation, link and publication checks learn one mapping from a logical name to its new
   location; the 412 and 131 files are not rewritten. The private-tree markers are updated to the new
   locations, and the rule that publishable documents must not cite the private tree is unchanged.
6. **The product does not depend on Build.** The demo-data generators the seeds call (Fixture Corp,
   the HMP fixture, the CDR and seizure fixtures, the scenario cohorts) move into Core as a small
   package, and the tests import them from there. Developer tools that need the test tree
   (`mint_dev_token.py`, `update_golden_baseline.py`) move to Build.
7. **Tests.** The Python suite in `tests/` moves to Build. Unit tests written beside front-end code
   (`*.test.ts(x)` under `apps/`) stay beside it: a test tree cannot be pulled away from the code it
   compiles with without breaking the front-end tooling. Pytest settings move to Build and put Core
   on the import path; CI and `make` run from the parent root.
8. **Root files that must stay at the root** (a tool requires it): `.git`, `.gitignore`,
   `.github/` (GitHub reads workflows only from the repository root), `Makefile` (the one entry point;
   its recipes are repointed), `.claude/` (Claude Code reads its settings and commands from where a
   session opens) and a new one-line `CLAUDE.md` that imports the real one in Build, so a session
   opened at the root or in Build reads the same rules. Everything else Claude-specific moves to
   Build.
9. **Proved, not assumed.** The full test and check suite is run before the move and after each
   commit of it, and must give the same result apart from tests that assert the old paths, which are
   corrected in the same commit. A check that would still pass with a path wrong is proved able to
   fail by planting the fault (rule 12).

### Proposed layout (to be approved)

| Now | Moves to |
|---|---|
| `apps/`, `packages/`, `services/`, `harness/`, `providers/`, `connectors/`, `recipes/`, `deploy/`, `config/`, `osprey.yaml` | `OspreyFlow_Core/` (same names) |
| `pyproject.toml` (dependencies), `uv.lock`, `package.json`, `package-lock.json`, `tsconfig.json`, `eslint.config.js`, `.dockerignore`, `.trivyignore`, `LICENSE`, `NOTICE`, `README.md`, `DEMO_GUIDE.md` | `OspreyFlow_Core/` |
| `scripts/` that run the product: `launch.py`, the four `seed_*.py`, `real_data_exceptions.py`, `demo_registry.py`, `publish_seed.py`, `osprey_bundle.py`, `release_local.py`, `register_tier4_provider.py`, `build_local_basemap.py`, `geo_local_provider.py` | `OspreyFlow_Core/scripts/` |
| Demo-data generators now under `tests/scenarios/fixtures/` | `OspreyFlow_Core/packages/`, as a small package |
| `spec/`, `tests/`, `process/` | `OspreyFlow_Build/` (same names) |
| `scripts/` that check or govern: the `*_check.py` files, `packaging_gate.py`, `licence_check.*`, `doc_site.py`, `simple_markdown.py`, `idp_test_realm.py`, `verify_map.py`, `mint_dev_token.py`, `update_golden_baseline.py` | `OspreyFlow_Build/tools/` |
| `CLAUDE.md` (the real one), `.graphifyignore`, `graphify-out/`, `.impeccable/`, `Claude outputs/`, `dist/`, caches, pytest settings | `OspreyFlow_Build/` |
| `data/` (untracked) | `OspreyFlow_Data/_local-runtime/` (the Conduit's default store path is repointed) |
| `demo-data/` (untracked, where present) | `OspreyFlow_Data/<dataset>/` |
| `.git`, `.gitignore`, `.github/`, `Makefile`, `.claude/`, new one-line `CLAUDE.md` | stay at the root |

Scripts marked uncertain (`doc_site.py`, `simple_markdown.py`, `idp_test_realm.py`, `verify_map.py`,
`publish_seed.py`) are decided by what imports them when the file-level inventory is made; the table
above states the rule, and the inventory states the file.

### Order of work (each step its own commit; the suite run before and after)

1. File-level inventory of every path reference, no moves, for the owner's approval.
2. Data folder and the internal-data path (untracked moves, the environment default).
3. Demo-data generators into Core; tests repointed. No folder moves yet.
4. Build: `spec/`, `tests/`, `process/`, tools, Claude material; the logical-name mapping in the
   checks; pytest settings.
5. Core: the product folders and manifests; Docker contexts, Makefile, workflows, root-finding code.
6. Rebuild the machine-bound pieces (`.venv`, `node_modules`, the generated deployment) and re-run
   the whole suite.

### State of the build

Nothing moved. Case-access stage 1 (ADR-052) starts after step 6.

### ADR-054, Amendment 1 (29 September 2026) — step 4 done: what the Build folder holds and how it is run

`spec/`, `tests/`, `process/`, the checks and the Claude material are in `OspreyFlow_Build/`. Three
points the step settled that the layout table above did not state:

- **Tools run as modules.** Every check is run `PYTHONPATH=OspreyFlow_Build python -m tools.<name>`
  (Makefile and workflows), never as a file path, because a file run that way cannot import the
  shared `tools.layout` that maps logical names to folders. Running them by file path was the
  first thing the Makefile did wrong, and every target failed the same way.
- **Tests run with `-c OspreyFlow_Build/pytest.ini`.** The pytest settings live in Build; the paths
  named to pytest are `OspreyFlow_Build/tests/...`. The coverage check reads both spellings and
  compares on the logical `tests/...`.
- **Tools that move with Build:** `osprey_bundle`, `release_local`, `ci_status_check`,
  `packaging_gate`, `licence_check`, `publish_seed` and the `*_check` files. The seeds, the
  launcher, the registration scripts and anything the running product imports stay in Core's
  `scripts/`. `.dockerignore` names `OspreyFlow_Build` in its private-tree block, as
  `PRIVATE_TREE_MARKERS` now requires.
- **The connector catalogue is found from the code, not the working directory.** `CONNECTORS_DIR`
  looks beside `packages/` first, so a process started from Build (the tests) or Core reads the
  same catalogue; `OSPREY_CONNECTORS_DIR` still overrides.

**State of the build.** Steps 5 (the Core folder) and 6 (machine-bound rebuild) remain.
