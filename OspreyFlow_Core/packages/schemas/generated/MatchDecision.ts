// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type NodeId = string;
export type Same = boolean;

/**
 * *Same* writes a confirmed `SAME_AS` (score 1.0) in the layer; *Not the same* a `NOT_SAME_AS`.
 * Neither changes the loaded item (decision 6; rule 6).
 */
export interface MatchDecision {
  drawn: NodeId;
  loaded: NodeId;
  same: Same;
}
