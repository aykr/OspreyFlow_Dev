// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type EdgeId = string;

/**
 * The link a match decision wrote.
 */
export interface MatchDecided {
  edge_id: EdgeId;
  [k: string]: unknown;
}
