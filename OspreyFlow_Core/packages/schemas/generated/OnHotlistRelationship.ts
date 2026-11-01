// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type Kind = "on_hotlist";

/**
 * The subject's identifier is on one of the author's own active hotlists (ADR-038).
 */
export interface OnHotlistRelationship {
  kind?: Kind;
  [k: string]: unknown;
}
