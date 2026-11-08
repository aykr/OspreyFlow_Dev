// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type Cover = string | null;
export type Until = string | null;

/**
 * Name a cover until a date (inclusive), a member other than the lead; `cover: null` ends
 * it.
 */
export interface TeamCoverInput {
  cover?: Cover;
  until?: Until;
  [k: string]: unknown;
}
