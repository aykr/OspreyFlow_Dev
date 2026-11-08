// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type Left = string;
export type Right = string;

/**
 * The two elements of Map's row template the match says may be one: `left`, written from the
 * left table's columns, and `right`, from the matched columns. The engine writes a scored
 * `SAME_AS` between them marked `inferred`, never a merge (ADR-006 Amendment 1; rules 5 and 6).
 */
export interface FuzzySameAs {
  left: Left;
  right: Right;
}
