// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type Kind = "s3";
export type Folder = string;
export type Format = "csv" | "parquet";

/**
 * The CSV or Parquet objects in a folder of the connection's bucket, and every folder under it,
 * read in key order. The folder is under the connection's own prefix (checked at the read).
 */
export interface S3Read {
  kind?: Kind;
  folder?: Folder;
  format?: Format;
}
