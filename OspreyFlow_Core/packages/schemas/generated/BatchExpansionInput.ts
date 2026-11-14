// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type NodeId = string;
export type NodeIds = NodeId[];
export type Depth = number;
export type EdgeTypes = string[] | null;
export type Direction = "out" | "in" | "both";
export type ValidFrom = string;
export type ValidTo = string | null;
export type Justification = string | null;
export type Name = string | null;

/**
 * `POST /v1/investigations/{id}/batch-expansions`: the refused expansion's own body
 * (`ExpandBody`), with the view's name if the analyst gave one.
 */
export interface BatchExpansionInput {
  request: ExpandRequest;
  justification?: Justification;
  name?: Name;
}
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
