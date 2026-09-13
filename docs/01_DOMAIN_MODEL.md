# 01 — Domain Model

Build this before anything else. Every other tier is a projection of it, and three of its
concepts — provenance, handling, confidence — cannot be retrofitted once data is loaded.

## 1. The ontology is configuration, not code

The platform ships a default ontology and a loader. A deployment can replace it without a code
change. This is what makes the same product serve a prison intelligence unit, a financial crime
team and a counter-fraud unit, and it is the difference between an intelligence platform and a
bespoke application.

The ontology is a YAML document validated against a JSON Schema at startup:

```yaml
# ontology/default.yaml
version: 3
entity_types:
  - name: Person
    pole_class: person           # POLE upper class — see §1.1
    channel: indigo              # binds to a design-system data channel
    shape: circle
    identifiers: [nino, pnc_id, prison_number, passport_number]
    properties:
      - {name: family_name, type: string, indexed: true, required: true}
      - {name: given_names, type: string, indexed: true}
      - {name: date_of_birth, type: date, indexed: true, sensitivity: high}
      - {name: aliases, type: string[], indexed: true}
    resolution:
      blocking: [soundex(family_name), year(date_of_birth)]
      comparisons: [jaro_winkler(family_name), levenshtein(given_names), exact(date_of_birth)]

  - name: Endpoint                # a phone number, handle, email, account — anything addressable
    pole_class: object
    channel: cyan
    shape: hexagon
    identifiers: [e164, handle, email]
    properties:
      - {name: value_raw, type: string}
      - {name: value_normalised, type: string, indexed: true, required: true}
      - {name: endpoint_kind, type: enum, values: [msisdn, imsi, imei, email, handle, iban, card]}

  - name: Device
    pole_class: object
    channel: plum
    shape: square
  - name: Location
    pole_class: location
    channel: ochre
    shape: pin
  - name: Organisation
    pole_class: organisation
    channel: azure
    shape: square
  - name: Event
    pole_class: event
    channel: moss
    shape: diamond
  - name: Document
    pole_class: object
    channel: violet
    shape: page
  - name: Vehicle
    pole_class: object
    channel: jade
    shape: triangle
  - name: Asset
    pole_class: object
    channel: rose
    shape: diamond

edge_types:
  - {name: COMMUNICATED_WITH, from: [Endpoint], to: [Endpoint], directed: true, temporal: true}
  - {name: USES,              from: [Person], to: [Endpoint, Device], directed: true}
  - {name: PRESENT_AT,        from: [Person, Device, Vehicle], to: [Location], temporal: true}
  - {name: MENTIONED_IN,      from: ["*"], to: [Document], directed: true}
  - {name: ASSOCIATE_OF,      from: [Person], to: [Person], directed: false}
  - {name: FAMILY_OF,         from: [Person], to: [Person], directed: false, properties: [relation]}
  - {name: MEMBER_OF,         from: [Person], to: [Organisation]}
  - {name: TRANSACTED,        from: [Asset, Endpoint], to: [Asset, Endpoint], temporal: true}
  - {name: SAME_AS,           from: ["*"], to: ["*"], directed: false, system: true}
```

### 1.1 POLE is the upper ontology, not the schema

`pole_class` puts every concrete entity type under a POLE upper class. Two layers, doing
different jobs:

- **POLE** — the shared vocabulary. Five classes: **Person**, **Object**, **Location**,
  **Event**, and Organisation where a deployment treats legal entities separately. Stable,
  small, recognisable to any UK policing analyst, and the level at which mapping, search
  facets and cross-force conversation happen.
- **The nine entity types** — the operational schema. Specific enough to validate against,
  index on, and resolve with.

A terminology note, since it matters for anything client-facing: POLE is **Person, Object,
Location, Event**. Organisation is not the O — it is usually folded into Object or carried as a
sixth class in the POLE+ variants some forces use. MantisNexus takes the second route and gives
`organisation` its own `pole_class`, because an organisation behaves like a party in this domain
rather than like a thing, and collapsing it into Object makes network analysis over corporate
structures awkward. Flag the divergence in any client conversation rather than letting it be
discovered.

