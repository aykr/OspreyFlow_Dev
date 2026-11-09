// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type DatasetId = string;
export type DatasetName = string;
export type ToDecide = number;

/**
 * One dataset's proposed link types in the reader's *Needs you* (ADR-145 decision 11, A2;
 * ADR-090 Amendment 4): how many the reader may read and decide. A dataset whose proposals the
 * reader is not cleared to read is not listed at all, not even as having one open (ADR-143
 * Amendment 4's *Open*, the strict reading; the orchestrator's ruling at L2.7's review).
 */
export interface NeedsYouProposals {
  dataset_id: DatasetId;
  dataset_name: DatasetName;
  to_decide: ToDecide;
  [k: string]: unknown;
}
