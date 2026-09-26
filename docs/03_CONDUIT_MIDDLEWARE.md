# 03 — The Conduit (Middleware)

## 1. What the Conduit is and is not

It is a stateless orchestration layer: FastAPI on Python 3.12, uvicorn workers, async
throughout. It translates analyst intent into port calls, enforces access control, and manages
the working set.

It is **not** a place where data lives. Any Conduit instance can serve any request for any
session; kill one mid-investigation and the analyst notices nothing. Session and working-set
state live in Valkey; durable state lives in the Vault. This is the property that lets the
Conduit scale horizontally to a large concurrent user base independently of the Vault, which is
the whole point of the tier.

It is also **not** a pass-through to Gremlin. The Conduit owns query construction. An analyst
never submits a traversal and the Glass never contains one. That is both an access-control
boundary (a hand-written traversal cannot be filtered reliably) and the reason a future move
from Gremlin to SQL/PGQ is an adapter change.

## 2. Service decomposition

One deployable API process plus three worker pools. Workers share the codebase and the ports;
they differ in what queue they consume.

| Service | Scales on | Consumes |
| --- | --- | --- |
| `api` | Concurrent analysts | HTTP / WebSocket |
| `worker-ingest` | Data volume | `ingest` queue |
| `worker-extract` | Unstructured volume, GPU availability | `extract` queue |
| `worker-compute` | Working-set size and metric complexity | `compute` queue |

Queue is Valkey Streams in `local-lite`, NATS JetStream (Apache-2.0) in `cluster`. Both behind
a `QueuePort` so the swap is a config value. Job state, progress and failure are first-class:
every job is addressable, has a progress stream, and reports partial results where partial
results are meaningful.

## 3. API surface

REST for request/response, Server-Sent Events for job progress, WebSocket for working-set
deltas. Not GraphQL: the response shapes here are few and large, the clients are one, and the
cost of a flexible query layer on top of an access-filtered graph is not worth paying.

### 3.0 Liveness

```
GET    /healthz                                is this process up
```

**Owner's decision, 24 September 2026.** One unauthenticated route, outside `/v1` because it is
not part of the API surface a client uses — it exists so an orchestrator can tell a started process
from a healthy one. `docker compose up --wait` has nothing to wait on without it, which is what
made the scripted deploy unable to reach its own exit criterion.

**Its body is fixed and says nothing else.** `{"status":"ok"}`, byte for byte, always. No version,
no build, no uptime, no component status, no counts. The reasoning is this document's own §6: an
unauthenticated endpoint that reports which stores are reachable tells an unauthenticated caller
about the deployment's internal topology, and one that reports counts is a count leak with a
friendly name. **It touches no store**, so it stays true when every store is down, which is exactly
when an orchestrator most needs to distinguish "the process is up but its dependencies are not"
from "the process is gone".

**Readiness stays authenticated and is a separate question.** "Can this process serve a request"
and "is this deployment ready to be used" are different, and only the second needs to talk to the
stores it depends on — which is why only the second can be allowed to describe them.

**The test that holds this, per the standing access-control rule:** the anonymous response and the
authenticated response are compared byte for byte and must be identical. A liveness route that
quietly said more to an authenticated caller would be a route with two behaviours, and the
unauthenticated one is the one an attacker gets.

### 3.1 Investigations

```
POST   /v1/investigations                      create
GET    /v1/investigations/{id}                 metadata, not the working set
POST   /v1/investigations/{id}/branch          fork the working set into a new investigation
GET    /v1/investigations/{id}/history         addressable step history
POST   /v1/investigations/{id}/history/{step}  restore to a step
```

**Authorization, added in Phase 3.** Every route above an investigation id checks the calling
`Principal.org_unit` against that investigation's own `owning_unit` — set once at creation (or
branch) from the acting principal's own unit, the same shape as `Handling.owning_unit`
(`01_DOMAIN_MODEL.md` §2.2), not a new concept. This is deliberately *not* `clearance`-gated: a
shared, unit-wide investigation with analysts at different clearances is the ordinary case, not
an edge case, and clearance still gates individual node/edge visibility separately (§4's read-time
handling filter). A principal in the wrong unit gets the same 404 an unknown investigation id
would — never a 403 — extending the existence-leak discipline `00_ARCHITECTURE.md` §5 already
requires at node/edge level up to the investigation id itself.

### 3.2 Working set

