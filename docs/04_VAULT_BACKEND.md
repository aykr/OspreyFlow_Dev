# 04 — The Vault (Backend)

Every component here sits behind a port from `00_ARCHITECTURE.md` §2 and is supported only if
its adapter passes the port's conformance suite. That suite is the contract. Read §6 before
choosing anything.

## 1. Graph store

### 1.1 The choice

| | ArcadeDB | JanusGraph | HugeGraph |
| --- | --- | --- | --- |
| Licence | Apache-2.0 | Apache-2.0 | Apache-2.0 (ASF top-level) |
| Deployment | Single binary, or embedded in a JVM | Server + storage backend + index backend | Server + RocksDB, or PD/HStore cluster |
| Query languages | SQL, openCypher, Gremlin, GraphQL | Gremlin | Gremlin, openCypher, REST |
| Scale ceiling | Single node to small cluster with Raft | Billions of edges across a cluster | Very large, with a separate Go OLAP engine |
| Operational weight | Very low | High — Cassandra/ScyllaDB plus OpenSearch | Medium to high |
| Community size | Smallest of the three | Largest | Large, much of it Chinese-language |
| Role here | **Default for `local-lite`** | **Default for `cluster`** | Candidate third adapter |

**`local-lite` uses ArcadeDB.** One container, no storage backend to operate, and it starts in
seconds on a laptop. The transportability requirement is a laptop requirement first.

**`cluster` uses JanusGraph** over ScyllaDB (or Cassandra) with **OpenSearch** as the index
backend. Note the substitution: the Gemini specification names Elasticsearch, which is under
SSPL/Elastic Licence and fails the open-source constraint that the same document sets. This is
the same trap it correctly identifies for FalkorDB.

JanusGraph's official release cadence is slow — 1.1.0 is the current tagged release and 1.2.0
has been in per-commit builds for some time. Pin a specific per-commit build, record the hash in
`deploy/versions.lock`, and treat a JanusGraph upgrade as a deliberate quarterly exercise with
the conformance suite as the gate. Do not track the per-commit stream continuously.

**HugeGraph is worth a third adapter** once the first two are stable, for one specific reason:
its Vermeer OLAP engine gives server-side PageRank, weakly connected components, BFS, local
clustering coefficient and label propagation over very large graphs via a REST call. That is a
ready-made `ComputePort` implementation at a scale where the alternative is standing up Spark.

### 1.2 Query dialects

Adapters declare which query languages they can render, and the Conduit picks a builder backend
from what the configured adapter advertises:

| Adapter | Dialects declared | Note |
| --- | --- | --- |
| `arcadedb` | `gremlin`, `opencypher` | Native Cypher engine; Gremlin via the TinkerPop bridge |
| `janusgraph` | `gremlin` | TinkerPop-native |
| `hugegraph` | `gremlin`, `opencypher` | Separate Cypher engine |

Gremlin is the v1 default because it is the only dialect all three speak. openCypher is the
second backend to write when one is worth writing, and it is the on-ramp to GQL — since GQL
published as ISO/IEC 39075:2024, openCypher's stated purpose has been to evolve toward GQL
conformance by absorbing GQL features. No engine in this candidate set declares GQL conformance
today; when one does, it declares `gql` in its `dialects` and the builders gain a third
`render()`. See ADR-003's GQL amendment.

The builders describe intent — expand, path, match, aggregate — not syntax, which is what makes
a second dialect a `render()` method rather than a project. The `GraphPort` conformance suite is
parameterised by dialect: a new backend proves identical results on the same fixtures before it
is supported.

### 1.3 Conformance caveat that will bite

Gremlin support differs in depth between these engines. ArcadeDB implements the TinkerPop bridge
over its own native engine; JanusGraph is TinkerPop-native. Traversal steps that work on one may
be unsupported, slow, or subtly different on the other — `repeat().until()` semantics, ordering
guarantees without an explicit `order()`, and index selection are the usual offenders.

The mitigation is to keep the surface small. The Conduit builds Gremlin from a bounded set of
composable builders — expand, path, match, aggregate — not free-form traversal strings. The
conformance suite runs every builder against every adapter and asserts identical results on a
fixture graph. Adding a builder means adding a conformance case first.

