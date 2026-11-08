// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type DatasetId = string;
export type HasHomeCase = boolean;
export type Id = string;
export type Name = string | null;
export type Approves = boolean;
export type People = DatasetAuthor[];
export type Team = string | null;

/**
 * A dataset's Authors (ADR-145 Amendment 4 decision 3): its home case's Authors. Names and
 * accounts only, never the home case's contents.
 */
export interface AdminDatasetAuthors {
  dataset_id: DatasetId;
  has_home_case: HasHomeCase;
  people?: People;
  team?: Team;
  [k: string]: unknown;
}
/**
 * One of a dataset's Authors, as Admin › Datasets shows them: the account and its name.
 */
export interface DatasetAuthor {
  id: Id;
  name?: Name;
  approves?: Approves;
  [k: string]: unknown;
}
