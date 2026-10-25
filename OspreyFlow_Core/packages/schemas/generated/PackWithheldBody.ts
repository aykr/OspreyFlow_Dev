// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type Error = "pack_has_withheld_items";
export type Withheld = boolean;

/**
 * Publishing refused: the draft holds items the publisher may not see (Amendment 1).
 */
export interface PackWithheldBody {
  error?: Error;
  withheld?: Withheld;
  [k: string]: unknown;
}
