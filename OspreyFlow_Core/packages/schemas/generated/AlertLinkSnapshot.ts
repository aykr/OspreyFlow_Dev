// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type EdgeId = string;
export type Type = string;
export type SourceName = string;
export type TargetName = string;

/**
 * A link an alert cites as evidence.
 */
export interface AlertLinkSnapshot {
  edge_id: EdgeId;
  type: Type;
  source_name: SourceName;
  target_name: TargetName;
  [k: string]: unknown;
}
