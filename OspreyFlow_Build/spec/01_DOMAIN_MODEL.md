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
  - {name: COMMUNICATED_WITH, from: [Endpoint], to: [Endpoint], directed: true, temporal: true, basis: direct}
  - {name: USES,              from: [Person], to: [Endpoint, Device], directed: true, basis: direct}
  - {name: PRESENT_AT,        from: [Person, Device, Vehicle], to: [Location], temporal: true, basis: direct}
  - {name: MENTIONED_IN,      from: ["*"], to: [Document], directed: true, basis: direct}
  - {name: ASSOCIATE_OF,      from: [Person], to: [Person], directed: false, basis: direct}
  - {name: FAMILY_OF,         from: [Person], to: [Person], directed: false, properties: [relation], basis: direct}
  - {name: MEMBER_OF,         from: [Person], to: [Organisation], basis: direct}
  - {name: TRANSACTED,        from: [Asset, Endpoint], to: [Asset, Endpoint], temporal: true, basis: direct}
  # By convention the source is an Endpoint of kind `imsi` only — see the
  # prose below. Not schema-enforced: `from`/`to` check entity type, not
  # `endpoint_kind`.
  - {name: PAIRED_WITH,       from: [Endpoint], to: [Device], directed: true, temporal: true, basis: direct}
  # `basis` is required on every authored type (ADR-081); `colour` (a data-channel name) and
  # `thickness` (1 to 5) are optional. The loader injects the two system types itself: `SAME_AS` is
  # `probabilistic`, `NOT_SAME_AS` has no basis.
  - {name: SAME_AS,           from: ["*"], to: ["*"], directed: false, system: true, basis: probabilistic}
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

**An entity type may name an icon (ADR-079).** `icon` is optional and is one of twenty names (person,
people, building, bank, phone, mail, device, pin, calendar, document, vehicle, box, key, globe, card,
shield, flag, link, tag, camera) held as a closed list in `ontology.schema.json`; the loader refuses
any other. The Glass draws it inside the type's shape. It adds to shape and hue and never replaces
them, so the rule above is unchanged. The default ontology gives every type one. Adding the field did
not move the ontology version: nothing a recipe writes, an index or an adapter reads changed.

### 1.2 The loaded schema's own shape

The YAML above validates into a typed Python object, `OntologySchema` — what `GraphPort.
apply_schema` takes and what the schema/migration runner turns into vertex/edge types and the
indexes `04_VAULT_BACKEND.md` §1.4 describes:

```python
class PropertyDef(BaseModel):
    name: str
    type: PropertyType             # STRING, DATETIME, INTEGER, FLOAT, BOOLEAN, ENUM
    indexed: bool = False
    required: bool = False
    sensitivity: Literal["low", "medium", "high"] | None = None
    values: list[str] | None = None   # required when type is ENUM

class ResolutionConfig(BaseModel):
    blocking: list[str] = []
    comparisons: list[str] = []

class EntityTypeDef(BaseModel):
    name: str
    pole_class: PoleClass
    channel: str
    shape: str
    icon: str | None = None        # ADR-079: a name from the closed list in ontology.schema.json
    identifiers: list[str] = []
    properties: list[PropertyDef] = []
    resolution: ResolutionConfig | None = None

class EdgeTypeDef(BaseModel):
    name: str
    from_types: list[str]          # `from` in YAML
    to_types: list[str]            # `to` in YAML
    directed: bool = True
    temporal: bool = False
    system: bool = False
    basis: Literal["direct", "probabilistic"] | None = None   # ADR-081; required in YAML, None only for NOT_SAME_AS
    colour: str | None = None      # one of the nine data-channel names; None keeps the ordinary line colour
    thickness: int | None = None   # 1 to 5; None keeps the weight-only width
    label: str | None = None       # ADR-091: display name in sentence case; None derives it from name
    aliases: list[str] = []        # ADR-090 Am1: other stored labels that read as this type
    direct_since: datetime | None = None   # ADR-090: promoted as Direct; links written before stay probabilistic
    analyst_defined: bool = False  # ADR-090: proposed by an analyst, never authored in YAML
    hidden: bool = False           # ADR-090: a proposal's own storage label; never offered or sent to the Glass
    properties: list[PropertyDef] = []

class OntologySchema(BaseModel):
    version: int
    entity_types: list[EntityTypeDef]
    edge_types: list[EdgeTypeDef]
    storage_aliases: dict[str, str] = {}   # ADR-090: a proposal's storage label -> the name its links read as
    overlay_revision: int = 0              # ADR-090: rises at each promotion and retirement; `version` does not
```

