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
    identifiers: [e164, handle, email, imsi]
    properties:
      - {name: value_raw, type: string}
      - {name: value_normalised, type: string, indexed: true, required: true}
      - {name: endpoint_kind, type: enum, values: [msisdn, imsi, email, handle, iban, card]}

  - name: Device                  # a physical handset — identified by IMEI, not an Endpoint kind
    pole_class: object
    channel: plum
    shape: square
    identifiers: [imei]
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
  # By convention the source is an Endpoint of kind `imsi` only — see the
  # prose below. Not schema-enforced: `from`/`to` check entity type, not
  # `endpoint_kind`.
  - {name: PAIRED_WITH,       from: [Endpoint], to: [Device], directed: true, temporal: true}
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
sixth class in the POLE+ variants some forces use. OspreyFlow takes the second route and gives
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

The CoLP journey turns on the fact that a mobile number, a WhatsApp handle and an IMSI are the
same *kind* of thing analytically: an addressable point a person uses and that can be swapped.
Modelling phone numbers and handles as separate types makes that traversal a special case;
modelling them as one `Endpoint` type with an `endpoint_kind` makes it a single hop. Take the
generalisation.

An IMEI is not this — it identifies the handset itself, not an address a person is reached at, so
it lives on `Device`, not as an `endpoint_kind`. The journey's pivot, a suspect swapping SIMs
while keeping a handset, is one hop *for the SIM leg specifically*: an `Endpoint` of kind `imsi`
carries one `PAIRED_WITH` edge to the `Device` it was inserted in, so two swapped SIMs both
resolve to one handset node in one traversal rather than two. An `Endpoint` of kind `msisdn` never
carries `PAIRED_WITH` directly — an MSISDN and the IMSI it is dialled through are the same SIM
observed two ways, so they resolve like any other duplicate identity in this scenario, via a
`SAME_AS` edge, not a second `PAIRED_WITH`. Reaching a `Device` from the number an analyst lands
on (`08_ACCEPTANCE_SCENARIOS.md` B5/B7) is therefore `Endpoint(msisdn) --SAME_AS-->
Endpoint(imsi) --PAIRED_WITH--> Device`: two graph hops, collapsing to one at the resolution
projection the same way every other `SAME_AS` in this journey does (`06_DECISIONS.md` ADR-023).

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

**An unrecognised clearance is default-deny, not default-allow.** A `Principal.clearance` value
the active handling scheme does not know — a typo, a scheme mismatch after a deployment swaps
schemes, a principal resolved against the wrong scheme entirely — is treated as the most
restrictive possible principal: it matches no classification, not every classification. The
alternative (fail open) would make a configuration error into a silent over-disclosure, which is
the one failure mode this platform cannot recover from after the fact.

**A non-human `Principal` follows the same two axes as any other — a decision, not an implied
exemption.** `06_DECISIONS.md` ADR-025's corpus-wide resolution trigger is the first caller in this
build that acts under a deployment-level service identity rather than an analyst's own — a real
question, since nothing above states what such an identity may see. Settled here: the service
principal carries the active scheme's *highest* classification but an **empty**
`receivable_handling_codes`. The reason is structural, not a cautious default chosen for its own
sake — `receivable_handling_codes` only ever matters for a `handling_code` whose scheme entry is
`dissemination: restricted`, and clearing one also requires `org_unit` to match the record's
`owning_unit` or `originator` (the table above). A single fixed `org_unit` cannot belong to every
unit a corpus spans, so a service principal with a *non-empty* `receivable_handling_codes` would
still fail the unit check for some records — an inconsistent, partially-working bypass rather than
a clean one. An empty list instead makes the outcome uniform and honest: the trigger resolves
every non-restricted record and **never** a restricted-`handling_code` record, corpus-wide, by
construction — the same `AccessFilter.gremlin_has_step` predicate every other principal is
compiled against, not a second, privileged path around it (`CLAUDE.md` rule 3). A future
deployment that needs restricted records resolved too needs per-unit service identities, a real,
separate design question this default does not answer.
`tests/resolve/test_trigger.py::test_service_principal_cannot_see_a_restricted_handling_code_record`
proves it against the real adapter: a `handling_code: R` `Person` is invisible to the service
principal and visible to an ordinarily-cleared-and-entitled one, in the same test.

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
    revision: int = 1
    superseded_by: str | None = None  # a NodeId on a Node's audit, an EdgeId on an Edge's — §3
    load_id: str | None = None
    recipe_id: str | None = None
    recipe_version: int | None = None
    reverted: bool = False
