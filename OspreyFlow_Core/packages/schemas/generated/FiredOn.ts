// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type Type = string;
export type Label = string;
export type Name = string;
export type Row = number | null;
export type Rows = number | null;
export type Records = number | null;
export type Files = FiredFile[];
export type MoreFiles = number;
export type SourcesWithheld = boolean;

/**
 * ADR-130 decision 1: what a matched node is, and where it was read from. `files` are in the
 * order of first appearance, at most five; `more_files` counts the rest.
 *
 * ADR-130 Amendment 1: when the node belongs to a dataset the reader's case does not read, its
 * sources are not said at all: `sources_withheld` is true, `files` is empty and `more_files` 0.
 */
export interface FiredOn {
  type: Type;
  label: Label;
  files: Files;
  more_files: MoreFiles;
  sources_withheld?: SourcesWithheld;
  [k: string]: unknown;
}
/**
 * One source file of a matched node: its name (the final path segment of the document id; two
 * loads' `calls.csv` are two entries), and what is cited in it. `row` is the single row (its
 * offset under the header, counted from 0; the Glass shows it counted from 1, ADR-131) when
 * exactly one `row N` is cited and nothing else; otherwise `rows` counts the distinct `row N`
 * locators and `records` the distinct locators of any other form (ADR-130 Amendment 1).
 */
export interface FiredFile {
  name: Name;
  row?: Row;
  rows?: Rows;
  records?: Records;
  [k: string]: unknown;
}
