// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type Name = string;
export type Ok = boolean;
export type Millis = number;
export type Detail = string | null;

/**
 * One part of the running deployment, asked just now: whether it answered, and how fast.
 */
export interface ComponentHealth {
  name: Name;
  ok: Ok;
  millis: Millis;
  detail?: Detail;
  [k: string]: unknown;
}
