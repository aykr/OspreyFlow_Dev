// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type Step = string;
export type Problems = string[];

/**
 * The gate's words for one SQL step, empty when it may be saved. Nothing runs over a row: the
 * step's drawer shows its output on the live sample (`POST …/staging-preview`).
 */
export interface SqlCheck {
  step: Step;
  problems?: Problems;
}
