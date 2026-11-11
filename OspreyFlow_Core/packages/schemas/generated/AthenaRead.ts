// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type Kind = "athena";
export type Table = string | null;
export type NamedQuery = string | null;

/**
 * A table of one of the connection's databases, read whole, or a named query saved in the
 * connection's workgroup (a SELECT, checked before it runs); never a query written here
 * (rule 8).
 */
export interface AthenaRead {
  kind?: Kind;
  table?: Table;
  named_query?: NamedQuery;
}
