// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type GapId = string;
export type InvestigationId = string;
export type Question = string;
export type PrincipalId = string;
export type NodeId = string;
export type LinkedEntities = NodeId[];
export type Status = "open" | "tasked" | "answered" | "closed";
export type CreatedAt = string;

/**
 * `01_DOMAIN_MODEL.md` §5, Phase 8 Stage 4b.
 */
export interface IntelligenceGap {
  id: GapId;
  investigation_id: InvestigationId;
  question: Question;
  raised_by: PrincipalId;
  linked_entities?: LinkedEntities;
  status?: Status;
  created_at: CreatedAt;
  [k: string]: unknown;
}