The reason to have both layers rather than one: POLE alone is too coarse to validate against — a
schema that says "this column is an Object" cannot tell you that an IMEI is not a vehicle
registration. The nine types alone are too fine for a mapping interface, where someone loading a
new source wants to say "this is a person" and then narrow. So the ingest studio in
`09_INGEST_STUDIO.md` works POLE-first and narrows to a concrete type, and search facets and
filter groupings roll back up to POLE.

A deployment may add entity types; it may not add POLE classes. That constraint keeps the
vocabulary shared.

Nine entity types, nine data channels. That is not a coincidence — the design system defines
exactly nine categorical channels, checked for protanopia and deuteranopia separation, and there
is no tenth to allocate.

The loader enforces two rules, and only two:

1. **A channel name must be one of the nine.** An unknown channel is a rejected configuration.
2. **No two entity types may share a channel *and* a shape.** Sharing a hue is permitted; being
   indistinguishable is not.

Rule 2 is deliberately narrower than "no reuse". Shape is always carried alongside hue precisely
so that hue never carries a distinction on its own, which is the recorded mitigation for
tritanopia, where nine hues cannot be separated. That mitigation is what makes channel sharing
safe: a deployment needing a tenth entity type gives it an existing channel and a distinct
shape, and nothing in the visual language breaks. A loader that rejected all reuse would forbid
the very escape hatch the design system provides, and would have to be reversed the first time a
deployment outgrew nine types.

The nine shipped types use nine distinct channels, so no sharing occurs in the default ontology.
The rule exists for the tenth.

### Why `Endpoint` rather than `Phone`

The CoLP journey turns on the fact that a mobile number, a WhatsApp handle, an IMEI and an IMSI
are the same *kind* of thing analytically: an addressable point that a person uses and that can
be swapped. The journey's pivot is a suspect swapping SIMs while keeping a handset. Modelling
phone numbers and handles as separate types makes that traversal a special case; modelling them
as one `Endpoint` type with an `endpoint_kind` makes it a single hop. Take the generalisation.

## 2. The node record

Every node carries five blocks. Only the first is domain data.

```python
class Node(BaseModel):
    id: NodeId                       # ULID, assigned by the Conduit, never by a source system
    type: str                        # must exist in the active ontology
    properties: dict[str, Any]       # validated against the ontology's property definitions
    provenance: Provenance
    handling: Handling
    resolution: ResolutionState
    audit: AuditStub
```

### 2.1 Provenance

```python
class Provenance(BaseModel):
    state: Literal["asserted", "inferred", "unresolved"]
    sources: list[SourceRef]         # never empty
    extracted_by: str | None         # "model:qwen2-vl:7b@2026-05-02" or "connector:cdr-o2"
    extraction_confidence: float | None   # 0..1, model-reported, null for asserted
    first_seen: datetime
    last_confirmed: datetime | None
    confirmed_by: PrincipalId | None

class SourceRef(BaseModel):
    document_id: DocumentId
    locator: str                     # page 7, char span 412-489, timestamp 00:14:22, row 1184
    excerpt_hash: str                # sha256 of the supporting span, for tamper evidence
```

The three provenance states map one-to-one onto the design system's provenance strokes:

| State | Meaning | Stroke |
| --- | --- | --- |
| `asserted` | Present in a source record as a fact | 1px solid, border-strong |
| `inferred` | Derived by a model or an algorithm | 1.5px dashed 4-2, channel colour |
| `unresolved` | Single uncorroborated source, or a resolution below threshold | 1.5px dotted, channel colour |

Provenance is carried by stroke, not by colour, precisely so that it composes with all nine
channels. This is the design system's rule and the ontology must not break it.

**Every node and edge created by a model is `inferred` until a human confirms it.** Confirmation
is an explicit analyst action that writes `confirmed_by` and `last_confirmed` and flips the state
to `asserted`. There is no automatic promotion, no confidence threshold above which the system
decides on the analyst's behalf. An intelligence product that cannot distinguish what a machine
guessed from what a document says is not usable as evidence.

