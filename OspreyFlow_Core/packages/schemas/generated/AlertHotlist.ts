// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type Identifier = string;
export type KeptAsWritten = boolean;
export type ReviewDate = string;

/**
 * ADR-130 decision 1: the hotlist a `hotlist:` alert came from, read at display time and only
 * for the hotlist's owner. The identifier is as typed (else as stored).
 */
export interface AlertHotlist {
  identifier: Identifier;
  kept_as_written: KeptAsWritten;
  review_date: ReviewDate;
  [k: string]: unknown;
}
