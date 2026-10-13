// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type NodeId = string;
export type Degree = number | null;
export type EdgeTypes = string[] | null;

/**
 * ADR-116 decision 6. With no `degree`, the fewest degrees that connect the two, looked for up
 * to `CONNECTIONS_DEFAULT_REACH`; with one, the routes at exactly that degree.
 */
export interface ConnectionsRequest {
  source: NodeId;
  target: NodeId;
  degree?: Degree;
  edge_types?: EdgeTypes;
  [k: string]: unknown;
}
