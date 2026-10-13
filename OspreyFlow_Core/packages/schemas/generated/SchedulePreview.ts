// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type Words = string;
export type NextRuns = string[];

/**
 * The schedule in words and its next five runs, in UTC.
 */
export interface SchedulePreview {
  words: Words;
  next_runs: NextRuns;
  [k: string]: unknown;
}
