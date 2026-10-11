// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type Version = string | null;
export type Name = string;
export type Ok = boolean;
export type Millis = number;
export type Detail = string | null;
export type Components = ComponentHealth[];

/**
 * The Admin area's *System* screen (ADR-110 Amendment 1): each component, asked as the screen
 * opens — what the harness's preflight showed before launch, for a running deployment.
 */
export interface SystemStatus {
  version?: Version;
  components: Components;
  [k: string]: unknown;
}
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
