// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type NodeId = string;
export type Type = string;
export type Nodes = StructureNode[];
export type EdgeId = string;
export type Weight = number;
export type Edges = StructureEdge[];

/**
 * A graph as only its structure (ADR-100 Amendment 5): each node's id and type, each link's
 * id, ends and weight. What groups are found from in a large case, whose records read in full are
 * hundreds of megabytes (measured: 1.6 KB a link on the Enron case).
 */
export interface LinkStructure {
  nodes: Nodes;
  edges: Edges;
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
