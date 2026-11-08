// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type NodeId = string;
export type Nodes = NodeId[];
export type EdgeId = string;
export type Links = EdgeId[];
export type WatchesEnded = number;

/**
 * What a withdrawal took back (never deleted: kept in the audit). Every drawn link touching a
 * withdrawn node goes with it, and is named here, so nothing is dropped silently (rule 2).
 */
export interface Withdrawn {
  nodes?: Nodes;
  links?: Links;
  watches_ended?: WatchesEnded;
  [k: string]: unknown;
}
