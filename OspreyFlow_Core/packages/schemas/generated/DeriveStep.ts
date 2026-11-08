// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type Id = string;
export type Label = string | null;
export type Kind = "derive";
export type Input = string;
export type Column = string;
export type Operation = "concat" | "split" | "substring" | "date_parse" | "arithmetic" | "case_when" | "normalise";
/**
 * @minItems 1
 */
export type Columns = [string, ...string[]];

/**
 * A new column from a catalogued operation over named columns (brief §6). `settings` are the
 * operation's declared settings (a separator, a part, a time zone…), data and never code; the
 * operation refuses a wrong one in words, as its golden file shows.
 */
export interface DeriveStep {
  id: Id;
  label?: Label;
  kind: Kind;
  input: Input;
  column: Column;
  operation: Operation;
  columns: Columns;
  settings?: Settings;
}
export interface Settings {
  [k: string]: unknown;
}