### 1.4 Schema and indexing

Both engines need explicit indexes; neither will be usable without them.

- Composite index on every `identifiers` field declared in the ontology.
- Composite index on `(type, handling.classification)` — the access filter runs on every read
  and an unindexed filter there costs more than the query.
- Mixed/full-text index on name-like properties, served by OpenSearch on the cluster profile.
- Vertex-centric index on `(edge_type, interval.from)` for every temporal edge type. Without
  this, timeline-filtered expansion on a high-degree node scans the whole adjacency list, which
  is the most common performance cliff in this class of system.

Schema is generated from the ontology by `packages/ontology`, applied by a migration runner,
and versioned. An ontology change that requires reindexing must say so before it runs, not
during.

## 2. Columnar analytics

| | DuckDB | ClickHouse |
| --- | --- | --- |
| Deployment | In-process, no server | Distributed server |
| Profile | `local-lite` | `cluster` |
| Ceiling | Comfortable to ~100 GB single node | Petabyte scale, high concurrency |
| Ops cost | None | Real |

Same SQL surface in both adapters, kept deliberately narrow: time bucketing, geospatial binning,
grouped counts, windowed baselines. Where dialects diverge, the adapter absorbs it; the
`AnalyticsPort` contract does not change.

**Storage is Parquet in object storage, in both profiles.** DuckDB reads it directly; ClickHouse
ingests from it. This is the second reason the staging layer earns its place: migrating from
laptop to cluster is a ClickHouse ingest against files that already exist, not an export from
one engine and an import into another.

Partition by `(investigation_scope, month)`. Cluster within a partition by
`(edge_id, timestamp)` so that the timeline's most common query — events for a set of edges in a
window — reads a small number of contiguous ranges.

`DuckPGQ` (the SQL/PGQ community extension) is worth watching for the laptop profile, since it
would allow pattern matching over the event tables without a graph round-trip. It is a community
extension under active development — do not build on it in v1, and revisit at the point where
`GraphPort` gains a SQL/PGQ adapter.

## 3. Graph compute

Three implementations, selected by working-set size, as set out in `00_ARCHITECTURE.md` §2.3.

**graphology + graphology-metrics** in a browser Web Worker, up to 20k nodes. This tier exists
so the metric panel updates as the analyst moves the timeline brush. A server round-trip on
every brush change would make the interaction unusable no matter how fast the server is.

**rustworkx** (Apache-2.0) in the Conduit's compute worker, up to roughly 2M nodes. Rust core,
Python API, and considerably faster than NetworkX on exactly the algorithms required here.
NetworkX remains useful as a reference implementation for the conformance fixtures.

**GraphFrames on Spark**, or HugeGraph Vermeer, above that. Batch only; results are written back
as node properties with a computation timestamp and the algorithm version.

All three must agree. The conformance suite runs a fixture graph of about 5,000 nodes through
every tier and asserts identical output for degree, betweenness, clustering coefficient, Leiden
communities and the Clique Metric, within a stated numerical tolerance for the iterative
algorithms. A metric that changes value when the working set crosses a size boundary destroys
analyst trust the first time someone notices, and they will notice.

## 4. Model serving

```
Conduit ──► LiteLLM proxy ──┬──► Ollama            (local-lite: LLM + VLM, quantised)
                            ├──► vLLM              (cluster: LLM + VLM, GPU)
                            ├──► faster-whisper    (ASR, both profiles)
                            └──► text-embeddings   (embeddings, both profiles)
```

LiteLLM (MIT core, self-hostable, runs air-gapped) presents one OpenAI-compatible endpoint.
Everything above it speaks one protocol. Routing, fallback, per-team budgets and rate limits are
`litellm-config.yaml`.

```yaml
model_list:
  - model_name: extract-text          # logical name used in code — never a vendor name
    litellm_params:
      model: ollama/qwen2.5:14b-instruct
      api_base: http://ollama:11434
  - model_name: extract-vision
    litellm_params:
      model: ollama/qwen2-vl:7b
      api_base: http://ollama:11434
  - model_name: embed
    litellm_params:
      model: ollama/bge-m3
      api_base: http://ollama:11434

router_settings:
  fallbacks: [{extract-text: [extract-text-large]}]
  num_retries: 2
  timeout: 120
```

