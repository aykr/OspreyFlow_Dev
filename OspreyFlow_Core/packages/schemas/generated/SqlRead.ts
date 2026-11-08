// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type Kind = "sql";
export type Table = string;
export type Columns = string[];

/**
 * A table (or view) of a SQL connection; the columns named, or all of them.
 */
export interface SqlRead {
  kind?: Kind;
  table: Table;
  columns?: Columns;
}