```
WS     /v1/investigations/{id}/stream          bidirectional delta channel
POST   /v1/ws-ticket                           short-lived single-use ticket for the stream above
POST   /v1/investigations/{id}/seed            seed from a search result or saved subgraph
POST   /v1/investigations/{id}/expand          apply an expansion
POST   /v1/investigations/{id}/expand/preview  cardinality only, no mutation
DELETE /v1/investigations/{id}/nodes           remove from the working set (not from the Vault)
```

**`/v1/ws-ticket`, ADR-050 objection 8.** A browser's native `WebSocket` cannot set an
`Authorization` header, so the stream above is opened with `?ticket=<value>` rather than a bearer
token in the URL. This route is the only way to obtain one: authenticated the ordinary way, it
mints a random, single-use value — bound to the calling principal, redeemable exactly once, and
expiring in 30 seconds — and returns it. A bearer token placed in the stream's own URL instead of a
ticket is refused outright, not merely accepted as a fallback.

The delta protocol, client-bound:

```json
{"seq": 412, "op": "add",     "nodes": [...], "edges": [...]}
{"seq": 413, "op": "update",  "nodes": [{"id": "...", "properties": {...}}]}
{"seq": 414, "op": "remove",  "node_ids": ["..."]}
{"seq": 415, "op": "reproject", "reason": "resolution_threshold",
 "merged": 3, "split": 1, "affected": 47}
{"seq": 416, "op": "notice",  "level": "warning",
 "message": "6 nodes withheld by handling policy", "count": 6}
{"seq": 417, "op": "snapshot", "nodes": [...], "edges": [...], "filtered_count": 6}
```

Sequence numbers are monotonic per investigation. A client that misses a sequence reconnects and
requests a full snapshot rather than attempting to patch — silent divergence between the
server's picture and the analyst's is the failure this protocol exists to prevent. `snapshot` is
that full-state response, added in Phase 3: the five ops above are this section's own
illustrative set, and a full-snapshot reconnect path is required without a shape given for it
before Phase 3 filled it in — the same way `GraphPort` grew past its own illustrative sketch
(`00_ARCHITECTURE.md` §2.1). Its `filtered_count` is the same figure `expand`'s response and the
status bar both carry, computed fresh for whichever principal is reconnecting (§4).

The `notice` operation is how withheld items reach the status bar. It carries a count and never
carries the withheld content, not even its identifiers.

### 3.3 Query and analytics

```
POST   /v1/search                       federated search across graph, documents, index
POST   /v1/paths                        k-shortest paths between two entities
POST   /v1/patterns/preview             cardinality estimate for a visual query
POST   /v1/patterns/run                 execute; large results return a job id
POST   /v1/analytics/histogram          cross-filter histogram set
POST   /v1/analytics/geobins            server-side spatial binning
POST   /v1/analytics/sightings          the "snail trail" — device/location sightings over time (Phase 8 Stage 4f, B18)
POST   /v1/compute/{metric}             submit a metric job over a working set
GET    /v1/jobs/{id}/events             SSE progress stream
```

### 3.4 Ingest, extraction, assessment

```
POST   /v1/ingest/upload                multipart; returns a document id and a job id
POST   /v1/ingest/connector/{name}/run  trigger a configured connector
GET    /v1/handling-scheme              the active deployment's classification/handling-code vocabulary
GET    /v1/yardstick                    the active deployment's probability yardstick (01_DOMAIN_MODEL.md §5)
GET    /v1/documents/{id}               metadata, provenance, extraction results
GET    /v1/documents/{id}/content       original bytes, access-checked, audited
POST   /v1/documents/{id}/reextract     re-run with a different model version

POST   /v1/investigations/{id}/judgements
GET    /v1/investigations/{id}/judgements   list visible judgements — ADR-046's own hide-in-full rule applies
POST   /v1/investigations/{id}/gaps
GET    /v1/investigations/{id}/gaps         list
POST   /v1/investigations/{id}/assumptions
GET    /v1/investigations/{id}/assumptions  list
POST   /v1/investigations/{id}/export    runs the handling gate; may return 409 with blockers
GET    /v1/exports                       the compliance-facing export ledger (ADR-047's own Gap 2) — role-gated, not per-investigation
```

### 3.5 Resolution

```
GET    /v1/resolution/threshold          current session τ
PUT    /v1/resolution/threshold          set τ; triggers a reproject delta
POST   /v1/resolution/link               analyst-asserted SAME_AS
POST   /v1/resolution/split              analyst-asserted NOT_SAME_AS
GET    /v1/resolution/explain/{cluster}  the comparison vector and score that produced a cluster
```

