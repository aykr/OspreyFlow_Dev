// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type NodeId = string;
export type Nodes = NodeId[];
export type EdgeId = string;
export type Links = EdgeId[];
export type Pictures = EdgeId[];
export type WatchesEnded = number;

/**
 * What a withdrawal took back (never deleted: kept in the audit). Every drawn link and picture
 * touching a withdrawn node goes with it. Those the caller may see are named here, so nothing is
 * dropped silently (rule 2); one they may not see is named only in the audit, and counted in
 * nothing here, not even among the watches ended (rule 3).
 */
export interface Withdrawn {
  nodes?: Nodes;
  links?: Links;
  pictures?: Pictures;
  watches_ended?: WatchesEnded;
  [k: string]: unknown;
}
