// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type Views = number;
export type Cases = number;
export type Problem = string | null;

/**
 * ADR-144 decision 6 on *Admin › System*: how many cases made from another became views, in how
 * many cases; the migration's dry-run report names any it did not place. Counted in the
 * administrator's own unit only (rule 7).
 */
export interface ConvertedViews {
  views?: Views;
  cases?: Cases;
  problem?: Problem;
  [k: string]: unknown;
}
