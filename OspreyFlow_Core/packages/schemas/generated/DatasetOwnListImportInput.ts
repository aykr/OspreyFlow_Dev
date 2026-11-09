// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type Location = string;
export type Name = string | null;
export type KeyColumn = string | null;

/**
 * A dataset's own reference list's rows, imported from one of the dataset's own files (a CSV
 * with a header row). The list's record is the one the dataset's live domain model names.
 */
export interface DatasetOwnListImportInput {
  location: Location;
  name?: Name;
  key_column?: KeyColumn;
}
