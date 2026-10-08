// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type EdgeId = string;
export type NodeId = string;
export type Weight = number;

export interface StructureEdge {
  id: EdgeId;
  source: NodeId;
  target: NodeId;
  weight?: Weight;
  [k: string]: unknown;
}
