// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type DatasetId = string;
export type DatasetName = string;
export type ToDecide = number;
export type AboveClearance = boolean;

/**
 * One dataset's proposed link types in the reader's *Needs you* (ADR-145 decision 11, A2;
 * ADR-090 Amendment 4): how many the reader may read and decide, and whether any exist above
 * their clearance. That is a flag, not a count, with no word of the proposal (ADR-143
 * Amendment 4's *Open*, the strict reading).
 */
export interface NeedsYouProposals {
  dataset_id: DatasetId;
  dataset_name: DatasetName;
  to_decide: ToDecide;
  above_clearance: AboveClearance;
  [k: string]: unknown;
}
