// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and _pending_port_placeholders.py, via generate_ts.py
export type NodeId = string;
export type NodeIds = NodeId[];
export type Depth = number;
export type EdgeTypes = string[] | null;
export type Direction = "out" | "in" | "both";
export type ValidFrom = string;
export type ValidTo = string | null;

export interface ExpandRequest {
  node_ids: NodeIds;
  depth?: Depth;
  edge_types?: EdgeTypes;
  direction?: Direction;
  temporal_window?: Interval | null;
  [k: string]: unknown;
}
export interface Interval {
  valid_from: ValidFrom;
  valid_to?: ValidTo;
  [k: string]: unknown;
}
