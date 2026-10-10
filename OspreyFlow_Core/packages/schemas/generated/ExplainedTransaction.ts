// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type EventId = string;
export type EdgeId = string;
export type NodeId = string;
export type OccurredAt = string;
export type Amount = number | null;

/**
 * One transaction an alert cites, as the reader may read it: the link it is on, its ends,
 * when, and how much.
 */
export interface ExplainedTransaction {
  event_id: EventId;
  edge_id: EdgeId;
  source_id: NodeId;
  target_id: NodeId;
  occurred_at: OccurredAt;
  amount?: Amount;
  [k: string]: unknown;
}
