// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type NodeId = string;
export type Type = string;

export interface StructureNode {
  id: NodeId;
  type: Type;
  [k: string]: unknown;
}
