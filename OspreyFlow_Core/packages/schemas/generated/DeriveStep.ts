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
export type Settings =
  | ConcatSettings
  | SplitSettings
  | SubstringSettings
  | DateParseSettings
  | ArithmeticSettings
  | CaseWhenSettings
  | NormaliseSettings;
export type Separator = string;
export type Delimiter = string;
export type Part = number;
export type Start = number;
export type Length = number | null;
export type DateOrder = ("dmy" | "mdy") | null;
export type Tz = string | null;
export type Op = "add" | "subtract" | "multiply" | "divide";
export type Constant = string | null;
/**
 * @minItems 1
 */
export type Cases = [CaseWhenCase, ...CaseWhenCase[]];
export type Equals = string;
export type Then = string;
export type Otherwise = string | null;
export type Adapter = string;

/**
 * A new column from a catalogued operation over named columns (brief §6). `settings` are the
 * operation's own declared settings, typed per operation (a separator, a part, a time zone…):
 * data and never code, and a key the operation does not read is refused, as is a wrong number
 * of columns.
 */
export interface DeriveStep {
  id: Id;
  label?: Label;
  kind: Kind;
  input: Input;
  column: Column;
  operation: Operation;
  columns: Columns;
  settings: Settings;
}
export interface ConcatSettings {
  separator?: Separator;
}
export interface SplitSettings {
  delimiter?: Delimiter;
  part?: Part;
}
export interface SubstringSettings {
  start?: Start;
  length?: Length;
}
export interface DateParseSettings {
  date_order?: DateOrder;
  tz?: Tz;
}
export interface ArithmeticSettings {
  op: Op;
  constant?: Constant;
}
export interface CaseWhenSettings {
  cases: Cases;
  otherwise?: Otherwise;
}
export interface CaseWhenCase {
  equals: Equals;
  then: Then;
}
export interface NormaliseSettings {
  adapter: Adapter;
}
