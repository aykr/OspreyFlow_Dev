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

### 3.1 Investigations

```
POST   /v1/investigations                      create
GET    /v1/investigations/{id}                 metadata, not the working set
POST   /v1/investigations/{id}/branch          fork the working set into a new investigation
GET    /v1/investigations/{id}/history         addressable step history
POST   /v1/investigations/{id}/history/{step}  restore to a step
```

### 3.2 Working set

```
WS     /v1/investigations/{id}/stream          bidirectional delta channel
POST   /v1/investigations/{id}/seed            seed from a search result or saved subgraph
POST   /v1/investigations/{id}/expand          apply an expansion
POST   /v1/investigations/{id}/expand/preview  cardinality only, no mutation
DELETE /v1/investigations/{id}/nodes           remove from the working set (not from the Vault)
```

The delta protocol, client-bound:

```json
{"seq": 412, "op": "add",     "nodes": [...], "edges": [...]}
{"seq": 413, "op": "update",  "nodes": [{"id": "...", "properties": {...}}]}
{"seq": 414, "op": "remove",  "node_ids": ["..."]}
{"seq": 415, "op": "reproject", "reason": "resolution_threshold",
 "merged": 3, "split": 1, "affected": 47}
{"seq": 416, "op": "notice",  "level": "warning",
 "message": "6 nodes withheld by handling policy", "count": 6}
```

Sequence numbers are monotonic per investigation. A client that misses a sequence reconnects and
requests a full snapshot rather than attempting to patch — silent divergence between the
server's picture and the analyst's is the failure this protocol exists to prevent.

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
POST   /v1/compute/{metric}             submit a metric job over a working set
GET    /v1/jobs/{id}/events             SSE progress stream
```

### 3.4 Ingest, extraction, assessment

```
POST   /v1/ingest/upload                multipart; returns a document id and a job id
POST   /v1/ingest/connector/{name}/run  trigger a configured connector
GET    /v1/documents/{id}               metadata, provenance, extraction results
GET    /v1/documents/{id}/content       original bytes, access-checked, audited
POST   /v1/documents/{id}/reextract     re-run with a different model version

POST   /v1/investigations/{id}/judgements
POST   /v1/investigations/{id}/gaps
POST   /v1/investigations/{id}/assumptions
POST   /v1/investigations/{id}/export    runs the handling gate; may return 409 with blockers
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
what the client last acknowledged. Projection is pure and cheap; it runs per request.

**Why server-side rather than browser-only.** Three reasons that each independently decide it.
An investigation must survive a tab crash. A branch operation must be atomic. And the resolution
threshold must re-project against the full source-fidelity set, which the browser does not hold
— the browser holds the projection.

## 5. Pipelines

### 5.1 Ingest

```
upload/connector → identify → normalise → deduplicate → stage → extract? → resolve → load → index
```

- **identify** — MIME sniffing, not extension trust. Container formats unpacked one level.
- **normalise** — the Knowledge Adapters from `01_DOMAIN_MODEL.md` §7. Originals retained.
- **deduplicate** — content hash per record type; the CDR rule is specified in the domain model.
- **stage** — everything lands in Parquet in object storage before it touches the graph. This is
  what makes re-extraction, re-resolution and schema migration possible without re-uploading.
  Skipping the staging layer is the most expensive shortcut available in this design.
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
spatial predicates are cheap, and the graph holds the `Location` node with a reference to it.
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
Mantis mark, the investigation reference, the export timestamp, the resolution threshold in
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
