// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type Name = string;
export type Passed = boolean;
export type Words = string;

export interface PromotionCheck {
  name: Name;
  passed: Passed;
  words: Words;
}
