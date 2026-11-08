// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type Id = string;
export type Name = string | null;

export interface TeamMember {
  id: Id;
  name?: Name;
  [k: string]: unknown;
}
