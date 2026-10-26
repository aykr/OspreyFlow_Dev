// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type Var = string;
export type EntityType = string | null;
export type NodeId = string | null;

export interface PatternNode {
  var: Var;
  entity_type?: EntityType;
  node_id?: NodeId;
  where?: Where;
  [k: string]: unknown;
}
export interface Where {
  [k: string]: string;
}
