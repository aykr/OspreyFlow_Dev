// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type Name = string;
export type Params = StructuringParams | RapidMovementParams | CircularFlowParams;
export type Typology = "structuring";
export type Threshold = number;
export type WindowDays = number;
export type MinimumCount = number;
export type Typology1 = "rapid_movement";
export type WithinHours = number;
export type KeepFraction = number;
export type Typology2 = "circular_flow";
export type MaxHops = number;
export type WindowDays1 = number;
export type Trigger = "pre_commit" | "post_commit";
export type BudgetMs = number;

/**
 * What a case Author deploys (ADR-109 ruling 4): a typology with its parameters and the
 * trigger point it runs at. `budget_ms` bounds a pre-commit evaluation; overrunning it holds the
 * rows it could not judge (ruling 1, fail closed).
 */
export interface TypologyRuleInput {
  name: Name;
  params: Params;
  trigger?: Trigger;
  budget_ms?: BudgetMs;
  [k: string]: unknown;
}
export interface StructuringParams {
  typology?: Typology;
  threshold: Threshold;
  window_days: WindowDays;
  minimum_count: MinimumCount;
  [k: string]: unknown;
}
export interface RapidMovementParams {
  typology?: Typology1;
  within_hours: WithinHours;
  keep_fraction: KeepFraction;
  [k: string]: unknown;
}
export interface CircularFlowParams {
  typology?: Typology2;
  max_hops: MaxHops;
  window_days: WindowDays1;
  [k: string]: unknown;
}
