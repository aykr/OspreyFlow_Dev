// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type Name = string;
export type Params =
  | StructuringParams
  | RapidMovementParams
  | CircularFlowParams
  | KycScreeningParams
  | SharedAttributesParams
  | DocumentVerificationParams
  | PatternRuleParams;
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
export type Typology3 = "kyc_screening";
export type MinScore = number;
export type ScreenOwners = boolean;
export type OwnerThreshold = number;
export type Typology4 = "shared_attributes";
export type MinOthers = number;
/**
 * @minItems 1
 */
export type Kinds = ["msisdn" | "email" | "ip" | "handle", ...("msisdn" | "email" | "ip" | "handle")[]];
export type Typology5 = "document_verification";
export type Typology6 = "pattern";
export type PatternId = string;
export type MaxMatches = number;
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
/**
 * ADR-109 phase F (the KYC addendum's Component 6): a newly loaded person or organisation
 * screened against the deployment's screening lists, and — for an organisation — each natural
 * person who ultimately owns at least `owner_threshold` of it, or controls it.
 */
export interface KycScreeningParams {
  typology?: Typology3;
  min_score?: MinScore;
  screen_owners?: ScreenOwners;
  owner_threshold?: OwnerThreshold;
  [k: string]: unknown;
}
/**
 * Component 6's synthetic-identity check: a new customer's phone, email, IP address or handle
 * already used by at least `min_others` other customers.
 */
export interface SharedAttributesParams {
  typology?: Typology4;
  min_others?: MinOthers;
  kinds?: Kinds;
  [k: string]: unknown;
}
/**
 * Component 7: a new customer with no valid verifying document — none, or each one expired
 * or marked fraudulent.
 */
export interface DocumentVerificationParams {
  typology?: Typology5;
  [k: string]: unknown;
}
/**
 * ADR-109 phase D, the no-code typology builder: a sub-graph drawn in the query builder and
 * saved (a `SavedPattern` the deployer owns, read afresh at each evaluation — ADR-036's own
 * discipline for monitors), deployed as a rule. Matched against the stored graph, so it runs
 * after commit only. A match larger than `max_matches` nodes is refused in words, never alerted on
 * in part (rule 2).
 */
export interface PatternRuleParams {
  typology?: Typology6;
  pattern_id: PatternId;
  max_matches?: MaxMatches;
  [k: string]: unknown;
}
