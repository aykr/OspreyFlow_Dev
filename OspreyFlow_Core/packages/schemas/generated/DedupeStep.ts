// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type Id = string;
export type Label = string | null;
export type Kind = "dedupe";
export type Input = string;
/**
 * @minItems 1
 */
export type On = [string, ...string[]];

/**
 * Drop repeats on declared columns (today's deduplication key, as a step). The first row in
 * the input's order stands for its repeats and carries all their refs, so the element it becomes
 * names every source row it stands for; the repeats are counted.
 */
export interface DedupeStep {
  id: Id;
  label?: Label;
  kind: Kind;
  input: Input;
  on: On;
}
