// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type RecordedAt = string;
export type PrincipalId = string;
export type PrincipalName = string | null;
export type Action = string;
export type ResultCardinality = number;

/**
 * One line of a case's rule audit (ADR-109 ruling 1): a deploy, retire, evaluation, firing,
 * failure, hold, release or rejection. Read only by the case's Authors and the deployment admin,
 * and an entry naming a node the reader cannot see is withheld whole (rule 3).
 */
export interface RuleAuditEntry {
  recorded_at: RecordedAt;
  principal_id: PrincipalId;
  principal_name?: PrincipalName;
  action: Action;
  detail?: Detail;
  result_cardinality?: ResultCardinality;
  [k: string]: unknown;
}
export interface Detail {
  [k: string]: unknown;
}
