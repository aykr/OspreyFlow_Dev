// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type NodeId = string;
export type EntityType = string;
export type Name = string;
export type Caption = string;

export interface EntitySnapshot {
  node_id: NodeId;
  entity_type: EntityType;
  name: Name;
  caption: Caption;
  [k: string]: unknown;
}
