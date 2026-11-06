// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type NodeId = string;
export type NodeIds = NodeId[];
export type EdgeId = string;
export type EdgeIds = EdgeId[];

/**
 * What one kept row wrote (ADR-110 Amendment 8 point 2): the nodes it wrote or matched and the
 * links it wrote, created or merged into, each by its stored id. For the ledger alone.
 */
export interface RowElements {
  node_ids?: NodeIds;
  edge_ids?: EdgeIds;
  [k: string]: unknown;
}
