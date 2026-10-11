// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type WeekStart = string;
export type Typology = string;
export type Count = number;

/**
 * Alerts raised in one week (Monday to Sunday) of one typology, as the reader sees them.
 */
export interface WeekCount {
  week_start: WeekStart;
  typology: Typology;
  count: Count;
  [k: string]: unknown;
}
