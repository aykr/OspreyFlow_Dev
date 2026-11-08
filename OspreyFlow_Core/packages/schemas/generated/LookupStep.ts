// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type Id = string;
export type Label = string | null;
export type Kind = "lookup";
export type Input = string;
export type List = string;
export type On = string;
export type Normalise = string | null;
/**
 * @minItems 1
 */
export type Add = [AddedColumn, ...AddedColumn[]];
export type Column = string;
export type As = string | null;

/**
 * Add columns from a reference list on a key: every row of `input` is kept, and a row whose
 * key is not in the list keeps empty cells for the added columns (counted, never dropped). The
 * list is the dataset's own, or a screening list the dataset subscribes to (ADR-140 Amendment 9
 * decision 3); its key column is the list's own `key_column`.
 */
export interface LookupStep {
  id: Id;
  label?: Label;
  kind: Kind;
  input: Input;
  list: List;
  on: On;
  normalise?: Normalise;
  add: Add;
}
/**
 * A column a Lookup or a Join brings across, optionally renamed.
 */
export interface AddedColumn {
  column: Column;
  as?: As;
}
