// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
/**
 * The memory the stores are sized to, in GiB (as Docker reports it). Default: none — the stores keep their fixed sizes.
 */
export type MemoryGib = number | null;
/**
 * Overrides the graph store's heap (-Xmx), in GiB; at most 31.
 */
export type GraphHeapGib = number | null;
/**
 * Overrides OpenSearch's heap (-Xms and -Xmx), in GiB.
 */
export type SearchHeapGib = number | null;
/**
 * Overrides PostgreSQL's shared_buffers, in GiB.
 */
export type PostgresSharedBuffersGib = number | null;
/**
 * Overrides PostgreSQL's max_connections: the connections its services may hold at once. Default: none — the computed number (660), from the pools the product's services open. Not less than 420, the same sum with one Conduit. Lite, and Small with every store in a container; a cluster's or a cloud platform's database is set where it is run.
 */
export type PostgresMaxConnections = number | null;
/**
 * Default: none — the local engine runs on the CPU. nvidia: the ollama service reserves every NVIDIA GPU, and the extraction model is qwen2.5:14b-instruct unless models.extraction names one. The NVIDIA driver and Container Toolkit are the administrator's to install.
 */
export type Gpu = "none" | "nvidia";

/**
 * ADR-114 Amendment 33 decision 6: the stores sized to the server's memory. `memory_gib` is
 * measured once, at install (`server.memory_gib: auto`), and written here, so the render reads a
 * number and never the machine; resizing is an edit and `ospreyflow apply`. The three overrides
 * win over the rule (`harness/profiles.py`). Unset, every store keeps today's values.
 */
export interface ResourcesConfig {
  memory_gib?: MemoryGib;
  graph_heap_gib?: GraphHeapGib;
  search_heap_gib?: SearchHeapGib;
  postgres_shared_buffers_gib?: PostgresSharedBuffersGib;
  postgres_max_connections?: PostgresMaxConnections;
  gpu?: Gpu;
}