### 2.2 Handling

```python
class Handling(BaseModel):
    classification: str              # from the deployment's classification scheme
    handling_code: str               # e.g. "P" — lawful sharing permitted
    action_code: str | None          # e.g. "A1" — covert development, no direct action
    sanitisation_code: str | None    # e.g. "S2" — consult originator before dissemination
    originator: OrgUnitId
    owning_unit: OrgUnitId
    review_date: date | None
    legal_basis: str | None          # the processing basis recorded at ingestion
```

**Which of these fields filters a read, and which gates an export.** They are not the same set,
and conflating them produces either a filter that leaks or an export gate that blocks everything.

| Field | Read-time visibility | Export gate |
| --- | --- | --- |
| `classification` | Yes — the primary axis, ordered, dominance rule | Yes |
| `handling_code` | Yes when `dissemination: restricted` — a recipient-restricted record is invisible outside its permitted set | Yes |
| `owning_unit`, `originator` | Yes, but only as the scope for a restricted `handling_code` | Yes, for the originator reference |
| `action_code` | **No.** It constrains what may be *done* with intelligence, not who may see it | No — it governs operational action |
| `sanitisation_code` | **No.** It is a dissemination control and is the export gate's entire reason for existing | Yes |

A `Principal` therefore carries the set of handling codes it may receive alongside its clearance
and unit, and the filter evaluates both axes. Filtering on classification alone is a partial
implementation: it will pass every existence-leak test written against classification and still
disclose a recipient-restricted record to the wrong unit.

**A clearance value the active scheme does not recognise is the most restrictive principal
possible: it sees nothing.** Default-deny, not default-allow — stated here rather than left as
an implementation's judgement call, because the alternative (an unrecognised clearance defaulting
to broad visibility) is exactly the kind of silent failure mode this section exists to close off.

The code *values* come from a scheme file, not from the codebase:

```yaml
# ontology/handling/uk-le.yaml
classification: [OFFICIAL, "OFFICIAL-SENSITIVE", SECRET]
handling_codes:
  P: {label: "Lawful sharing permitted", dissemination: permitted}
  C: {label: "Conditions apply", dissemination: conditional}
  R: {label: "Recipient restricted", dissemination: restricted}
action_codes:
  A1: {label: "Covert development", direct_action: false, originator_permission: true}
  A2: {label: "Action permitted", direct_action: true}
sanitisation_codes:
  S1: {label: "May be sanitised", consult_originator: false}
  S2: {label: "Consult originator", consult_originator: true}
```

Do not hardcode any national scheme. **Exactly one handling scheme is active at a time** — they
define competing classification orderings and merging two produces a lattice nobody can reason
about. What may be enabled alongside it is a *source-evaluation* scheme such as 5×5×5, which is a
second file of the same shape describing a different axis: how reliable the source is, not who
may see the record. One handling scheme, optionally one source-evaluation scheme. The enforcement logic reads
the booleans (`dissemination`, `direct_action`, `consult_originator`), never the code letters.

**Two schemes ship, for the two target jurisdictions.** `uk-le.yaml` as above. For the US,
`us-criminal-intelligence.yaml` models the controls that 28 CFR Part 23 imposes on criminal
intelligence systems — an entry standard, a periodic review and purge cycle, and dissemination
recording. Three fields already in the model carry it: `handling.review_date` is the review
cycle, `legal_basis` is the entry justification, and the audit stream in
`03_CONDUIT_MIDDLEWARE.md` §6 is the dissemination record. What is added is a scheme file plus
two behaviours: a review queue that surfaces records approaching their review date, and a purge
action that supersedes rather than deletes, leaving the audit trail intact.

Confirm the specifics with the client's own legal or compliance function before go-live rather
than treating the shipped file as authoritative. The point of the scheme format is that their
answer is a configuration change. It is worth raising early in a US engagement: a platform that
cannot evidence periodic review is difficult to operate under Part 23, and retrofitting review
dates onto data already loaded is painful.

