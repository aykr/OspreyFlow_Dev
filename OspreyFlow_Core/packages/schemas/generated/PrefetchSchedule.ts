// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type EveryHours = (6 | 24 | 168) | null;

/**
 * Every area is fetched again this often; `None` means by hand only.
 */
export interface PrefetchSchedule {
  every_hours?: EveryHours;
}
