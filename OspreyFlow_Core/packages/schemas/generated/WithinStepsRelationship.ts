// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type Kind = "within_steps";
export type Steps = number;
export type OtherType = string;

/**
 * Within N steps of something of a declared type, by any links the author may see.
 */
export interface WithinStepsRelationship {
  kind?: Kind;
  steps: Steps;
  other_type: OtherType;
  [k: string]: unknown;
}