```

Nodes are versioned, not overwritten. A correction writes a new revision and points the old one
forward. An intelligence assessment written last month must still be reconstructible against the
picture as it stood at the time.

**`load_id`/`recipe_id`/`recipe_version`** are what makes ADR-018's "every loaded element is
stamped with the recipe version that produced it" true at the element level, not only in a
side-table: `load_id` is the join key into the load ledger (`services/ingest`'s `LoadRecord`) for
full source/recipe detail, and `recipe_id`/`recipe_version` are denormalised onto every element
too, so "everything `cdr-carrier-a` version 4 produced" is a property filter on the graph itself
rather than a join through the ledger. `None` for anything written outside a recipe load — a
conformance fixture, a manual `SAME_AS`, a Splink write.

**`reverted`** is a universal axis, not principal-dependent: a reverted element is invisible to
every read, any clearance, the same way a classification a principal cannot see is invisible to
them — `services/ingest`'s `revert_load` is the only writer, via `GraphPort.revert_elements`. It
is never deleted, only flagged, so the audit trail stays intact and the same element ID can be
cited in an audit query after the fact.

**`superseded_by`** is written only by `GraphPort.supersede_node`/`supersede_edge` (§8.2). A
superseded element is excluded from ordinary reads by default, the same as a reverted one, and
retrievable only via `get_node(..., include_superseded=True)`.

**This absence of a hard-delete method is load-bearing for something outside `GraphPort` itself,
not only a design choice contained here — read this before adding one.** `06_DECISIONS.md`
ADR-037's own amendment (Phase 7 Stage 6, the corpus-wide change stream a saved-pattern monitor
watches) proves the stream misses no possible match — including one created by removing
something — on exactly two facts: this section's own "nodes are versioned, not overwritten"
(supersession is a *write*, which the change stream already captures) and `PatternQuery`'s own
absence of a negation/"must not exist" clause (`§8.1`, its own matching note). **If a real
hard-delete is ever added to `GraphPort`, that half of the argument breaks even if `PatternQuery`
still has no negation** — a hard-deleted element is not a write the change stream would see, so a
monitor watching for a pattern whose completion depended on that element's absence (once
`PatternQuery` can express that) would go silently incomplete: it would simply never fire, with
nothing failing to say so. **The test that would need to exist at that point:**
`test_change_stream_carries_an_entry_for_a_hard_delete`, asserting a consumer reading the stream
after a hard-delete sees an entry for it, the same proof `06_DECISIONS.md` ADR-037's own accepted
case already requires for resolution/manual-assertion writes. Until a hard-delete method exists,
this is a documented dependency, not a gap — recorded here as well as in `06_DECISIONS.md`
ADR-037 and `§8.1` below, so whoever adds one reads it at the point they'd otherwise miss it.

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
    weight_components: WeightComponents | None  # §6.1 — the raw counts behind `weight`
    provenance: Provenance
    handling: Handling
    audit: AuditStub                 # §2.4 — an edge is versioned the same way a node is
```

**An edge carries `AuditStub` too, including `superseded_by`.** Correcting an edge (a wrong
`duration_s`, a mistakenly-typed edge, evidence found to be unreliable) uses
`GraphPort.supersede_edge` (§8.2), not a mutation in place, for the same reason a `Person` is
never overwritten: `01_DOMAIN_MODEL.md` §5's `Judgement.supporting`/`contradicting` can cite an
`EdgeId` directly, and a correction must leave that citation resolvable to something rather than
silently rewriting what it pointed at.

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

**`PRESENT_AT` carries two distinct meanings under one edge type**: a person's (or device's or
vehicle's) residency at a `Location` (e.g. a person's assigned cell), and their point-in-time
presence at a `Location` at a specific timestamp (e.g. an incident sighting in a yard). Both use
the same `PRESENT_AT` edge/event shape rather than a second edge type, so a caller must not assume
a given `Person` has exactly one `PRESENT_AT` edge — a subject under investigation may carry a
residency edge plus one or more incident-presence edges to other locations.

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

**`soundex(family_name)` normalises before blocking — a matching-semantics decision, not only the
crash fix it shipped alongside (`services/resolve/duckdb_setup.py::_soundex`, Phase 7 Stage 6b).**
Before blocking two family names against each other, the value is Unicode-normalised (NFKD) and
folded to its base Latin letters — `Müller` and `Muller` now block together, `José` and `Jose` too
— rather than compared on the raw, accent-bearing string. This is a deliberate choice about what
"the same name" means for blocking purposes, not an incidental side effect of making the function
not crash: the alternative (strip accented characters outright rather than fold them to their base
letter) would not have crashed either, but would have silently stopped an accented and unaccented
spelling of the same surname from blocking together — the wrong trade for a blocking key whose
entire purpose is "probably the same person, worth a closer comparison," not an identity match.
Whoever next tunes resolution quality (a new comparison function, a change to blocking granularity)
should read this as the current behaviour, not assume the raw string is what's being compared.
**No existing test noticed this before it was made** — checked directly, not assumed: every
family-name fixture in `tests/resolve/` before Stage 6b was plain ASCII (`"Mercer"`, `"Okafor"`,
`"Ahmed"`), so accent handling was previously untested in both directions, and the resolution
pipeline's own behaviour on an accented name was unspecified — the same "invariant stated in
prose and exercised by nothing" gap `CLAUDE.md` rule 12 warns about, closed now by
`tests/resolve/test_duckdb_setup.py::test_an_accented_family_name_does_not_raise_and_folds_to_
its_base_letters` (`_soundex("müller") == _soundex("muller")` and `_soundex("josé") ==
_soundex("jose")`), the one test that would notice a future regression of this specific behaviour.

