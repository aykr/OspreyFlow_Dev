// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type Id = string;
export type Label = string | null;
export type Kind = "fuzzy_match";
export type Left = string;
export type Right = string;
/**
 * @minItems 1
 */
export type Compare = [FuzzyComparison, ...FuzzyComparison[]];
export type Left1 = string;
export type Right1 = string;
export type Method = "exact" | "jaro_winkler" | "levenshtein";
export type Left2 = string;
export type Right2 = string;
export type Method1 = "exact" | "soundex" | "year";
export type BlockOn = FuzzyBlocking[];
export type Threshold = number;
/**
 * @minItems 1
 */
export type Add = [AddedColumn, ...AddedColumn[]];
export type Column = string;
export type As = string | null;
export type Left3 = string;
export type Right3 = string;

/**
 * Expert mode (ADR-140 decision 13; ADR-006 Amendment 1; R5, R13): each row of `left` kept,
 * with the columns `add` names from its best-scoring row of `right` and that row's score as
 * `match_score`, when the score is at least `threshold`; a row below it is kept with those cells
 * empty, and counted. The threshold is part of the pipeline's version. What Map writes from a
 * matched column is `inferred` with the score, and the match itself is the `SAME_AS` that
 * `same_as` names, inferred until a person confirms it. It is the last step: Map reads it.
 */
export interface FuzzyMatchStep {
  id: Id;
  label?: Label;
  kind: Kind;
  left: Left;
  right: Right;
  compare: Compare;
  block_on?: BlockOn;
  threshold: Threshold;
  add: Add;
  same_as: FuzzySameAs;
}
/**
 * One comparison: a column of the left table against a column of the right, by a method.
 */
export interface FuzzyComparison {
  left: Left1;
  right: Right1;
  method: Method;
}
/**
 * Only pairs agreeing on this key are compared (as the ontology's `resolution.blocking`).
 */
export interface FuzzyBlocking {
  left: Left2;
  right: Right2;
  method?: Method1;
}
/**
 * A column a Lookup or a Join brings across, optionally renamed.
 */
export interface AddedColumn {
  column: Column;
  as?: As;
}
/**
 * The two elements of Map's row template the match says may be one: `left`, written from the
 * left table's columns, and `right`, from the matched columns. The engine writes a scored
 * `SAME_AS` between them marked `inferred`, never a merge (ADR-006 Amendment 1; rules 5 and 6).
 */
export interface FuzzySameAs {
  left: Left3;
  right: Right3;
}
