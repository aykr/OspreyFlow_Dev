// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type SourceId = string;
export type Column = string;
export type Kind = "number" | "time" | "text";
export type Value = string;

/**
 * The highest value of an incremental source's watermark column a run read (ADR-110 Amendment
 * 6 point 1), kept with the load's record: the next refresh of the source, by the same pipeline
 * into the same case, reads only rows past it. `value` is the value as the file held it;
 * `kind` says how it compares (as a number, as an instant, or as text). For the ledger alone: a
 * value of the loader's own source, never in a route's answer.
 */
export interface SourceWatermark {
  source_id: SourceId;
  column: Column;
  kind: Kind;
  value: Value;
  [k: string]: unknown;
}