**A known residual gap in the same fix, not resolved by it: a family name with no Latin letters at
all still crashes the entire resolution pass for its whole population.** `_soundex` returns `None`
when nothing letter-shaped survives sanitisation — an entirely non-Latin-script family name (fully
Chinese, Cyrillic, Arabic, Devanagari, etc.) sanitises to nothing, same as an empty string. DuckDB's
own scalar-UDF registration (`con.create_function(...)`, no `null_handling` argument passed)
defaults to `null_handling='DEFAULT'`, under which **a UDF is contractually never allowed to return
`NULL` for a non-`NULL` input** — confirmed directly, not assumed: `resolve_entity_type` raises
`SplinkException` (wrapping DuckDB's own `Invalid Input Error: ... The UDF is not expected to
return NULL values`) the moment even one `Person` in the population being resolved has a family
name that sanitises to nothing, exactly the same "Splink compiles blocking into one SQL statement
over the whole population" blast radius the original hyphen defect had — not the "every non-Latin
name silently blocks with every other one" false-positive risk that seemed the more likely failure
mode before this was checked. **Not fixed here** (Stage 6b's own scope was the crash class a
hyphenated/apostrophised/spaced/digit-bearing Latin name hits, not this one) — **owning phase:
Phase 8**, alongside the resolver-internals work the original soundex finding was filed under.
**The test that would prove it, once owned:** `test_a_non_latin_family_name_does_not_crash_the_
entire_resolution_pass` — a `Person` population including one entirely non-Latin-script family
name (Chinese, Cyrillic, or similar), asserting `resolve_entity_type` does not raise and that
unrelated members of the population still resolve. Not added to the suite un-owned: a permanently
failing test with no fix behind it would be indistinguishable from a real regression to the next
reader, the same reasoning `07_BUILD_PLAN.md`'s own "no skip mechanism" discipline already argues
for treating every failure as real rather than expected.

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
service number that everyone calls.

The two functions the formula leans on, which earlier drafts left undefined:

```
recency(t)   = 0.5 ^ ((now - t) / half_life)          # exponential decay
normalise(x) = 1 / (1 + e^(-(x - midpoint) / scale))  # logistic
```

Five parameters, all per-deployment configuration: α = 0.5, β = 0.2, γ = 0.3,
`half_life` = 90 days, and the logistic's `midpoint` and `scale` calibrated per corpus. Record
the parameter set alongside any stored weight components — a weight computed under one
calibration is not comparable with one computed under another, and a silent recalibration would
reorder every edge-strength filter in every saved investigation. The Glass exposes the normalised result as the edge-strength filter slider.

**`WeightComponents` stores the raw counts, not just the derived float.** `mutual_information` is
corpus-wide — it depends on how the *whole* corpus looks, which changes as more data loads and
again when a caller scopes the formula to a working set rather than the full corpus. `weight` on
`Edge` is a load-time snapshot using the corpus as it stood then, never frozen ground truth:
freezing a single number and calling it the weight would silently go stale as the corpus grows.
`WeightComponents` (`occurrences`, `corpus_pair_count`, `corpus_source_degree`,
`corpus_target_degree`, `corpus_total_occurrences`, `computed_at`) persists exactly what the
formula needs, so a later, more scoped recompute — Phase 3's working-set service — is arithmetic
over stored numbers, never a full corpus rescan.

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
| Louvain | Community detection | Leiden is unavailable on either compute tier (no browser-ecosystem implementation, and the standard Python route is GPL); both tiers run Louvain with a connected-components split pass closing the one hazard Leiden would have avoided — `06_DECISIONS.md` ADR-029 |
| Betweenness centrality | Brokers and cut-outs | Approximate (Brandes with sampling) above 100k nodes |
| Eigenvector / PageRank | Influence | Report alongside clique score, never instead of it |
| k-shortest paths | Pathfinder between two entities | Must respect the access filter; a path through a node the principal cannot see is not returned |
| Temporal motifs | Convoy, relay, burst | See `02_GLASS_FRONTEND.md` §5 |

**`GraphPort.paths` implementation note.** The access predicate is compiled once per call and
applied at *every* step of the traversal — the source vertex, each candidate edge, and each
intermediate vertex (`otherV()`) before it is allowed onto the path — not only checked against
the two endpoints. A path that would have to pass through a node the principal cannot see is
never found at all, rather than found and then filtered, which is what "respect the access
filter" means concretely for a multi-hop traversal.

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
| `datetime` | mixed formats, local times, missing zones | UTC with recorded original offset. A missing offset is an error, not a guess — and so is an **ambiguous date order**: `03/04/2026` is April in the UK and March in the US, and with both in scope (ADR-017) there is no safe default. The connector profile declares `date_order: dmy` or `mdy`; a file with ambiguous dates and no declaration is rejected, named and counted, exactly like a missing offset |
| `person_name` | ordering, diacritics, honorifics, ALL-CAPS surnames | structured given/family, originals retained |
| `postcode` | UK postcode, spacing and case variance | normalised outward and inward code |
| `grid_ref` | British National Grid reference, letter pair plus digits, or a bare easting/northing pair | EPSG:27700 easting and northing, then reprojected to WGS84 like any other coordinate |
| `coordinate_lon` / `coordinate_lat` | a declared-CRS easting/northing pair | WGS84 longitude/latitude, for an `EventRecord` or similar — never a `Location` node property (§7.1) |
| `geometry_ref` | the same pair, reprojected the same way | a deterministic reference into the analytics store's geometry partition — what a `Location` node actually binds (§7.1) |
| `address` | free text | structured, with a gazetteer identifier attached where one is configured — UPRN in the UK, a GNIS feature id, TIGER GEOID or county parcel id in the US. The identifier is an alias, never the key |
| `iban` / `card` | spacing, masking | normalised; card stored as last-four plus a hash, never in full |

Three rules that are not optional:

1. **Never discard the original.** `value_raw` is retained on every normalised property. A
   normaliser bug discovered in month six must be correctable by re-running against the raw
   value, and the original is sometimes itself evidence — CLI suppression is a fact about the
   caller's behaviour, not noise.
2. **Canonicalise before hashing, always.** Every field in a deduplication key passes through
   its Knowledge Adapter first. `start_ts_to_second` means the normalised UTC instant truncated
   to the second, not the source string — two carriers writing `2026-03-10T10:00:00Z` and
   `2026-03-10 10:00:00+00:00` describe the same call, and a hash over raw strings will not say
   so. Hashing raw fields works on a fixture where duplicates are byte-identical and fails on
   real data, which is the worst order to discover it in.
3. **Deduplicate CDRs on a content hash, not on the whole row.** The CoLP deck asks about
   duplicate CDR lines directly. The same call appears twice with different sequence numbers or
   file-level metadata. Hash `(a_party, b_party, start_ts_to_second, duration, direction)` and
   deduplicate on that, retaining every source row reference on the surviving event so the
   provenance chain stays complete.

### 7.1 Coordinate reprojection

`00_ARCHITECTURE.md` §1.2.2 and ADR-017 require reprojection at ingest, never at query time, and
require the source CRS to be declared rather than guessed. `03_CONDUIT_MIDDLEWARE.md` §5.1
requires geometry to live in the analytics store, never on the graph node — a `Location` carries
`geometry_ref` (a plain string, optional), never `lon`/`lat`/`source_x`/`source_y` directly. An
earlier version of this section, and of `default.yaml`, put the coordinates on the node itself;
that was a real defect (geometry in the graph store makes spatial filtering a traversal, the
wrong shape of query), corrected in ontology v6, not patched in place — the CRS reprojection
fixtures were rebuilt against the corrected shape rather than adjusted.

Three Knowledge Adapters produce a `geometry_ref`:

- **`coordinate_lon`/`coordinate_lat`** reproject a source easting/northing pair to WGS84 via
  `pyproj.Transformer` and return a bare coordinate — for an `EventRecord.lat`/`lon` or any other
  property that genuinely wants one, not for a `Location` node.
- **`geometry_ref`** reprojects the same pair and returns a deterministic reference string — a
  hash of `(source_crs, x, y)`, so the same source coordinate always yields the same ref and a
  recipe re-run never mints a second geometry record for one point. This is what a `Location`
  binds.
- **`grid_ref`** parses a British National Grid reference — a single bare string
  (`"TQ 32106 81020"`), or the letter pair and the two numeric offsets already split across three
  columns — into the same kind of `geometry_ref`. No `source_crs` to declare: a grid reference is
  EPSG:27700 by construction, never ambiguous. UK source documents quote grid references directly
  (the HMP analysis is itself a grid), so this is not optional for the target geography.

**A coordinate pair is the first case in this build needing more than one source column for one
transform**, so `FieldBinding` gained `fields: list[str]`, an explicit named list of source
columns, alongside the existing single `field` — still not an expression
(`09_INGEST_STUDIO.md` §4), since nothing computes which columns to combine; the recipe states
them outright. How many columns a transform takes is that adapter's own declared arity
(`knowledge_adapters.ARITY`), not a fixed count: `coordinate_lon`/`coordinate_lat`/`geometry_ref`
take two, `grid_ref`'s split form takes three — a British National Grid reference split across a
letter pair and two numeric columns needs one more field than a plain easting/northing pair, and
nothing about `fields` assumes every multi-column transform needs the same count.

**The matching `GeometryRecord`** (`schemas/analytics.py`) — the reprojected WGS84 point plus the
retained original `source_crs`/`source_x`/`source_y`, the same `value_raw` discipline every other
Knowledge Adapter follows — is what a caller writes into the analytics store's geometry reference
partition under that ref. No Knowledge Adapter writes anywhere itself, and the recipe engine does
not yet write `GeometryRecord`s any more than it writes `EventRecord`s to the analytics store's
served dataset (`services/ingest/__main__.py`'s stated gap) — Phase 2 establishes the correct
storage tier and shape; the reference partition's own versioning and access-controlled read path,
plus polygon storage for a boundary with no single point, ship in Phase 5/5a, the same phases that
build the geospatial connectors and the site grid this table also serves.

Tested against three real projections with real place coordinates, not arbitrary numbers, so a
wrong zone or a transposed axis shows up as a wrong place rather than a plausible wrong number:
EPSG:27700 (OSGB36 British National Grid, both as an easting/northing pair and as bare grid
references), and two NAD83 State Plane zones from different states — EPSG:32139 (Texas Central)
and EPSG:2227 (California Zone III) — proving the two US zones are not interchangeable
(`tests/knowledge_adapters/test_coordinates.py`, `test_grid_ref.py`,
`tests/ingest/test_crs_reprojection.py`).

## 8. `GraphPort` request and response shapes

`packages/ports/graph.py` is the source of truth; this section documents the request/response
shapes it builds on, the same way §9 documents `AnalyticsPort`'s. Port request and response
shapes belong in the domain model, not only in docstrings.

```python
class ExpandRequest(BaseModel):
    node_ids: list[NodeId]
    depth: int = 1                       # 1..4
    edge_types: list[str] | None = None
    direction: Literal["out", "in", "both"] = "both"
    temporal_window: Interval | None = None

class PathRequest(BaseModel):
    source: NodeId
    target: NodeId
    max_hops: int = 6                    # 1..8 — Phase 7 Stage 5, ADR-033: a disclosed,
                                          # reasoned-but-unmeasured ceiling, not a multiplier
    k: int = 1                           # k-shortest paths, 1..10
    edge_types: list[str] | None = None

class Path(BaseModel):
    nodes: list[Node]                    # hydrated — Phase 7 Stage 5, `06_DECISIONS.md` ADR-033
    edges: list[Edge]                    # (was list[NodeId]/list[EdgeId] through Phase 6a)
    length: int

class NeighbourhoodStats(BaseModel):
    node_id: NodeId
    degree: int
    degree_by_type: dict[str, int]

class Subgraph(BaseModel):
    nodes: list[Node]
    edges: list[Edge]
    filtered_count: int = 0              # §8.2 — placeholder until Phase 3
```

### 8.1 Pattern matching

`match()` takes a bounded `PatternQuery`, never free-form Gremlin (ADR-003):

```python
class PatternNode(BaseModel):
    var: str
    entity_type: str | None = None
    node_id: str | None = None   # pins this variable to one already-known node — §8.1's own
                                  # widening, `06_DECISIONS.md` ADR-030

class PatternEdge(BaseModel):
    edge_type: str
    from_var: str
    to_var: str

class PatternQuery(BaseModel):
    nodes: list[PatternNode]
    edges: list[PatternEdge]
    limit: int = 1000
```

A fixed set of Conduit-side builders compiles a `PatternQuery` into Gremlin; the shape itself
cannot express an arbitrary traversal, which is what makes it safe to accept from above the Vault
boundary.

**A pattern may have more than one root, within a real, checked limit — widened in Phase 7 Stage
4 (`06_DECISIONS.md` ADR-030), replacing the single-chain-only restriction this section
previously left undocumented.** Before this widening, `MatchBuilder`'s own compiler could only
express a traversal linearised from one node (`nodes[0]`), walked forward via `.outE()` only — a
node reachable exclusively through a second, independent starting point (a diamond: two roots
converging on a shared node) could not be expressed at all. `08_ACCEPTANCE_SCENARIOS.md` B19
("expand to common contacts across the two principal endpoints") is exactly this shape and is
this build's own binding proof that the restriction had to be lifted, not merely documented.

**The real mechanism, checked against a live ArcadeDB instance rather than assumed from the
TinkerPop spec.** The natural general solution — Gremlin's own `match()` step, which finds every
consistent variable binding across independently-expressed traversal fragments — does not work on
this adapter: ArcadeDB's own Gremlin engine rejects a `match()` fragment that introduces a
genuinely independent second enumeration (a fragment starting its own fresh `V()`), confirmed
directly by testing the simplest possible case with no filters at all. The mechanism this build
uses instead is narrower and does not need `match()`: **every root beyond the first must be
pinned to an already-known `node_id`** — which is B19's own real shape (the analyst has already
selected both "principal endpoints"; the query discovers their common contacts, not the endpoints
themselves). The primary root's own chain is walked forward exactly as the single-chain compiler
already does; each pinned secondary root's own chain to the convergence point is reversed into a
`.where()` reachability check ending in `.has("id", <the known id>)` — proving "this known node
also reaches the same point," without ever needing to enumerate or bind a second, independent
root. **An open (unpinned) second root remains unsupported.** There is no general join to fall
back to on this adapter; a pattern needing one is rejected by the builder with a specific error
naming the unbound root, not silently mis-compiled.

**What this changes for a caller.** `PatternNode.node_id` is the only new surface: set it to pin
a variable to a specific, already-known node. A pattern where every node is either the first root
or reachable by a forward chain from it compiles exactly as before (byte-identical Gremlin,
proven by a dedicated no-regression test). A pattern with additional roots compiles only if every
one of them is pinned and its own chain converges on a variable the primary chain also reaches;
anything else — an unpinned second root, or a chain that never converges — is a compile-time
error, not a silent wrong answer.

**`PatternQuery`'s own absence of a negation/"must not exist" clause is load-bearing for
something outside pattern matching itself, not only a scope limit contained here — read this
before adding one.** `06_DECISIONS.md` ADR-037's own amendment (Phase 7 Stage 6, the corpus-wide
change stream a saved-pattern monitor watches) proves the stream misses no possible match —
including one created by removing something — on exactly two facts: `GraphPort`'s own absence of
a hard-delete method (`§2.4`, above) and this schema's own absence of a negation clause, checked
directly against `PatternNode`/`PatternEdge` above rather than assumed. A pattern language with no
"must not exist" shape cannot have a match newly created by removing something, because removing
an edge or node can only shrink a match set under this schema, never grow it. **If negation is
ever added — an obvious future want, letting a pattern express "an `Endpoint` with no `SAME_AS`
edge to a hotlisted identifier," say — this argument breaks even if `GraphPort` still has no
hard-delete:** a superseded element is still a write the change stream captures, but the *effect*
of that write can now be "a previously-blocking match now completes because the blocking element
is gone" — a state change the corpus-wide change stream's own entry shape (source, node/edge ids
*touched*) does not obviously encode, since the newly-completed match's own nodes/edges were not
what was written. **The test that would need to exist at that point:**
`test_monitor_fires_on_a_match_completed_by_a_negated_clause_no_longer_blocking`, proving whatever
mechanism exists then (the change stream as built today, or a revised one) still lets a monitor
watching a negated pattern fire correctly once the blocking element is superseded — the same
proof `06_DECISIONS.md` ADR-037's own accepted case already requires for resolution/manual-
assertion writes, for the shape negation adds rather than the shape it replaces. Until negation
exists, this is a documented dependency, not a gap — recorded here as well as in `06_DECISIONS.md`
ADR-037 and `§2.4` above, so whoever adds it reads this at the point they'd otherwise miss it, and
`06_DECISIONS.md` ADR-030's own "revisit if" (a general multi-root join or negation added to the
pattern language) is exactly the trigger for re-checking this argument, not a coincidence.

### 8.2 Additions since Phase 1

Phase 1 shipped `upsert_nodes`/`upsert_edges`/`get_node`/`expand`/`paths`/`match`/
`neighbourhood_stats`/`apply_schema`/`revert_schema` against `00_ARCHITECTURE.md` §2.1's
illustrative sketch. Phase 2 added five more, without re-litigating the sketch first, the same
way Phase 1 itself went beyond it for transaction management and schema application:

- **`find_node(entity_type, identifier_field, value, principal)`.** The recipe engine's
  `on_match: reference` (§7) needs to look an entity up by its declared identifier before
  deciding whether to create a new node, and `match()`'s `PatternQuery` has no property-value
  predicate — only an entity type.
- **`get_node(..., include_superseded=False)`.** The one way to retrieve a node
  `supersede_node` has replaced; otherwise excluded from every read by default. Lifts only the
  supersession exclusion — classification and `handling_code` still apply underneath.
- **`supersede_node(node_id, replacement, tx) -> NodeId`.** Writes `replacement` as a new node
  at `revision = node_id`'s current revision + 1, sets `node_id`'s own `AuditStub.superseded_by`
  to the new id, and returns it. The old node is never deleted; every prior revision and the full
  `superseded_by` chain stays individually retrievable. **Confirmed empirically that ArcadeDB (like
  TinkerPop generally) cannot relink an existing edge's endpoints** — `UPDATE E1 SET out = #rid`
  reports success but leaves `@out`/`@in` unchanged — so every edge incident to `node_id` is
  cloned onto the replacement (provenance, handling, interval and occurrences preserved exactly)
  and the originals are marked `reverted`, rather than repointed in place. The clone-and-revert is
  wrapped in the same transaction as the rest of the operation: a failure partway rolls back to
  zero trace of the partial write, proven by a conformance case that injects a failure after N
  clones and asserts the pre-operation graph is exactly restored. **Measured, not estimated:**
  superseding a node of degree 5,000 took 41 seconds against a single ArcadeDB instance — a real
  ceiling, not a projected one. Above some threshold below that, synchronous supersession inside
  one request is the wrong shape; Phase 3's scope (`07_BUILD_PLAN.md`) records making it a
  background job past a configured degree rather than discovering the timeout in production.
- **`supersede_edge(edge_id, replacement, tx) -> EdgeId`.** The same operation for an edge —
  simpler, since nothing references an edge by id except an assessment's evidence list (§5), which
  is expected to follow `superseded_by`, not be silently rewritten, so there is nothing to
  repoint.
- **`revert_elements(node_ids, edge_ids, tx) -> None`.** Sets `AuditStub.reverted` on existing
  elements; `services/ingest`'s `revert_load` is the only caller. No `principal` argument, unlike
  every read method — this is a backend write attributed by the caller's own audit trail (the
  load ledger), not a principal-scoped read. A reverted element is invisible to every read
  afterwards, any clearance, and is never actually deleted.

