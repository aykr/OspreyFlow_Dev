// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type NodeId = string;
export type Nodes = NodeId[];
export type EdgeId = string;
export type Edges = EdgeId[];
export type Length = number;

export interface Path {
  nodes: Nodes;
  edges: Edges;
  length: Length;
  [k: string]: unknown;
}
