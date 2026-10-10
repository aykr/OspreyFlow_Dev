// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type Typology = "rapid_movement";
export type WithinHours = number;
export type KeepFraction = number;

export interface RapidMovementParams {
  typology?: Typology;
  within_hours: WithinHours;
  keep_fraction: KeepFraction;
  [k: string]: unknown;
}
