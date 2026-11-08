// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type Id = string;
export type Name = string | null;
export type Approves = boolean;

/**
 * One of a dataset's Authors, as Admin › Datasets shows them: the account and its name.
 */
export interface DatasetAuthor {
  id: Id;
  name?: Name;
  approves?: Approves;
  [k: string]: unknown;
}
