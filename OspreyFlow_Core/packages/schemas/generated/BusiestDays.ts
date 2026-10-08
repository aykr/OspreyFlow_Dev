// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type Start = string;
export type End = string;
export type Count = number;
export type Days = BusyDay[];
export type Total = number;
export type Offset = number;
export type ComputedAt = string | null;

/**
 * One page of the case's days by events, most first, ties by date; `total` is how many days
 * have any (rule 2).
 */
export interface BusiestDays {
  days: Days;
  total: Total;
  offset: Offset;
  computed_at?: ComputedAt;
  [k: string]: unknown;
}
export interface BusyDay {
  start: Start;
  end: End;
  count: Count;
  [k: string]: unknown;
}
