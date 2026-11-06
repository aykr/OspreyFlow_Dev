// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type Kind = "files";
export type Name = string;

export interface ConnectionInput {
  kind?: Kind;
  name: Name;
  [k: string]: unknown;
}