`PropertyDef` is one property line from the YAML above (`{name: family_name, type: string,
indexed: true, required: true}`) — an `enum`-typed property must declare `values`, enforced at
validation time rather than left to fail later against real data. `EntityTypeDef`/`EdgeTypeDef`
are one whole entry from `entity_types`/`edge_types`; `resolution` is `None` for an entity type
the ontology declares no blocking/comparison rules for (`Location`, `Device`, and every other type
with no `resolution:` block in the example above) rather than an empty `ResolutionConfig` standing
in for "not configured." `OntologySchema` is the whole loaded, validated document — the object
`apply_schema` and `revert_schema` (§2.4) both operate on.

**A relationship type says what stands behind a link of it, and how it is drawn (ADR-081).** `basis`
is `direct` (a loaded, established record stands behind the link: a device paired with a call
record, an ownership an evidential record states) or `probabilistic` (statistically derived, or an
analyst's declaration). It is required on every authored type: an ontology that omits it, or names
anything but those two, is refused at load, so there is no unclassified type. The loader injects
`SAME_AS` as `probabilistic`; `NOT_SAME_AS` is an analyst's judgement that two nodes are different,
not a claim that a link exists, so it sits outside the rule and has no basis (Amendment 1). The line
style is not authored: the Glass draws a Direct link solid and a Probabilistic one dotted
(`02_GLASS_FRONTEND.md` §4). A declaration may also carry a `colour`, one of the nine data-channel
names that an entity type's `channel` already uses, and a `thickness`, a whole number from 1 to 5;
the loader refuses anything else. A declaration may carry a `label` (ADR-091), the name a person
reads, in sentence case ("Communicated with"); `name` stays the key stored on every link, and a blank
label is refused. The test that would fail if any of this were broken is
`tests/ontology/test_relationship_basis.py`. A link may carry a basis of its own (`Edge.basis`, ADR-081 step B, Amendment 2): a link of a
Direct type marked `probabilistic`, statistically derived or declared by an analyst with a reason that
is kept in the link's change history. A link written without one takes its type's basis, which every
loader and the resolution engine write; `effective_basis` reads the two together, and a link of a
Probabilistic type is probabilistic whatever is stored on it. A person never promotes a link to Direct.
The Ingest Studio's refusal of a probabilistic type is built (ADR-081 step D, `recipe_rules.py`).

**Analysts may propose a relationship type (ADR-090 and its Amendments).** The ontology in force is
`default.yaml` plus every proposal, composed by one function (`services/api/link_types.py`'s
`compose_ontology`) at start-up and after each proposal and decision. A pending proposal is usable at
once in its own case, the cases branched from it, and any case where the caller can see one of its
links; it is probabilistic. Each proposal's links are stored under a label of their own,
`<name>__<proposal id>`, declared as a `hidden` type so the graph store accepts them, and
`storage_aliases` makes that label read as the name the links answer to: the proposal's own while
pending, rejected, withdrawn or retired, the promoted name once promoted, merged or renamed. So no
link is ever rewritten, restricted ones included: renaming, merging and retiring change one mapping.
A type promoted as Direct is Direct only for links written from `direct_since`. The tests that would
fail are `tests/services/api/test_link_type_overlay.py` (the composition),
`test_link_type_service.py` (who may do what, and what each case is offered),
`test_link_type_routes.py` (levels, roles, and that `/v1/ontology` never sends a storage label),
`test_link_type_store.py` (an administrator reads only their own unit's, on real Postgres) and
`tests/conformance/graph_port/test_type_aliases.py` (labels written and read on real ArcadeDB).

Applying a schema returns a report, not a bare success flag:

```python
class SchemaReport(BaseModel):
    migration_id: str
    applied_entity_types: list[str]
    applied_edge_types: list[str]
    indexes_created: list[str]
    reversible: bool = True
```

`migration_id` is the join key `revert_schema` takes back — the same "every write is addressable
and revertible" discipline the audit stub (§2.4) applies to element-level writes, applied here at
the schema level. `reversible` is `False` only for a migration the adapter cannot cleanly undo
(a destructive index change, say); the loader surfaces that before the migration runs, not after.

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
compiled against, not a second, privileged path around it: access control lives in the adapter's
own traversal, never a bypass applied after retrieval. A future
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
ADR-037's own amendment (the corpus-wide change stream a saved-pattern monitor watches) proves
the stream misses no possible match — including one created by removing
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
crash fix it shipped alongside (`services/resolve/duckdb_setup.py::_soundex`).**
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
family-name fixture in `tests/resolve/` before this fix was plain ASCII (`"Mercer"`, `"Okafor"`,
`"Ahmed"`), so accent handling was previously untested in both directions, and the resolution
pipeline's own behaviour on an accented name was unspecified — an invariant stated in prose and
exercised by nothing, closed now by
`tests/resolve/test_duckdb_setup.py::test_an_accented_family_name_does_not_raise_and_folds_to_
its_base_letters` (`_soundex("müller") == _soundex("muller")` and `_soundex("josé") ==
_soundex("jose")`), the one test that would notice a future regression of this specific behaviour.

**A residual gap in the same fix, found and then fixed separately, 22 September 2026 — recorded
here as closed, not left reading as still open.** `_soundex` returns `None` when nothing
letter-shaped survives sanitisation — an entirely non-Latin-script family name (fully Chinese,
Cyrillic, Arabic, Devanagari, etc.) sanitises to nothing, same as an empty string. DuckDB's own
scalar-UDF registration defaulted to `null_handling=DEFAULT`, under which **a UDF is contractually
never allowed to return `NULL` for a non-`NULL` input** — confirmed directly, not assumed:
`resolve_entity_type` raised `SplinkException` (wrapping DuckDB's own `Invalid Input Error: ... The
UDF is not expected to return NULL values`) the moment even one `Person` in the population being
resolved had a family name that sanitised to nothing, exactly the same "Splink compiles blocking
into one SQL statement over the whole population" blast radius the original hyphen defect had —
not the "every non-Latin name silently blocks with every other one" false-positive risk that
seemed the more likely failure mode before this was checked.

**Fixed:** `services/resolve/duckdb_setup.py::new_connection` registers `soundex` with
`null_handling=duckdb.func.FunctionNullHandling.SPECIAL` — DuckDB now accepts the `NULL` this
function was already correctly returning, so a person with no letter-shaped soundex key simply
never blocks with anyone via that rule (standard SQL: `NULL` never equals `NULL`), the same
"no blocking key" outcome an empty `family_name` already produced, instead of crashing before that
behaviour is ever reached. Proven at the actual point of failure — a real, registered DuckDB
connection, not only the pure `_soundex` function, which never crashed —
`tests/resolve/test_duckdb_setup.py::test_a_fully_non_latin_family_name_does_not_crash_the_
registered_udf`, verified non-vacuous by reverting the fix, watching the real
`duckdb.InvalidInputException` this defect always raised, and restoring it. `tests/scenarios/
fixtures/fixture_corp.py` now carries a non-Latin-script resolution pair too, so this fix is
exercised by every run of Fixture Corp's own real resolution pass, not only by its own dedicated
unit test.

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

### Notes on links

An analyst can attach plain-text notes to a link (`06_DECISIONS.md` ADR-075). Notes are analytical
working, not graph content: they are kept in the investigation's control-plane store and never written to the
graph, so a note cannot change a link, its weight, its provenance or what resolution does.

```python
class LinkNote(BaseModel):
    id: str
    investigation_id: str
    edge_id: EdgeId
    author: PrincipalId
    body: str                     # plain text, 1 to 4,000 characters, never interpreted as markup
    created_at: datetime
    edited_at: datetime | None
    mine: bool                    # worked out per reader when served; never stored
```

A link has any number of notes, listed newest first. A note has no handling marking of its own: it is
shown to exactly the principals the link is shown to (the link's own marking and both of its ends clear
that principal's clearance, and the link is in the investigation's working set), so a link a principal
cannot see has no notes they can read, and asking for them answers as a link that does not exist.
Only a note's author edits or removes it.

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
formula needs, so a later, more scoped recompute — the working-set service — is arithmetic over
stored numbers, never a full corpus rescan.

> **PROPOSED, not yet the design (ADR-058 D4).** A bulk load would weigh every edge it writes against the corpus as it
> stands at the end of the load, with this formula and these `WeightComponents` unchanged and `computed_at` recording the
> end of the load, instead of against the corpus as it stood when each edge was written. A bulk-loaded edge and an
> upsert-loaded one would then differ in the weight value but not in the stored counts it is computed from.

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

**Where the canonical value is stored, and what `identifiers:` means — clarified after an
ambiguity in this document cost an analyst the ability to find what they had just ingested.**

For `Person`, `Device`, `Location` and `Organisation`, an `identifiers:` entry is a **property
name**: a `Person` carries `nino`, a `Device` carries `imei`, and search matches them directly.

For `Endpoint` it is not. `identifiers: [e164, handle, email, imsi]` names the **kinds** of
addressable thing an `Endpoint` can be; the canonical value always lives in the single
`value_normalised` property (`indexed: true, required: true`) and the kind in `endpoint_kind`.
The two lists deliberately do not match — `endpoint_kind`'s enum says `msisdn` where
`identifiers` says `e164`, and carries `iban` and `card`, which that list does not. **Nothing
writes an `e164` property, and nothing should:** duplicating the value into a kind-specific
property would be two statements of one fact, and the collapse this section exists to guarantee
("must resolve to one `Endpoint`") depends on there being exactly one canonical field.

**What went wrong before this was written down.** `GraphPort.search_nodes` read `identifiers:` as
property names for every type, so it looked for an `e164` property that no ingest, seeder or
fixture has ever written. Every ingested `Endpoint` was therefore invisible to search: measured
over the wire, `POST /v1/search` for a number a load had demonstrably just created returned **0
hits**. The graph conformance suite did not catch it because its own case constructed an
`Endpoint` *with* an `e164` property — a shape the engine never emits. Search now matches
declared identifiers **and** every property the ontology marks `indexed: true`, which is the
ontology's own statement of "a field you look things up by";
`test_search_nodes_finds_an_endpoint_in_the_shape_the_engine_actually_writes` is the case that
fails if it regresses.

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
served dataset (`services/ingest/__main__.py`'s stated gap) — the correct storage tier and shape
are established; the reference partition's own versioning and access-controlled read path, plus
polygon storage for a boundary with no single point, are not yet implemented — they ship alongside
the geospatial connectors and the site grid this table also serves.

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
    max_hops: int = 6                    # 1..8 — ADR-033: a disclosed,
                                          # reasoned-but-unmeasured ceiling, not a multiplier
    k: int = 1                           # k-shortest paths, 1..10
    edge_types: list[str] | None = None

class Path(BaseModel):
    nodes: list[Node]                    # hydrated — `06_DECISIONS.md` ADR-033
    edges: list[Edge]                    # (previously list[NodeId]/list[EdgeId])
    length: int

class NeighbourhoodStats(BaseModel):
    node_id: NodeId
    degree: int
    degree_by_type: dict[str, int]

class Subgraph(BaseModel):
    nodes: list[Node]
    edges: list[Edge]
    filtered_count: int = 0              # §8.2 — computed via expand_candidate_count, see below
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

**A pattern may have more than one root, within a real, checked limit — widened
(`06_DECISIONS.md` ADR-030), replacing the single-chain-only restriction this section
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
before adding one.** `06_DECISIONS.md` ADR-037's own amendment (the corpus-wide change stream a
saved-pattern monitor watches) proves the stream misses no possible match — including one created
by removing something — on exactly two facts: `GraphPort`'s own absence of
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

### 8.2 Additions beyond the illustrative sketch

The illustrative sketch in `00_ARCHITECTURE.md` §2.1 covers `upsert_nodes`/`upsert_edges`/
`get_node`/`expand`/`paths`/`match`/`neighbourhood_stats`/`apply_schema`/`revert_schema`. Five
more methods were added later, without re-litigating the sketch first, the same way the original
set itself went beyond it for transaction management and schema application:

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
  one request is the wrong shape; making it a background job past a configured degree, rather than
  discovering the timeout in production, is planned but not yet implemented.
- **`supersede_edge(edge_id, replacement, tx) -> EdgeId`.** The same operation for an edge —
  simpler, since nothing references an edge by id except an assessment's evidence list (§5), which
  is expected to follow `superseded_by`, not be silently rewritten, so there is nothing to
  repoint. An analyst's correction of a link (ADR-080) is the one caller outside the loads and
  resolution. Link notes (ADR-075) are also kept against an edge id, so the service that supersedes a
  link for an analyst moves its notes to the new id in the same step; the old link and the change
  between them stay readable through the change history.
- **`revert_elements(node_ids, edge_ids, tx) -> None`.** Sets `AuditStub.reverted` on existing
  elements; `services/ingest`'s `revert_load` is the only caller. No `principal` argument, unlike
  every read method — this is a backend write attributed by the caller's own audit trail (the
  load ledger), not a principal-scoped read. A reverted element is invisible to every read
  afterwards, any clearance, and is never actually deleted.

One more method closes the `filtered_count` gap this section used to describe as outstanding
(below):

- **`expand_candidate_count(req) -> int`.** The unfiltered half of `Subgraph.filtered_count`'s
  comparison. Same seed set, depth, edge-type and temporal scope as `expand(req, principal)`, but
  with neither access axis applied — only structural exclusion (reverted, superseded) carries
  over, since those aren't principal-dependent. No `principal` argument, matching
  `revert_elements`: not a principal-scoped read, and it returns only a bare count, never a node,
  an id or a property, so it cannot itself disclose which nodes are hidden or why.
  `services/api`'s Working-Set Service is the only sanctioned caller — see below.

The first bulk read this port has ever had (`06_DECISIONS.md` ADR-025):

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

**`Subgraph.filtered_count`** started as a placeholder `0`. It stood in for
a specific question `GraphPort` alone could not answer: of the nodes an `expand` call excluded,
how many were excluded because of the *access filter* specifically, as opposed to depth, edge-type
or temporal scoping simply not reaching them? Answering that needs both the filtered and
unfiltered node sets compared under one authority, and a single `expand()` call only ever sees the
already-filtered result — computing the unfiltered side *inside* the adapter would mean a second,
less-audited query channel with no caller to hold both results and reconcile them.

The gap is closed by `expand_candidate_count` above, called by the Working-Set Service
alongside the ordinary filtered `expand()`: `expand_candidate_count(req) - len(filtered.nodes)` is
`filtered_count`. This is the one place the comparison can be made safely — the Working-Set
Service already holds the filtered result under its own authority, and the unfiltered count adds
no channel beyond a bare integer that cannot itself leak which nodes are hidden. See
`03_CONDUIT_MIDDLEWARE.md` §4 for the read-time projection this feeds into, and §3.2 for
`filtered_count`'s place in the delta protocol.

### 8.3 Saved patterns

A `PatternQuery` (§8.1) becomes reusable once persisted:

```python
class SavedPattern(BaseModel):
    id: str
    pattern_id: str                # stable across saves; `id`/`version` identify one save
    version: int
    name: str
    owner_id: str
    created_at: datetime
    definition: PatternQuery
```

`pattern_id` is stable across a pattern's own edit history; `id` and `version` identify one
specific saved revision, so "run the pattern I saved" and "run exactly what version 3 said" are
both addressable. Deliberately carries `owner_id` and nothing shaped like `Handling.owning_unit`
or a share target — a saved pattern is readable only by its own owner until pattern sharing is
built; there is no broader-audience field to widen by accident because none exists yet. §11 covers
the watch this can be turned into.

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

**`properties.site_cell` — an incident geocoded into a site-grid cell (owner rulings R9, R10).**
The grid route calls `AnalyticsPort.geocode_events` at draw time, and each event
whose point a cell's polygon covers carries `site_cell` = the cell `Location`'s node id. For a
`PRESENT_AT` incident, the graph also gains a `PRESENT_AT` edge from the incident's subject to
that cell, carrying the incident's own handling. No ontology change: `PRESENT_AT` already runs
`Person|Device|Vehicle → Location`, and event `properties` are undeclared by design.
`08_ACCEPTANCE_SCENARIOS.md`'s A1 note has the full contract.

**`GeometryRecord`** — the analytics store's geometry reference partition, §7.1's
`geometry_ref`/`grid_ref` Knowledge Adapters produce the reference a `Location` node points at:

**Owner ruling R9, 28 September 2026 — a site-grid cell is a `POLYGON` here**, not the `POINT` at
its centroid that the grid route writes today. The cell keeps its `Location` identity, its
`geometry_ref` moves to the polygon, and the centroid becomes a derived value. Point-in-cell
containment is one `AnalyticsPort` method (DuckDB adapter, held to by the conformance suite).
`08_ACCEPTANCE_SCENARIOS.md`'s A1 note has the full ruling.

```python
class GeometryKind(StrEnum):
    POINT = "point"
    POLYGON = "polygon"              # a jurisdiction/boundary with no single point

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
`geometry_wkb`) are both shipped.

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

`packages/schemas/compute.py` is the source of truth, ahead of any adapter (standing rule 1).
Graph algorithms: centrality, community detection, the Clique Metric, temporal
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
(the metrics panel) owes the equivalent test the moment it exists — named here so
it is not assumed to happen automatically once the route is built.

**`temporal_motifs` is real as a type, not as a claimed capability.** `MotifRequest`/`MotifMatch`
exist because `_pending_port_placeholders.py`'s retirement needed real content for every one of
`ComputePort`'s five names, not because any commitment has claimed the convoy/relay/burst
algorithms themselves — only "Degree, betweenness, eigenvector, clustering coefficient, Louvain,
Clique Metric" were ever committed to. Recorded as a known gap from the outset, not discovered
only at the exit gate.

## 11. Watches: hotlists, monitors and alerts

A hotlist watches a bare identifier; a monitor watches a saved pattern (§8.3); both produce
alerts when new data matches.

```python
WatchStatus = Literal["active", "stopped"]

class Hotlist(BaseModel):
    id: str
    identifier: str                # a normalised value string — the same shape
                                    # Endpoint's own identifiers use, not a node id
    owner_id: str
    review_date: date
    status: WatchStatus = "active"
    created_at: datetime

class Monitor(BaseModel):
    id: str
    pattern_id: str                 # references a SavedPattern; never copies its definition
    owner_id: str
    status: WatchStatus = "active"
    created_at: datetime
```

A `Hotlist` is deliberately bare: an identifier, an owner, a review date, no handling ceiling — an
analyst can hotlist a bare phone number read off a warrant before it resolves to anything they can
see. A `Monitor` references a `SavedPattern` by `pattern_id` and never copies its own definition,
so an edited-then-resaved pattern is evaluated as it now reads, not as it read when the monitor was
turned on; its query is resolved fresh against the owner's own access on every evaluation, never
cached. `owner_id` on `Monitor` is redundant with the referenced `SavedPattern.owner_id` (a monitor
cannot be turned on for a pattern its own creator does not own) but stored directly so a monitor
row is self-describing without a join for the common "list my own monitors" case.

**`status` surfaces a stopped watch, rather than a silent skip with no visible state change.** Both
row types stop being evaluated once their owner becomes unresolvable (the same failure mode); a
stopped watch is shown as stopped in the monitor list or the alert inbox, not simply absent from
future results with nothing explaining why.

```python
class AlertMode(StrEnum):
    FULL = "full"           # referents re-checked against the reading principal at read time
    NOTIFY_STUB = "notify_stub"   # the triggering referent was outside the recipient's access
                                   # at write time; carries no referent of any kind

class Alert(BaseModel):
    id: str
    rule_id: str                    # the Hotlist or Monitor that fired
    owner_id: str
    mode: AlertMode
    referent_node_ids: list[NodeId] = []
    investigation_id: str | None = None
    created_at: datetime
```

An `Alert` stores references to evidence, never copies — access is re-checked at read time against
`referent_node_ids`, not trusted from whatever was true when the row was written. A `NOTIFY_STUB`
row never carries a referent at all: the triggering match was outside the recipient's own access
when it fired, so nothing about it — not even the identifier that matched — is disclosed to a
principal who could not see it anyway. `investigation_id` is a best-effort audit-shaped hint, not
an access-control scope, threaded from whichever producer route was investigation-scoped at the
point the triggering write happened; `None` for a producer with no single investigation in scope
(a corpus-wide resolution trigger, say). Jumping from an alert into an investigation branches a new
one from this field via the same mechanism an ordinary investigation branch already uses; a `None`
here means the jump starts an unbranched investigation rather than one carrying that link.