`explain` is required, not a nicety. An analyst who cannot see why two records were treated as
one person will either trust the merge blindly or distrust the whole system. Return the
per-comparison match weights, not just the total.

### 3.6 Dossier

```
GET    /v1/investigations/{id}/dossier/documents/{document_id}   a message, with its entity spans
```

Phase 6a Stage 4 (B6): the Dossier's own read, backing `apps/workspace/src/dossier/` — "the
shared endpoint's messages... rendered with the entity spans highlighted in place." A document's
raw text (persisted once, at extraction time, keyed by `document_id` and scoped to the extracting
principal's own `owning_unit` — the same `WHERE owning_unit = $2` shape `get_authorized` already
uses for a candidate, so an unauthorised principal gets the same 404 whether the document never
existed or simply isn't theirs) plus the subset of its **accepted** extraction candidates whose
minted node the requesting principal can currently see:

```json
{
  "document_id": "doc-412",
  "text": "Dana called +441621926368 about the shipment.",
  "spans": [
    {"start": 0, "end": 4, "node_id": "n1", "entity_type": "Person", "provenance_state": "asserted"}
  ]
}
```

A span naming a node the principal cannot see is **omitted from the array entirely, never
returned redacted** — the same rule §3.5's `explain` response already follows for a pairwise
comparison naming an invisible node (`visiblePairs`). A redacted span would still assert "an
entity was extracted here," which is exactly the existence signal access control exists to deny;
omission is the only response shape that doesn't. A **pending** (not yet accepted) or **rejected**
candidate never produces a span at all — that is the still-separate, still-unbuilt review-queue
screen's own concern (`09_INGEST_STUDIO.md` §7), not post-hoc inspection of an already-resolved
message, and a pending candidate has no minted node and no `Handling` to check visibility against
in the first place.

### 3.7 Geospatial admin actions

```
POST   /v1/admin/geospatial/build-basemap   tier-1 pipeline: download, planetiler, gazetteer load — streamed
POST   /v1/admin/geospatial/verify          attribution and, for a tier-4 provider, a live CRS/zoom probe
```

Round 09: the two Geospatial-screen actions `harness/geospatial.py`'s own docstring found
structurally unreachable from inside the setup harness image (`build_local_basemap` needs a live
`GraphPort` transaction; both it and `verify_map` import `services`/`adapters` modules the harness
image deliberately does not carry). Admin-role-gated (`require_admin_role`, `osprey-admin`) — the
one process that already has every module both actions need. `build-basemap` streams its own real
progress the same way Launch does (`text/event-stream`, one `{"line": ...}` per step, `event:
complete` last); `verify` is fast enough to answer as a plain JSON `{"passed": ..., "issues": [...]}`.
Not yet called from any UI — `Stage 2 §7`'s own post-launch console has no screen built yet;
`07_BUILD_PLAN.md`'s Stage 2 §6 part B entry has the full account.

## 4. The Working-Set Service

The most important component in the Conduit.

**Storage.** One Valkey hash per investigation holding the node and edge set in a compact binary
encoding, plus a capped stream of deltas for reconnect. TTL of 24 hours on idle, with explicit
save promoting the set to durable storage in the Vault.

**Caps.** 50,000 nodes, 250,000 edges. On breach the service does not truncate; it returns a
`limit_exceeded` response naming the three options the Glass offers the analyst (branch, filter,
promote to batch). Encode this as a typed error, not a generic 400, so the client can render the
right dialogue.

**Projection.** The stored set is source-fidelity. The projection applied on read is: resolution
collapse at the session's τ, handling filter for the principal, then delta computation against
what the client last acknowledged. Projection is pure and cheap; it runs per request. Resolution
collapse lands in Phase 6 with Splink; the handling filter and delta computation are real from
Phase 3.

**Why the stored set can hold more than one principal's own view, and why the filter must
therefore run on every read, not once at write time.** An investigation is not single-principal
for its whole life — §3.1's `owning_unit` authorization is unit-wide, not creator-only, so a
shared team investigation, or one principal's branch of another's, means a later reader's own
`Principal` may be different, and less privileged, than whoever's `expand`/`seed` call originally
populated a given node. `GraphPort`'s own access filtering at the point of fetch is still the only
thing that ever decides what gets *written* to the store — nothing re-derives or second-guesses
that. What the handling filter re-applies on every read (`ontology.handling.principal_may_view`,
the same predicate the adapter's compiled Gremlin is built from) is a *second*, independent check
for whoever is *reading* the store back: a node one principal was entitled to fetch is not
disclosed to a different principal who is not. This applies uniformly to the reconnect snapshot,
replayed missed deltas, a live WebSocket push, and a `branch` copy — you cannot fork what you
cannot see, either.

**Why server-side rather than browser-only.** Three reasons that each independently decide it.
An investigation must survive a tab crash. A branch operation must be atomic. And the resolution
threshold must re-project against the full source-fidelity set, which the browser does not hold
— the browser holds the projection.

## 5. Pipelines

### 5.1 Ingest

```
upload/connector → identify → stage(raw) → normalise → deduplicate → stage(normalised)
                                                     → extract? → resolve → load → index
```

- **identify** — MIME sniffing, not extension trust. Container formats unpacked one level.
- **normalise** — the Knowledge Adapters from `01_DOMAIN_MODEL.md` §7. Originals retained.
- **deduplicate** — content hash per record type; the CDR rule is specified in the domain model.
- **stage(raw)** — the source rows land in Parquet *before* any transform touches them, every
  field as it appeared, typed as text. Immutable, never rewritten.
- **stage(normalised)** — the post-transform rows land in a second Parquet dataset, partitioned
  the same way and carrying the raw row's identifier.

**Two staging datasets, not one, and the order matters.** Staging exists so that re-extraction,
re-resolution and schema migration are possible without re-uploading — and only the raw dataset
delivers that. If normalisation runs before the only stage step, a normaliser bug found in month
six is correctable only for fields the recipe happened to bind twice, and an ontology version
that wants a property the original recipe never captured has nowhere to read it from. Both cases
end in a re-upload, which is the outcome staging is meant to prevent.

Raw staging is cheap — text columns, compressed — and it is the layer that makes every other
recovery path work. Skipping it is the most expensive shortcut available in this design.
- **extract** — only for unstructured material; see §5.2.
- **resolve** — Splink, writing `SAME_AS` edges; see §5.3.
- **load** — batched writes through `GraphPort` and `AnalyticsPort` in one logical transaction
  per document.
- **index** — full text and embeddings into OpenSearch.

**Geospatial reference data uses the same pipeline with two differences.** Gazetteers, boundary
files and OSM extracts enter through `services/ingest/connectors/geo/` (GeoPackage, Shapefile,
GeoJSON, CSV-with-coordinates, OSM PBF, and WFS). They skip extraction entirely, since they are
already structured, and they load into a **reference partition** that is versioned as a whole
rather than per-document — a gazetteer refresh replaces a version, it does not merge into the
previous one, and investigations record which gazetteer version was in force.

Geometry is stored once, not twice: the geometry column lives in the analytics store where
spatial predicates are cheap, and the graph holds the `Location` node with a `geometry_ref`
pointing at that row — never `lon`, `lat` or a source easting and northing as node properties.
A `Location` with no single point, such as a jurisdiction or an administrative boundary, can carry
a polygon-shaped `geometry_ref` instead of a point one (`schemas/analytics.py`'s `GeometryRecord.
kind`, Phase 5's known-gaps closure) — or none at all, so coordinates can never be a required
property on the type.
Putting geometry in the graph store would make spatial filtering a traversal, which is the wrong
shape of query and constrains engine choice for no gain.

The **geocoder is a local service** over that reference partition. An address or place name
extracted from a document resolves against the ingested gazetteer inside the deployment. No
hosted geocoder is called, ever: an air-gapped deployment could not, and sending intelligence
material to one would breach the handling model regardless of connectivity. A gazetteer match is
written as `inferred` with its match score, confirmable by an analyst like any other derived
link.

### 5.2 Extraction

Four modalities behind one `ModelPort`:

| Input | Model class | Default local | Output |
| --- | --- | --- | --- |
| Text | Instruction-tuned LLM | Qwen/Llama-class 7–14B via Ollama | Typed nodes and edges |
| Audio | ASR | faster-whisper | Transcript with word timings and speaker turns |
| Image | Vision-language | Qwen2-VL / Llama Vision | Description, OCR, detected objects |
| Document | Layout + text | Text path after layout parse | As text, plus table structure |

**Structured output is enforced, not requested.** The extraction call passes a JSON Schema
generated from the active ontology and uses constrained decoding — vLLM guided decoding on the
cluster profile, Ollama's format parameter locally. A model that cannot be constrained is not a
supported extraction model. Parsing free text for JSON and hoping is the single largest source
of silent data corruption in pipelines of this kind.

Each extracted element carries the model identifier and version, the character span or timestamp
it came from, and the model's reported confidence. All of it is `inferred` until confirmed.

**The golden set is a build artefact.** `tests/golden/` holds documents with hand-labelled
expected extractions. Changing a prompt or a model runs the set and reports precision and recall
per entity type against the previous version. A change that degrades recall on any type fails
the build unless explicitly accepted with a recorded reason. This is the evaluation harness the
Gemini specification asks for, and it needs to exist from the first extraction commit, not
later — retrofitting a golden set means hand-labelling against a corpus you have already come to
believe in.

**Extraction never writes directly to the graph.** It writes candidates to the staging layer.
Resolution and load are separate stages so that a bad extraction run is revertible.

### 5.3 Resolution

Splink, running on DuckDB locally and Spark on the cluster, configured from the ontology's
per-type `resolution` block. Output is `SAME_AS` edges with the match probability, the model
version and the full comparison vector. Nothing is merged in storage — see
`01_DOMAIN_MODEL.md` §4 for why this overrides the Gemini specification.

Deterministic identifiers bypass the probabilistic path. Two endpoints with the same normalised
E.164 are the same endpoint; do not spend a Fellegi–Sunter model on it.

Analyst decisions are permanent and beat the model: a `NOT_SAME_AS` edge is never overridden by
a later resolution run, and a later run that would have merged the pair records the conflict for
review rather than acting on it.

## 6. Access control and audit

**Principal resolution.** OIDC via Keycloak (Apache-2.0). The session token resolves to a
`Principal` carrying identity, unit, roles, clearance, and the handling codes the principal may
receive.

**Enforcement at the port.** The `Principal` is a required argument on every read path in
`GraphPort` and `AnalyticsPort`. Adapters inject the filter into the traversal or the `WHERE`
clause. Filtering in the Conduit after retrieval is forbidden — it leaks existence through
counts and timing, and it is the mistake this rule exists to prevent.

**Existence, not just content.** The conformance suite asserts that an unauthorised principal
cannot detect a filtered node's existence: not through a path length, not through a degree
count, not through a histogram bucket. Aggregate endpoints apply the filter before aggregation.

**Audit.** Append-only, to a stream the Conduit cannot rewrite. Every read, expansion, path
query, pattern run, document view and export records principal, timestamp, the resolved query,
result cardinality, and — where the action crosses a handling boundary — the justification the
analyst supplied. Audit write failure fails the request; an unaudited read in this domain is
worse than a refused one.

**Export gate.** `POST /export` evaluates every node and edge in the selection against the
handling scheme. A `consult_originator` item blocks the export and is named specifically.
Override requires a justification and an originator reference, both recorded. Exports carry the
Osprey mark, the investigation reference, the export timestamp, the resolution threshold in
force, and a manifest of withheld items by count.

## 7. Caching

Three layers, three different invalidation stories. Keep them separate or you will invalidate
the wrong one.

| Layer | Store | Key | Invalidation |
| --- | --- | --- | --- |
| Working set | Valkey hash | `ws:{investigation_id}` | Explicit, on mutation |
| Query result | Valkey string | hash of (query, principal_class, τ) | TTL 300s + on graph write to touched types |
| Analytics result | Valkey string | hash of (query, principal_class) | TTL 900s + on partition load |

`principal_class` rather than `principal_id`: cache by the set of handling codes the principal
may receive, not by the person. Otherwise the cache is useless at scale — and caching by person
while keying on query is how access-control leaks happen.

## 8. Failure behaviour

Stated explicitly because the default behaviours are all wrong for this domain.

- **A source is offline.** Return the partial result with an explicit notice naming how many
  sources contributed and how many did not. Never return a partial result silently.
- **A query times out.** Return the partial traversal with its depth, and a message naming the
  narrowing action. Never return an empty result for a timeout.
- **A model is unavailable.** Extraction jobs queue rather than fail. The document is ingested
  and searchable; extraction is marked pending and visible as such.
- **The graph store rejects a write.** The staged Parquet is intact; the job is retryable with
  no data loss. This is the property the staging layer buys.
- **The audit stream is unavailable.** Reject reads. This is the one case where the platform
  fails closed.