Phase 3 added one more, closing the `filtered_count` gap this section used to describe as
outstanding (below):

- **`expand_candidate_count(req) -> int`.** The unfiltered half of `Subgraph.filtered_count`'s
  comparison. Same seed set, depth, edge-type and temporal scope as `expand(req, principal)`, but
  with neither access axis applied — only structural exclusion (reverted, superseded) carries
  over, since those aren't principal-dependent. No `principal` argument, matching
  `revert_elements`: not a principal-scoped read, and it returns only a bare count, never a node,
  an id or a property, so it cannot itself disclose which nodes are hidden or why.
  `services/api`'s Working-Set Service is the only sanctioned caller — see below.

Phase 7 Stage 1 added the first bulk read this port has ever had (`06_DECISIONS.md` ADR-025):

- **`list_nodes(entity_type, principal, cursor=None, limit=500) -> ListNodesPage`.** "Every
  `Person` node" — the corpus-wide resolution trigger's own population fetch — has no other route
  to it: `find_node`/`search_nodes` need an exact identifier value, `expand`/`paths` need a known
  seed, `match` needs a bounded pattern. Paginated, access-controlled exactly like every other
  read. `ListNodesPage = {nodes: list[Node], next_cursor: NodeId | None}`; `next_cursor is None` is
  the *only* correct exhaustion signal — a short page is not one, since a page can legitimately
  return zero visible nodes while more exist further on if that page's key range happens to be
  entirely hidden from `principal`. **Not `limit_exceeded`'s contract**: that typed error is
  analyst-facing (three interactive options a person chooses between); this method's only caller
  is a service principal that pages, with no one to offer a choice to. **Cursor: keyset on `id`
  (a ULID, lexicographically sortable and fixed at creation), not an offset** — a page selects
  `id > cursor`, ordered by `id`, so a node written after a scan starts is picked up by a later
  page in the ordinary case rather than skipped or duplicated. Not snapshot isolation: a node
  whose id happens to sort behind the current cursor at the moment it's written (only possible
  under ULID clock skew across writers) could be missed by that pass — acceptable given ADR-025's
  own "re-run whole, never resume from a checkpoint" recovery model, which corrects a missed node
  on the next triggered run rather than this method guaranteeing a perfect snapshot it cannot
  cheaply give. `services/resolve/trigger.py` is the only caller today.

