// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type AssumptionId = string;
export type InvestigationId = string;
export type Statement = string;
export type IfFalseImpact = string;
export type JudgementId = string;
export type LinkedJudgements = JudgementId[];
export type CreatedAt = string;

/**
 * `01_DOMAIN_MODEL.md` §5, Phase 8 Stage 4b.
 */
export interface Assumption {
  id: AssumptionId;
  investigation_id: InvestigationId;
  statement: Statement;
  if_false_impact: IfFalseImpact;
  linked_judgements?: LinkedJudgements;
  created_at: CreatedAt;
  [k: string]: unknown;
}
