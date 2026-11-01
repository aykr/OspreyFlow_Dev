// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type NodeId = string;
export type EntityType = string;
export type Name = string;

/**
 * An entity an alert matched, named as its adder read it.
 */
export interface AlertEntitySnapshot {
  node_id: NodeId;
  entity_type: EntityType;
  name: Name;
  [k: string]: unknown;
}
