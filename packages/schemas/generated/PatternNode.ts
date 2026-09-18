// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and _pending_port_placeholders.py, via generate_ts.py
export type Var = string;
export type EntityType = string | null;

export interface PatternNode {
  var: Var;
  entity_type?: EntityType;
  [k: string]: unknown;
}
