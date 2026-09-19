// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type Var = string;
export type EntityType = string | null;
export type Nodes = PatternNode[];
export type EdgeType = string;
export type FromVar = string;
export type ToVar = string;
export type Edges = PatternEdge[];
export type Limit = number;

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
  [k: string]: unknown;
}
export interface PatternEdge {
  edge_type: EdgeType;
  from_var: FromVar;
  to_var: ToVar;
  [k: string]: unknown;
}
