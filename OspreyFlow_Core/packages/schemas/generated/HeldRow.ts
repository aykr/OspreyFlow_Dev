// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type Id = string;
export type InvestigationId = string;
export type RecipeId = string;
export type RecipeVersion = number;
export type LoadId = string;
export type Source = string;
export type RowIndex = number;
export type RuleId = string;
export type Reason = string;
export type Classification = string;
export type HandlingCode = string;
export type ActionCode = string | null;
export type SanitisationCode = string | null;
export type OrgUnitId = string;
export type ReviewDate = string | null;
export type LegalBasis = string | null;
export type Status = "held" | "released" | "rejected";
export type HeldAt = string;
export type DecidedBy = string | null;
export type DecidedAt = string | null;
export type DecisionReason = string | null;
export type DatasetId = string | null;

/**
 * A source row a pre-commit rule could not judge — it errored or overran its budget — held
 * out of the graph for a reviewer (ADR-109 ruling 1, fail closed). Carries the row as read and its
 * original row number, so a release loads it with its provenance unchanged; `handling` is the
 * marking the recipe would have given it, and a reader is filtered by it (rule 3).
 */
export interface HeldRow {
  id: Id;
  investigation_id: InvestigationId;
  recipe_id: RecipeId;
  recipe_version: RecipeVersion;
  load_id: LoadId;
  source: Source;
  row_index: RowIndex;
  row: Row;
  rule_id: RuleId;
  reason: Reason;
  handling: Handling;
  status?: Status;
  held_at: HeldAt;
  decided_by?: DecidedBy;
  decided_at?: DecidedAt;
  decision_reason?: DecisionReason;
  dataset_id?: DatasetId;
  [k: string]: unknown;
}
export interface Row {
  [k: string]: string;
}
export interface Handling {
  classification: Classification;
  handling_code: HandlingCode;
  action_code?: ActionCode;
  sanitisation_code?: SanitisationCode;
  originator: OrgUnitId;
  owning_unit: OrgUnitId;
  review_date?: ReviewDate;
  legal_basis?: LegalBasis;
  [k: string]: unknown;
}
