// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py and _pending_port_placeholders.py, via generate_ts.py
export type EdgeType = string;
export type FromVar = string;
export type ToVar = string;

export interface PatternEdge {
  edge_type: EdgeType;
  from_var: FromVar;
  to_var: ToVar;
  [k: string]: unknown;
}