The **export gate** is the point where this becomes load-bearing. Exporting a chart, a subgraph
or a report runs every node and edge in the selection through the handling evaluator. If any
carries `consult_originator: true`, the export is blocked with the specific items named, and
proceeds only with a recorded justification and an originator reference. This is the single
control that the HMP report's `S2` marking exists to impose.

### 2.3 Resolution state

```python
class ResolutionState(BaseModel):
    cluster_id: ClusterId | None     # the resolved-entity cluster this node belongs to
    cluster_score: float | None      # Fellegi-Sunter match probability
    resolution_run: str | None       # which resolution model version produced it
    manually_linked: list[NodeId]    # analyst-asserted same-as
    manually_split: list[NodeId]     # analyst-asserted not-same-as, never re-merged
```

See §4 — nodes are never destructively merged.

### 2.4 Audit stub

```python
class AuditStub(BaseModel):
    created_at: datetime
    created_by: PrincipalId          # a person, a connector, or an extraction worker
    revision: int
    superseded_by: NodeId | None
```

Nodes are versioned, not overwritten. A correction writes a new revision and points the old one
forward. An intelligence assessment written last month must still be reconstructible against the
picture as it stood at the time.

## 3. The edge record

Structurally identical, plus:

```python
class Edge(BaseModel):
    id: EdgeId
    type: str
    source: NodeId
    target: NodeId
    properties: dict[str, Any]
    interval: Interval | None        # valid_from / valid_to, for temporal edges
    occurrences: int                 # how many source events this edge summarises
    weight: float                    # derived; see §6
    provenance: Provenance
    handling: Handling
```

### Temporal edges and the event table

An edge such as `COMMUNICATED_WITH` between two endpoints summarises many individual events.
Storing every call as its own edge makes the graph unusable; storing only a summary makes
temporal analysis impossible. Do both:

- The **graph store** holds one summarised edge per pair per type, with `occurrences`, an
  `interval` spanning first to last, and a `weight`.
- The **analytics store** holds the event rows: `(event_id, edge_id, source_id, target_id, ts,
  duration, cell_site, lat, lon, direction, properties)`, one row per call, message, transaction
  or sighting.

The timeline brush queries the analytics store for counts and drives the graph's edge weights
and visibility from the result. This is the mechanism behind the temporal slider highlighting
the graph, and it is why `AnalyticsPort` exists as a separate port rather than being folded into
`GraphPort`.

## 4. Entity resolution is a view, not a merge

**This overrides the Gemini specification, which states that records are "probabilistically
merged into golden records before insertion into the graph database."** That contradicts the
dynamic-threshold requirement in the same document: if you hard-merge at ingest you have fixed
the threshold at ingest time, and an analyst cannot loosen it to catch a fuzzy name match or
tighten it for a high-assurance financial investigation. You also cannot un-merge, which is the
more serious problem — a wrong merge in an intelligence system silently attributes one person's
activity to another, and there is no signal that it happened.

The design:

1. Ingest writes **source-fidelity nodes**. A `Person` extracted from a witness statement and a
   `Person` from a custody record are two nodes. Nothing is merged.
2. Splink runs over the source-fidelity nodes and writes `SAME_AS` edges carrying the
   Fellegi–Sunter match probability, the model version, and the comparison vector that produced
   the score.
3. At query time the Conduit applies a **resolution threshold** τ from the analyst's session and
   collapses `SAME_AS` components with score ≥ τ into a single displayed entity. Changing τ
   re-projects the view; it does not touch storage.
4. Analyst decisions are edges too: a manual link is a `SAME_AS` with score 1.0 and
   `provenance.state = asserted`; a manual split is a `NOT_SAME_AS` edge that the projection
   always honours and no future resolution run may override.

The Glass surfaces τ as a slider with three labelled detents — **Strict (0.99)**, **Balanced
(0.95)**, **Broad (0.80)** — and shows the delta when it moves: "3 entities merged, 1 split, 47
nodes affected." Silent re-projection of a network under an analyst is disorienting and
dangerous; always show what changed.

