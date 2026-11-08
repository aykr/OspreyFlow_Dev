// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type Kind = "api";
export type Path = string;
export type RecordsAt = string | null;

/**
 * A path under the connection's base URL, and where each page's records are.
 */
export interface ApiRead {
  kind?: Kind;
  path: Path;
  records_at?: RecordsAt;
}
