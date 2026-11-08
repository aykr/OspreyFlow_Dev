// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type RecordedAt = string;
export type PrincipalId = string;
export type PrincipalName = string | null;
export type Action = string;
export type Kind =
  | "assertions"
  | "loads_and_promotions"
  | "types"
  | "people_and_roles"
  | "datasets"
  | "rules"
  | "models"
  | "reads_and_other";
export type HeldIn = "case_and_admin" | "rules" | "models";
export type InvestigationId = string | null;
export type CaseName = string | null;
export type Detail = {
  [k: string]: unknown;
} | null;
export type WordsWithheld = boolean;
export type ResultCardinality = number | null;

/**
 * One entry of Admin › Audit, read under the reader's own principal (rule 3). `detail` holds
 * the entry's words only where the reader's own read of that record would show them; otherwise it
 * is null and `words_withheld` says so, and the entry's count is withheld with them.
 */
export interface AuditSectionEntry {
  recorded_at: RecordedAt;
  principal_id: PrincipalId;
  principal_name?: PrincipalName;
  action: Action;
  kind: Kind;
  held_in: HeldIn;
  investigation_id?: InvestigationId;
  case_name?: CaseName;
  detail?: Detail;
  words_withheld?: WordsWithheld;
  result_cardinality?: ResultCardinality;
  [k: string]: unknown;
}