### Splink configuration

Splink (MIT, UK Ministry of Justice) runs on DuckDB in the laptop profile and on Spark in the
cluster profile — the same model definition, the same comparison library, a different backend.
That maps exactly onto the transportability requirement, and it is the reason Splink is the
right choice over Dedupe or Zingg here.

Blocking rules and comparisons come from the ontology's `resolution` block per entity type, so
adding an entity type does not require touching the resolution service.

Deterministic identifiers short-circuit the probabilistic path entirely: two `Endpoint` nodes
with the same normalised E.164 value are the same endpoint, full stop. Only run Splink on types
where identity is genuinely uncertain.

## 5. Assessment objects

The HMP Hollywood report is not a graph. It is an *assessment*: a set of judgements, each with a
stated probability, each resting on named evidence, plus explicit intelligence gaps and
assumptions. The platform must produce that artefact, not just the picture behind it.

```python
class Judgement(BaseModel):
    id: JudgementId
    investigation_id: InvestigationId
    statement: str
    probability_band: str            # from the configured yardstick
    supporting: list[NodeId | EdgeId | DocumentId]
    contradicting: list[NodeId | EdgeId | DocumentId]
    author: PrincipalId
    created_at: datetime

class IntelligenceGap(BaseModel):
    id: GapId
    question: str
    raised_by: PrincipalId
    linked_entities: list[NodeId]
    status: Literal["open", "tasked", "answered", "closed"]

class Assumption(BaseModel):
    id: AssumptionId
    statement: str
    if_false_impact: str             # which judgements fall over
    linked_judgements: list[JudgementId]
```

Probability bands come from a configured yardstick file, not from the codebase:

```yaml
# ontology/yardstick/phia.yaml
name: "PHIA probabilistic yardstick"
bands:
  - {label: "remote chance",          lower: 0.00, upper: 0.05}
  - {label: "highly unlikely",        lower: 0.05, upper: 0.20}
  - {label: "unlikely",               lower: 0.20, upper: 0.35}
  - {label: "realistic possibility",  lower: 0.40, upper: 0.50}
  - {label: "likely",                 lower: 0.55, upper: 0.75}
  - {label: "highly likely",          lower: 0.80, upper: 0.90}
  - {label: "almost certain",         lower: 0.95, upper: 1.00}
```

Confirm the exact bands against the currently published yardstick your organisation uses before
go-live — they have been revised, and the file exists so that a revision is a config change.

The UI constraint that makes this worth building: **a judgement cannot be saved without at least
one supporting reference**, and the reference must be a node, edge or document in the
investigation. Selecting a judgement highlights its evidence on the canvas; selecting a node
lists the judgements that rest on it. When a supporting node is later split, corrected or
retracted, every judgement resting on it is flagged for review. That closed loop between the
picture and the assessment is the thing the commercial products do not give you, and it is
cheap to build once the provenance model above exists.

## 6. Edge weight and the Clique Metric

### 6.1 Weight

`weight` is derived at load time and recomputed on the working set, never hand-set:

```
weight(e) = normalise( α·log1p(occurrences) + β·recency(interval.to) + γ·mutual_information(u,v) )
```

`mutual_information` is the pointwise mutual information of the pair against the corpus, which
is what suppresses high-volume, low-information relationships — the broadcast sender, the
service number that everyone calls. α, β, γ are per-deployment configuration with defaults
0.5 / 0.2 / 0.3. The Glass exposes the normalised result as the edge-strength filter slider.

### 6.2 Clique Metric

Both the v2 spec and the Gemini spec require a "Clique Metric" and neither defines it. Here is
the definition to implement:

For node *v* with neighbourhood *N(v)*:

```
internal(v) = number of edges among N(v)
possible(v) = |N(v)| · (|N(v)| − 1) / 2
density(v)  = internal(v) / possible(v)                    # local clustering coefficient

external(v) = Σ over u ∈ N(v) of edges from u to nodes outside N(v) ∪ {v}
dispersion(v) = external(v) / Σ over u ∈ N(v) of degree(u)

clique(v) = density(v) · (1 − dispersion(v)) · saturate(|N(v)|, k_min, k_max)
```

