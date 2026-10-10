// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type NodeId = string;
export type Type = string;
export type Nodes = StructureNode[];
export type EdgeId = string;
export type Weight = number;
export type Edges = StructureEdge[];
export type MaxHops = number;
export type Decay = number;

/**
 * How much risk reaches `target` from the seeds around it: each seed's weight decayed by
 * `decay` per hop of its *shortest* distance (links undirected), counted once, out to `max_hops`.
 * The structure is whatever the caller read as the reader — so a seed, or a path, the reader
 * cannot see contributes nothing (rule 3).
 */
export interface PropagationRequest {
  target: NodeId;
  nodes: Nodes;
  edges: Edges;
  seeds: Seeds;
  max_hops?: MaxHops;
  decay?: Decay;
  [k: string]: unknown;
}
export interface StructureNode {
  id: NodeId;
  type: Type;
  [k: string]: unknown;
}
export interface StructureEdge {
  id: EdgeId;
  source: NodeId;
  target: NodeId;
  weight?: Weight;
  [k: string]: unknown;
}
export interface Seeds {
  [k: string]: number;
}
