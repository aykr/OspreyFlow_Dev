// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type NodeId = string;
export type Type = string;
export type Nodes = StructureNode[];
export type EdgeId = string;
export type Kind = "owns" | "controls";
export type Percent = number | null;
export type Links = OwnershipLink[];
export type Threshold = number;
export type MaxDepth = number;

/**
 * Who ultimately owns or controls `target`, through every chain of `links` that reaches
 * it. `nodes` carry each party's type, so a natural person is told apart.
 */
export interface OwnershipRequest {
  target: NodeId;
  nodes: Nodes;
  links: Links;
  threshold?: Threshold;
  max_depth?: MaxDepth;
  [k: string]: unknown;
}
export interface StructureNode {
  id: NodeId;
  type: Type;
  [k: string]: unknown;
}
/**
 * One link of a corporate structure, owner to owned: `owns` with its percentage (0–100;
 * `None` when the record states none), or `controls` (control without a stated share).
 */
export interface OwnershipLink {
  id: EdgeId;
  source: NodeId;
  target: NodeId;
  kind: Kind;
  percent?: Percent;
  [k: string]: unknown;
}
