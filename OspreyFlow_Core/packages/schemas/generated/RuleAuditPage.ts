// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type RecordedAt = string;
export type PrincipalId = string;
export type Action = string;
export type ResultCardinality = number;
export type Entries = RuleAuditEntry[];
export type Total = number;

/**
 * A page of a case's rule audit, newest first, with the total of what the reader may see —
 * an entry withheld from them is neither on the page nor in the total (rule 3).
 */
export interface RuleAuditPage {
  entries?: Entries;
  total: Total;
  [k: string]: unknown;
}
/**
 * One line of a case's rule audit (ADR-109 ruling 1): a deploy, retire, evaluation, firing,
 * failure, hold, release or rejection. Read only by the case's Authors and the deployment admin,
 * and an entry naming a node the reader cannot see is withheld whole (rule 3).
 */
export interface RuleAuditEntry {
  recorded_at: RecordedAt;
  principal_id: PrincipalId;
  action: Action;
  detail?: Detail;
  result_cardinality?: ResultCardinality;
  [k: string]: unknown;
}
export interface Detail {
  [k: string]: unknown;
}
