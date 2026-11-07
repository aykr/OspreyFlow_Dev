// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type NodeId = string;
export type NodeIds = NodeId[];
export type EdgeId = string;
export type EdgeIds = EdgeId[];
export type EventIds = string[];

/**
 * What one kept row wrote (ADR-110 Amendment 8 point 2): the nodes it wrote or matched and the
 * links it wrote, created or merged into, each by its stored id, and the events it wrote, by
 * `event_id` (Amendment 15: a full snapshot withdraws a dropped row's own events by these, never
 * by link). For the ledger alone.
 */
export interface RowElements {
  node_ids?: NodeIds;
  edge_ids?: EdgeIds;
  event_ids?: EventIds;
  [k: string]: unknown;
}
