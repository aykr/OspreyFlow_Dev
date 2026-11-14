// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type Earliest = string | null;
export type Latest = string | null;

export interface DateSpan {
  earliest: Earliest;
  latest: Latest;
  [k: string]: unknown;
}
