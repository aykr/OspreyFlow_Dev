// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type Classification = string;
export type HandlingCode = string;
export type OwningUnit = string;
export type Originator = string;

/**
 * One distinct handling among the events a trend counted: what a reader of a frozen snapshot
 * must be able to view (ADR-113 Amendment 1) — the restricted code and its units, not only the
 * classification.
 */
export interface CountedHandling {
  classification: Classification;
  handling_code: HandlingCode;
  owning_unit: OwningUnit;
  originator: Originator;
  [k: string]: unknown;
}
