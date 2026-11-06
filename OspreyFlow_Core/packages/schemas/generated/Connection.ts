// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type Id = string;
export type Kind = "files";
export type Name = string;
export type CreatedBy = string;
export type CreatedAt = string;

export interface Connection {
  id: Id;
  kind: Kind;
  name: Name;
  created_by: CreatedBy;
  created_at: CreatedAt;
  [k: string]: unknown;
}
