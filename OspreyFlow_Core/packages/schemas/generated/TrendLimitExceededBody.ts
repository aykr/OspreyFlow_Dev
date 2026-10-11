// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type Error = "limit_exceeded";
export type CapKind = "periods" | "series";
export type Cap = number;
export type WouldBe = number;
export type Options = ("shorter_period" | "monthly_interval" | "fewer_series")[];

export interface TrendLimitExceededBody {
  error?: Error;
  cap_kind: CapKind;
  cap: Cap;
  would_be: WouldBe;
  options?: Options;
  [k: string]: unknown;
}