**Code never names a model.** It names a role: `extract-text`, `extract-vision`, `transcribe`,
`embed`, `summarise`. Changing the model behind a role is a YAML edit and a container restart,
which is the flexibility requirement satisfied concretely rather than aspirationally.

**Egress is default-denied.** The model gateway is the only component permitted to reach a
network outside the deployment, and in the default configuration it is not permitted either. A
deployment that wants a hosted model enables it deliberately, per role, with the handling codes
that may be sent to it declared explicitly. An extraction request carrying `OFFICIAL-SENSITIVE`
material must not be able to reach a hosted endpoint by a routing accident.

## 5. Supporting services

| Service | Choice | Licence | Role |
| --- | --- | --- | --- |
| Object store | MinIO | AGPL-3.0, run unmodified as a separate service | Original documents, staged Parquet, tiles |
| Search index | OpenSearch | Apache-2.0 | Full text, embeddings, JanusGraph mixed index |
| Cache and queue | Valkey | BSD-3 | Working set, session, cache, local queue |
| Cluster queue | NATS JetStream | Apache-2.0 | Job distribution on the cluster profile |
| Identity | Keycloak | Apache-2.0 | OIDC, roles, clearance claims |
| Relational store | PostgreSQL | PostgreSQL Licence | Investigations, judgements, audit, users, jobs |
| Tiles | PMTiles / TileServer GL | BSD-3 / MIT | Offline basemaps |
| Observability | OpenTelemetry + Prometheus + Loki | Apache-2.0 | |

MinIO's AGPL requires a decision to be made deliberately rather than by default: running it
unmodified as a separate containerised service does not impose source obligations on
MantisNexus, but modifying it would. If that is judged too close to the line for the deployment,
SeaweedFS (Apache-2.0) is the substitute and the adapter surface is small — everything goes
through an S3-compatible client either way.

PostgreSQL rather than the graph store for investigations, judgements and audit. Relational data
belongs in a relational store, the audit stream needs a different durability and retention
story than the graph, and keeping the graph store free of platform metadata is what keeps it
swappable.

## 6. The conformance suites

`tests/conformance/` is the enforcement mechanism for the entire swap-boundary claim. Without
it, "swappable" is a slide, not a property.

Each port has a suite that runs against every adapter in CI, on the same fixture dataset.

**GraphPort suite** — write and read back every ontology type; expand at depth 1–4; k-shortest
paths; pattern match; temporal filtering on a vertex-centric index; access filter with three
principals of differing clearance; assert that an unauthorised principal cannot detect a
filtered node's existence via path length, degree count or aggregate bucket; transaction
rollback; schema migration up and down.

**AnalyticsPort suite** — identical histogram, geobin and baseline results across adapters,
including edge cases: empty window, single-event window, window crossing a DST boundary, null
coordinates.

**ComputePort suite** — identical metric values across all three tiers on the 5,000-node
fixture, within tolerance.

**ModelPort suite** — schema-constrained output validates against the ontology schema; a
deliberately malformed model response is rejected rather than partially parsed; the golden
extraction set meets the recorded precision and recall floor.

A component without a green suite is not a supported component, whatever its merits. Say so in
the documentation, because the failure mode otherwise is someone swapping in an untested adapter
in production and discovering the differences during an investigation.

## 7. Capacity guidance

Starting points, to be replaced by measurements from your own data.

| Profile | Graph | Events | Concurrent analysts | Shape |
| --- | --- | --- | --- | --- |
| `local-lite` | ≤ 5M nodes / 20M edges | ≤ 100M rows | 1–3 | One laptop, 16 GB RAM, 8 cores. Extraction on CPU is slow but works |
| `small` | ≤ 50M / 200M | ≤ 2B | ≤ 25 | 3 nodes, 64 GB each, one GPU |
| `cluster` | 500M+ / 2B+ | 50B+ | 250+ | Scylla 5+, JanusGraph 3+, ClickHouse 3+, GPU pool, Conduit autoscaled |

The dimension that actually breaks first is rarely the one people plan for. It is **working-set
projection latency under a high resolution-threshold change** — an analyst dragging τ across a
densely linked set of a million `SAME_AS` edges. Load-test that specific interaction before go-live.
