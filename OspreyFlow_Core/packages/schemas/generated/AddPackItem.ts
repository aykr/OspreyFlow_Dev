// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type Kind = "trend" | "assessment" | "entity" | "note";
export type TrendId = string | null;
export type JudgementId = string | null;
export type NodeId = string | null;
export type Caption = string | null;
export type Text = string | null;
export type Classification = string | null;
export type HandlingCode = string | null;

/**
 * What to add. The server reads and freezes the content itself, as the adder; nothing here is
 * trusted as content except a caption and a note's own words.
 */
export interface AddPackItem {
  kind: Kind;
  trend_id?: TrendId;
  judgement_id?: JudgementId;
  node_id?: NodeId;
  caption?: Caption;
  text?: Text;
  classification?: Classification;
  handling_code?: HandlingCode;
  [k: string]: unknown;
}
