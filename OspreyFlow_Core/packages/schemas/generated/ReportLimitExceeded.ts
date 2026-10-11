// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type Error = "limit_exceeded";
export type CapKind = "alerts" | "customers";
export type Cap = number;
export type WouldBe = number;
export type Options = ("shorter_period" | "fewer_typologies")[];

/**
 * A report past its bound answers this, never a partial figure presented as whole (rule 2).
 * `would_be` counts only what the reader can see, so the refusal itself discloses nothing.
 */
export interface ReportLimitExceeded {
  error?: Error;
  cap_kind: CapKind;
  cap: Cap;
  would_be: WouldBe;
  options?: Options;
  [k: string]: unknown;
}