**`Subgraph.filtered_count`** stayed the Phase 1 placeholder `0` through Phase 2. It stood in for
a specific question `GraphPort` alone could not answer: of the nodes an `expand` call excluded,
how many were excluded because of the *access filter* specifically, as opposed to depth, edge-type
or temporal scoping simply not reaching them? Answering that needs both the filtered and
unfiltered node sets compared under one authority, and a single `expand()` call only ever sees the
already-filtered result — computing the unfiltered side *inside* the adapter would mean a second,
less-audited query channel with no caller to hold both results and reconcile them.

Phase 3 closes the gap with `expand_candidate_count` above, called by the Working-Set Service
alongside the ordinary filtered `expand()`: `expand_candidate_count(req) - len(filtered.nodes)` is
`filtered_count`. This is the one place the comparison can be made safely — the Working-Set
Service already holds the filtered result under its own authority, and the unfiltered count adds
no channel beyond a bare integer that cannot itself leak which nodes are hidden. See
`03_CONDUIT_MIDDLEWARE.md` §4 for the read-time projection this feeds into, and §3.2 for
`filtered_count`'s place in the delta protocol.

## 9. `AnalyticsPort` request and response shapes

`packages/schemas/analytics.py` is the source of truth. Columnar aggregation over the event table
§3 describes. Every read method takes an `EventFilter` the adapter injects into its own `WHERE`
clause before aggregating — there is no `raw_sql` escape hatch, deliberately
(`00_ARCHITECTURE.md` §2.2): an arbitrary SQL string cannot be access-filtered, the same reason
`GraphPort` never accepts free-form Gremlin.

