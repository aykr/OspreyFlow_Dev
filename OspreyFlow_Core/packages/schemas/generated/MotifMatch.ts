// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type MotifType = "convoy" | "relay" | "burst";
export type NodeId = string;
export type NodeIds = NodeId[];
export type ValidFrom = string;
export type ValidTo = string | null;

export interface MotifMatch {
  motif_type: MotifType;
  node_ids: NodeIds;
  interval?: Interval | null;
  [k: string]: unknown;
}
export interface Interval {
  valid_from: ValidFrom;
  valid_to?: ValidTo;
  [k: string]: unknown;
}
