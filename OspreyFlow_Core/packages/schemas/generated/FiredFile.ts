// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type Name = string;
export type Row = number | null;
export type Rows = number | null;
export type Records = number | null;

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