`saturate` suppresses trivial cases: a node with two neighbours who know each other has
density 1.0 and is not interesting. Default `k_min = 4`, `k_max = 30`; below `k_min` the score
is zero, above `k_max` it plateaus.

The metric answers the question the input documents pose: it scores a node whose contacts all
know each other and talk to nobody else, and it scores a broad, well-connected hub near zero.
That is precisely the inverse of degree centrality, which is why it surfaces an insular
middle-management cluster while filtering out a chief executive who corresponds with everyone.

Implement it in `ComputePort` at all three tiers. The browser tier must produce identical
results to the rustworkx tier on the same input — assert this in the conformance suite with a
fixture graph, because a metric that changes value when the working set crosses a size threshold
will destroy analyst trust the first time someone notices.

### 6.3 Other required algorithms

| Algorithm | Use | Note |
| --- | --- | --- |
| Louvain / Leiden | Community detection | Prefer Leiden; Louvain can produce disconnected communities |
| Betweenness centrality | Brokers and cut-outs | Approximate (Brandes with sampling) above 100k nodes |
| Eigenvector / PageRank | Influence | Report alongside clique score, never instead of it |
| k-shortest paths | Pathfinder between two entities | Must respect the access filter; a path through a node the principal cannot see is not returned |
| Temporal motifs | Convoy, relay, burst | See `02_GLASS_FRONTEND.md` §5 |

**`GraphPort.paths` is not this table's k-shortest paths.** Two methods share a `PathRequest` and
return a `list[Path]`, and they are not the same capability. `GraphPort.paths` is a bounded
traversal-level existence check — is there a route within `max_hops`, access-filtered, and if so
return up to `k` of whatever `simplePath` finds — suited to a single adapter answering "are these
two entities connected at all" cheaply, on the graph store itself. `ComputePort.shortest_paths`
(this table, Phase 7's Pathfinder) is the actual weighted, ranked k-shortest-paths algorithm,
running on one of `ComputePort`'s three compute tiers over the working set. Do not implement
`GraphPort.paths` as a shortest-path algorithm, and do not route the Pathfinder feature through
`GraphPort` — the split exists so that a cheap connectivity check and an expensive ranked
algorithm scale independently, the same reasoning as ADR-008's split between `AnalyticsPort` and
`ComputePort`.

## 7. Identifier normalisation — the Knowledge Adapters

The CoLP deck is specific about this and it is the least glamorous, highest-value part of the
ingest path. A phone number arriving as `01621926368`, `+44(0)1621926368`, `441621926368` or
`#31#01621926368` must resolve to one `Endpoint`. Get this wrong and the graph silently
fragments; no amount of analytics recovers it.

Normalisers required at ingest, each a pure function with a golden test file:

| Adapter | Input variance | Canonical form |
| --- | --- | --- |
| `msisdn` | national, international, CLI-suppression prefixes, extensions | E.164, plus original retained in `value_raw` |
| `imei` | 14/15/16 digits, check digit, `/` separators | 14-digit TAC+serial, check digit dropped |
| `imsi` | with/without MCC-MNC separators | 15-digit |
| `email` | case, plus-addressing, unicode domains | lowercase local, punycode domain |
| `datetime` | mixed formats, local times, missing zones | UTC with recorded original offset; a missing offset is an error, not a guess |
| `person_name` | ordering, diacritics, honorifics, ALL-CAPS surnames | structured given/family, originals retained |
| `address` | free text | structured, with a gazetteer identifier attached where one is configured — UPRN in the UK, a GNIS feature id, TIGER GEOID or county parcel id in the US. The identifier is an alias, never the key |
| `iban` / `card` | spacing, masking | normalised; card stored as last-four plus a hash, never in full |

Two rules that are not optional:

1. **Never discard the original.** `value_raw` is retained on every normalised property. A
   normaliser bug discovered in month six must be correctable by re-running against the raw
   value, and the original is sometimes itself evidence — CLI suppression is a fact about the
   caller's behaviour, not noise.
2. **Deduplicate CDRs on a content hash, not on the whole row.** The CoLP deck asks about
   duplicate CDR lines directly. The same call appears twice with different sequence numbers or
   file-level metadata. Hash `(a_party, b_party, start_ts_to_second, duration, direction)` and
   deduplicate on that, retaining every source row reference on the surviving event so the
   provenance chain stays complete.

## 8. `GraphPort` request and response shapes

`00_ARCHITECTURE.md` §2.1 gives `GraphPort`'s method signatures — `expand(req: ExpandRequest,
principal) -> Subgraph`, and so on — but never defined the request/response types themselves.
Phase 1 built them, without raising the gap first. Recorded here so the contract three more
adapters must satisfy is not only the one written down in a single implementation.

```python
class ExpandRequest(BaseModel):
    node_ids: list[NodeId]
    depth: int                        # 1-4
    edge_types: list[str] | None      # None: every edge type: an explicit ["*"]-style
                                       # wildcard was not worth a second spelling of "no filter"
    direction: Literal["out", "in", "both"]
    temporal_window: Interval | None  # filters by the edge's own interval, not the node's