```python
class EventRecord(BaseModel):
    event_id: str
    edge_id: EdgeId                  # the graph edge this row is one occurrence of
    edge_type: str
    source_id: NodeId
    target_id: NodeId
    occurred_at: datetime
    duration_s: float | None = None
    cell_site: str | None = None
    lat: float | None = None         # -90..90
    lon: float | None = None         # -180..180, travels with lat or not at all
    direction: str | None = None
    properties: dict[str, Any] = {}
    investigation_scope: str
    handling: Handling               # carried per row, so a filtered query never joins back
                                      # to the graph store to know what it may not show

class EventFilter(BaseModel):
    investigation_scope: str         # required — the event tables partition on it
    window: Interval | None = None
    node_ids: list[NodeId] = []
    edge_types: list[str] = []
```

**`GeometryRecord`** — the analytics store's geometry reference partition, §7.1's
`geometry_ref`/`grid_ref` Knowledge Adapters produce the reference a `Location` node points at:

```python
class GeometryKind(StrEnum):
    POINT = "point"
    POLYGON = "polygon"              # a jurisdiction/boundary with no single point (Phase 5)

class GeometryRecord(BaseModel):
    geometry_ref: str
    version: int                     # the reference partition's own version, not per-investigation
    kind: GeometryKind = GeometryKind.POINT
    lon: float | None = None         # -180..180, WGS84 — POINT only
    lat: float | None = None         # -90..90, WGS84 — POINT only
    source_crs: str | None = None
    source_x: float | None = None    # retained original, never discarded — POINT only
    source_y: float | None = None
    geometry_wkb: bytes | None = None  # POLYGON only
    handling: Handling
```

