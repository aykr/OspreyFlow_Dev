// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type Words = string;
export type NodeId = string;
export type NodeIds = NodeId[];
export type EdgeId = string;
export type EdgeIds = EdgeId[];
export type Status = "open" | "closing" | "closed";
export type Disposition = ("true_positive" | "false_positive" | "duplicate" | "no_further_action" | "referred") | null;
export type DispositionReason = string | null;
export type DecidedBy = string | null;
export type DecidedAt = string | null;
export type CloseProposedBy = string | null;

/**
 * ADR-146 Amendment 7: one of the things an alert cites that a reader may be cleared for or
 * not, apart from the rest of it: a screening alert's match on one list (the listed party and the
 * scored `SAME_AS` to it). The alert is shown to a reader who may read everything it rests on
 * outside its citations and at least one citation; each citation is shown only to a reader who
 * may read every node and link it names, and a hidden one is left out of the alert as served
 * (its words, its ids and how many there are), so the alert never says which lists, or how many,
 * a reader cannot see (rule 3).
 */
export interface AlertCitation {
  words: Words;
  node_ids?: NodeIds;
  edge_ids?: EdgeIds;
  status?: Status;
  disposition?: Disposition;
  disposition_reason?: DispositionReason;
  decided_by?: DecidedBy;
  decided_at?: DecidedAt;
  close_proposed_by?: CloseProposedBy;
  [k: string]: unknown;
}
