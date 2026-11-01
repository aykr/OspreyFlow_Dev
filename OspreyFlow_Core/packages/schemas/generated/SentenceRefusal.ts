// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type Error = "sentence_refused";
export type Blank = string;
export type Reason = string;
export type Detail = string;

/**
 * A sentence refused at validation, by the blank it is about, in words (never a bare 400).
 */
export interface SentenceRefusal {
  error?: Error;
  blank: Blank;
  reason: Reason;
  detail: Detail;
  [k: string]: unknown;
}