No `investigation_scope` here, unlike `EventRecord` — reference data is versioned as a whole
rather than scoped per investigation (`version` above), not per document. `handling` **is** carried
per row: a site's own control-point/grid geometry is exactly as sensitive as the `Location`
entities it backs, so it gets the same per-row access-control discipline `EventRecord` already has,
via the same `AccessFilter`. This partition's versioning/access-controlled read path
(`AnalyticsPort.get_geometry`/`get_geometries`/`list_boundaries`) and polygon storage (`kind`/
`geometry_wkb`) both shipped in Phase 5's known-gaps closure.

```python
class HistogramBucketing(StrEnum):
    FIXED_INTERVAL = "fixed_interval"
    WEEKDAY_HOUR = "weekday_hour"
    CATEGORICAL = "categorical"       # buckets by an EventRecord/properties field

class HistogramRequest(BaseModel):
    filter: EventFilter
    bucketing: HistogramBucketing = HistogramBucketing.FIXED_INTERVAL
    interval_seconds: int | None = None   # required for FIXED_INTERVAL
    field: str | None = None              # required for CATEGORICAL

class HistogramBucket(BaseModel):
    start: datetime | None = None     # fixed_interval
    end: datetime | None = None       # fixed_interval
    weekday: int | None = None        # weekday_hour — 0 = Monday
    hour: int | None = None           # weekday_hour
    label: str | None = None          # categorical
    count: int

class Histogram(BaseModel):
    bucketing: HistogramBucketing
    buckets: list[HistogramBucket]
    total: int
```

