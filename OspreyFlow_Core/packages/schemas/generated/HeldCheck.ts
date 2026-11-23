// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type Id = string;
export type Engine = string;
export type Label = string;
export type By = string;
export type At = string;
export type ExpiresAt = string;

/**
 * A passed check waiting for **Add** (ADR-135 Amendment 14 point 2), shown in Admin as being
 * checked so it can be cancelled; never an engine, never offered to analysts.
 */
export interface HeldCheck {
  id: Id;
  engine: Engine;
  label: Label;
  by: By;
  at: At;
  expires_at: ExpiresAt;
  [k: string]: unknown;
}
