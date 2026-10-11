// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type Held = number;
export type Released = number;
export type Rejected = number;

/**
 * The case's held rows by what became of them — for Editors and above only, as the Held rows
 * tab is (ADR-111 decision 2).
 */
export interface HeldFigures {
  held: Held;
  released: Released;
  rejected: Rejected;
  [k: string]: unknown;
}
