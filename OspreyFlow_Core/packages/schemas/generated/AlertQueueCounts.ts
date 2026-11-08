// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type Open = number;
export type Claimed = number;
export type Closing = number;

/**
 * A case's alert queue as counts alone (ADR-146 Amendment 2 point 3): what Home shows a reader
 * of the queue whom Rules and Monitoring is not offered to (the Data Engineer), who is given no
 * alert's title, words or id. Counted as the queue is, so an alert any of whose evidence is hidden
 * from the reader is not counted (rule 3).
 */
export interface AlertQueueCounts {
  open: Open;
  claimed: Claimed;
  closing: Closing;
  [k: string]: unknown;
}
