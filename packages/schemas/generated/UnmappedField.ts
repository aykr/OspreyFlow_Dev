// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type Field = string;
export type Action = "ignore";
export type Note = string | null;

export interface UnmappedField {
  field: Field;
  action?: Action;
  note?: Note;
  [k: string]: unknown;
}
