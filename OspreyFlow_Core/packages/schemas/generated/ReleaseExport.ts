// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type LeftOut = number;

/**
 * *Export*'s answer: the bundle's files as text by path, and how many published pipelines
 * were left out, being marked above the exporter's view (rule 2: said, never silent).
 */
export interface ReleaseExport {
  files: Files;
  left_out?: LeftOut;
}
export interface Files {
  [k: string]: string;
}
