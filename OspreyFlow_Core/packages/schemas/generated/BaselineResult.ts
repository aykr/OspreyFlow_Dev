// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type BaselineCount = number;
export type ComparisonCount = number;
export type BaselineRatePerBucket = number;
export type ComparisonRatePerBucket = number;
export type Ratio = number | null;

export interface BaselineResult {
  baseline_count: BaselineCount;
  comparison_count: ComparisonCount;
  baseline_rate_per_bucket: BaselineRatePerBucket;
  comparison_rate_per_bucket: ComparisonRatePerBucket;
  ratio?: Ratio;
  [k: string]: unknown;
}
