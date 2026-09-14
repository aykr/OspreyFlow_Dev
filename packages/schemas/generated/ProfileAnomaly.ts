// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py and _pending_port_placeholders.py, via generate_ts.py
/**
 * `09_INGEST_STUDIO.md` §3: "The profile also flags what will hurt
 * later." `ENCODING_NOT_UTF8` is deliberately absent — detecting it
 * needs the raw bytes a connector decoded, not the already-decoded rows
 * this profiler receives; it belongs to the connector layer, not here
 * (`services/ingest/profiler.py`'s module docstring records this as a
 * stated gap, not a silent omission).
 */
export type AnomalyKind = "ragged_row" | "duplicate_row" | "mixed_datetime_formats" | "undetermined_timezone";
export type Column = string | null;
export type Count = number;
export type Sample = string;

export interface ProfileAnomaly {
  kind: AnomalyKind;
  column?: Column;
  count: Count;
  sample: Sample;
  [k: string]: unknown;
}