```python
class GeoBinRequest(BaseModel):
    filter: EventFilter
    precision: int                    # 1..12 — higher is finer

class GeoBin(BaseModel):
    cell_id: str
    centroid_lon: float
    centroid_lat: float
    count: int
```

**`geo_bins` is not a geohash.** No base-32 cell-id encoding, and bins are equal-*area* via a
sinusoidal projection (`x = lon / cos(lat)`, gridded uniformly), not equal-*degree* — a degree of
longitude at 55°N is about 57% the width, on the ground, of one at the equator, so an
equal-degree grid gives the UK materially narrower bins than the US at the same precision and a
cross-region density comparison reads wrong. Each row's own latitude sets its longitude bin
width; there is no single global one.

```python
class BaselineRequest(BaseModel):
    filter: EventFilter
    baseline_window: Interval
    comparison_window: Interval
    bucketing: HistogramBucketing = HistogramBucketing.FIXED_INTERVAL
    interval_seconds: int | None = None
    field: str | None = None

class BaselineResult(BaseModel):
    baseline_count: int
    comparison_count: int
    baseline_rate_per_bucket: float
    comparison_rate_per_bucket: float
    ratio: float | None               # null when baseline_count is 0 — never divide to guess

class CrossFilterDimension(BaseModel):
    name: str
    bucketing: HistogramBucketing
    interval_seconds: int | None = None
    field: str | None = None

class CrossFilterRequest(BaseModel):
    filter: EventFilter
    dimensions: list[CrossFilterDimension]   # at least one
```

`cross_filter` runs every dimension against the same `EventFilter`, so the timeline, the map and
the histogram panel restrict in lockstep (`08_ACCEPTANCE_SCENARIOS.md` A3) — one request, one
compiled access predicate, rather than one call per panel that could disagree with itself under
concurrent writes.

## 10. `ComputePort` request and response shapes

`packages/schemas/compute.py` is the source of truth — Phase 7 Stage 2, ahead of any adapter
(standing rule 1). Graph algorithms: centrality, community detection, the Clique Metric, temporal
motifs (`00_ARCHITECTURE.md` §2.3).

```python
CentralityMetric = Literal[
    "degree", "weighted_degree", "betweenness", "eigenvector", "pagerank", "clustering_coefficient",
]

class CentralityRequest(BaseModel):
    subgraph: Subgraph
    metric: CentralityMetric

class CommunityRequest(BaseModel):
    subgraph: Subgraph                # Louvain, connected-components split — ADR-029:
                                       # Leiden is unavailable on either compute tier

class CliqueMetricRequest(BaseModel):
    subgraph: Subgraph
    k_min: int = 4                    # §6.2's own defaults, deployment-overridable like the
    k_max: int = 30                   # edge-weight formula's α/β/γ, never hardcoded

MotifType = Literal["convoy", "relay", "burst"]

class MotifRequest(BaseModel):
    subgraph: Subgraph
    motif_type: MotifType
    distance_tolerance: float | None = None       # named from 02_GLASS_FRONTEND.md's own
    time_tolerance_seconds: float | None = None   # Convoy analysis line

class MotifMatch(BaseModel):
    motif_type: MotifType
    node_ids: list[NodeId]
    interval: Interval | None = None
```

**No `Principal` on any `ComputePort` method, deliberately — unlike `GraphPort`/`AnalyticsPort`,
which carry one everywhere.** Every population-carrying request above embeds `Subgraph` — the same
type `GraphPort.expand`/`match` already return, already access-filtered — rather than an implicit
"compute over the whole graph." This is not an oversight in `00_ARCHITECTURE.md` §2.3's own
illustrative sketch (which never had one either); it is the same shape `services/resolve/
projection.py`'s `compute_clusters` already uses successfully: a pure function over whatever
population it is handed, correct because its caller fetches through an access-filtered path first,
never because the function checks anything itself. The alternative — threading a `Principal`
through every tier — would need a browser Web Worker with no server-side session, an in-process
`rustworkx` call with no store handle, and a Spark/Vault batch job to each independently compile an
access predicate, which only `GraphPort` adapters do today and which Tier 1/2 cannot do at all:
they never hold a store connection, so a `Subgraph` is structurally the only population they can
ever reach.

**What this makes true by construction, and what it does not.** A `ComputePort` adapter cannot leak
a node it was never given — `tests/conformance/compute_port/test_suite.py`'s
`test_centrality_never_returns_a_node_outside_the_requested_subgraph` proves this structurally,
for every registered tier. It does **not** prove that a real caller always assembles that
`Subgraph` through an access-filtered fetch first — the same residual `compute_clusters` has, which
`tests/resolve/test_projection_access_control.py` closes for it directly (real `GraphPort` adapter,
two principals, one hidden node, fed into the pure function). `ComputePort`'s own first real caller
(the metrics panel, Phase 7 Stage 3) owes the equivalent test the moment it exists — named here so
it is not assumed to happen automatically once the route is built.

**`temporal_motifs` is real as a type, not as a claimed capability.** `MotifRequest`/`MotifMatch`
exist because `_pending_port_placeholders.py`'s retirement needed real content for every one of
`ComputePort`'s five names, not because any phase's own bullet list has claimed the convoy/relay/
burst algorithms themselves — `07_BUILD_PLAN.md`'s Phase 7 outcome bullet names only "Degree,
betweenness, eigenvector, clustering coefficient, Louvain, Clique Metric." Recorded in Phase 7's own
known-gaps list, not discovered only at the exit gate.