class PathRequest(BaseModel):
    source: NodeId
    target: NodeId
    max_hops: int
    k: int                            # at most this many paths returned
    edge_types: list[str] | None

class Path(BaseModel):
    nodes: list[NodeId]
    edges: list[EdgeId]
    length: int                       # hop count; len(edges)

class NeighbourhoodStats(BaseModel):
    node_id: NodeId
    degree: int
    degree_by_type: dict[str, int]    # keyed by edge type name

class Subgraph(BaseModel):
    nodes: list[Node]
    edges: list[Edge]
    filtered_count: int                # see the note below — reserved, not yet populated
```

**`GraphPort.paths` is a bounded connectivity check, not the k-shortest-paths algorithm** — see
§6.3's note under the algorithm table for the split against `ComputePort.shortest_paths`.

**`filtered_count` is reserved, and Phase 1's adapter leaves it at zero.** `00_ARCHITECTURE.md`
§5 states the general principle — "the count is reported as filtered so the analyst knows the
picture is incomplete" — but computing it correctly needs a full-vs-filtered comparison at a
point that holds both results, which is the Working-Set Service in Phase 3
(`03_CONDUIT_MIDDLEWARE.md`, the expansion budget/cardinality preview), not a second query
inside `GraphPort.expand` itself. A second query invented per adapter to populate this field is
exactly the kind of extra, less-audited channel the existence-leak requirement exists to rule
out. Phase 3 populates it; until then it is a declared gap, not a silent one.

### 8.1 Pattern matching

```python
class PatternNode(BaseModel):
    var: str                          # a name local to this query, not a stored identifier
    entity_type: str | None           # None: any entity type

class PatternEdge(BaseModel):
    edge_type: str
    from_var: str
    to_var: str

class PatternQuery(BaseModel):
    nodes: list[PatternNode]
    edges: list[PatternEdge]
    limit: int
```

The binding rule, stated explicitly because nothing else does: **`nodes[0]` is the query's
anchor, and every edge in `edges` must name a `from_var` already bound by the anchor or an
earlier edge in the list — never a `to_var` introduced later.** A pattern is built up the way a
caller would compose it by hand, one hop at a time from a starting point, not declared as an
unordered set of constraints to be solved. `MENTIONED_IN` from either of two unconnected node
sets, or a pattern requiring a node reachable only via a *later* edge, cannot be expressed;
splitting it into two `match` calls and joining the results in the Conduit is the workaround
until a real pattern-solving `match` is worth building. A second `GraphPort` adapter proving this
suite must honour the same ordering rule, not invent its own.

Two nodes may share an `entity_type`, and an edge's endpoints are matched against whichever
`PatternNode.entity_type` is declared for `to_var`, if any — an untyped node matches any entity
type reached at that position.
