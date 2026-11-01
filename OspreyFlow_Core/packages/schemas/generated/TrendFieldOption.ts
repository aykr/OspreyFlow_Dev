// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type Name = string;
export type Kind = "number" | "category";
export type Values = string[];
export type Labels = string[];

export interface TrendFieldOption {
  name: Name;
  kind: Kind;
  values?: Values;
  labels?: Labels;
  [k: string]: unknown;
}
