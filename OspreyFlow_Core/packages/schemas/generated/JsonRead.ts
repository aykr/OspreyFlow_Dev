// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type Kind = "json";
export type Pattern = string;
export type RecordsAt = string | null;

/**
 * JSON files of the dataset's folder whose names match `pattern`, records at `records_at`.
 */
export interface JsonRead {
  kind?: Kind;
  pattern: Pattern;
  records_at?: RecordsAt;
}
