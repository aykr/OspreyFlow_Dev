// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type SourceId = string;
export type File = string | null;
export type Rows = number;
export type Cursor = string | null;
export type Words = string;

/**
 * One read of a non-file source (*Refresh now*, or its schedule): the rows it found and the
 * file of the dataset's folder they were written to, which the source's pipelines then run on;
 * or, when nothing new was found, no file, in words.
 */
export interface ConnectorRead {
  source_id: SourceId;
  file?: File;
  rows?: Rows;
  cursor?: Cursor;
  words: Words;
  [k: string]: unknown;
}
