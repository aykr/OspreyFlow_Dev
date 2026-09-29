// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type Id = string;
export type PatternId = string;
export type Version = number;
export type Name = string;
export type OwnerId = string;
export type CreatedAt = string;
export type Var = string;
export type EntityType = string | null;
export type NodeId = string | null;
export type Nodes = PatternNode[];
export type EdgeType = string;
export type FromVar = string;
export type ToVar = string;
export type Edges = PatternEdge[];
export type Limit = number;

/**
 * A persisted `PatternQuery` — Phase 7 Stage 4's own "saveable ... and versioned" promise
 * (`02_GLASS_FRONTEND.md` §3.3), closed for save/load/list/version by `06_DECISIONS.md` ADR-032/
 * 036/040. `pattern_id` is stable across saves; `id` and `version` identify one specific save.
 * Deliberately carries `owner_id` and nothing shaped like `Handling.owning_unit` or a share
 * target — ADR-036 and ADR-040 both require a saved pattern readable only by its own owner until
 * ADR-040 (pattern sharing) is accepted; there is no broader-audience field to widen by mistake
 * because none exists yet.
 */
export interface SavedPattern {
  id: Id;
  pattern_id: PatternId;
  version: Version;
  name: Name;
  owner_id: OwnerId;
  created_at: CreatedAt;
  definition: PatternQuery;
  [k: string]: unknown;
}
/**
 * A bounded pattern description the Conduit compiles from a fixed set
 * of builders — never free-form Gremlin (ADR-003).
 */
export interface PatternQuery {
  nodes: Nodes;
  edges: Edges;
  limit?: Limit;
  [k: string]: unknown;
}
export interface PatternNode {
  var: Var;
  entity_type?: EntityType;
  node_id?: NodeId;
  [k: string]: unknown;
}
export interface PatternEdge {
  edge_type: EdgeType;
  from_var: FromVar;
  to_var: ToVar;
  [k: string]: unknown;
}
