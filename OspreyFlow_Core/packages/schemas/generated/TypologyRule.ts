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
export type Id = string;
export type InvestigationId = string;
export type OwnerId = string;
export type Status = "active" | "retired";
export type CreatedAt = string;
export type RetiredAt = string | null;
export type DatasetId = string | null;

/**
 * A deployed rule. It belongs to the case it was deployed in and evaluates as its deployer's
 * principal, resolved fresh at each evaluation (ADR-036, unchanged by ADR-109).
 */
export interface TypologyRule {
  name: Name;
  params: Params;
  trigger?: Trigger;
  budget_ms?: BudgetMs;
  id: Id;
  investigation_id: InvestigationId;
  owner_id: OwnerId;
  status?: Status;
  created_at: CreatedAt;
  retired_at?: RetiredAt;
  dataset_id?: DatasetId;
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
