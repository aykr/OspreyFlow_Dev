// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type NodeId = string;
export type MaxHops = number;
export type K = number;
export type EdgeTypes = string[] | null;

export interface PathRequest {
  source: NodeId;
  target: NodeId;
  max_hops?: MaxHops;
  k?: K;
  edge_types?: EdgeTypes;
  [k: string]: unknown;
}
