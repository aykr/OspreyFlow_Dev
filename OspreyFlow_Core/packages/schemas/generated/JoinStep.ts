// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type Id = string;
export type Label = string | null;
export type Kind = "join";
export type Left = string;
export type Right = string;
export type LeftKey = string;
export type RightKey = string;
export type Normalise = string | null;
export type How = "inner" | "left";
/**
 * @minItems 1
 */
export type Add = [AddedColumn, ...AddedColumn[]];
export type Column = string;
export type As = string | null;

/**
 * Join two tables on a declared key, never a guessed one (brief §6): exact, or each side read
 * through the same Knowledge Adapter first (E.164, prison number, IBAN…). A row of `left` with
 * several matches gives one row per match, each carrying both sides' refs.
 */
export interface JoinStep {
  id: Id;
  label?: Label;
  kind: Kind;
  left: Left;
  right: Right;
  left_key: LeftKey;
  right_key: RightKey;
  normalise?: Normalise;
  how?: How;
  add: Add;
}
/**
 * A column a Lookup or a Join brings across, optionally renamed.
 */
export interface AddedColumn {
  column: Column;
  as?: As;
}
