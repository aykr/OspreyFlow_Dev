// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and _pending_port_placeholders.py, via generate_ts.py
export type RowIndex = number;
export type ValuesMasked = boolean;
export type IsLastRow = boolean;

/**
 * One raw row from the same bounded sample Profile reads — §4's "the
 * template is always shown bound to a real row, and the analyst can page
 * through." Shape-masked exactly like `ColumnProfile.sample_values`
 * (`09_INGEST_STUDIO.md` §3's independent-minimums rule) when the
 * principal isn't cleared for the source's own handling marking.
 */
export interface MapSampleRow {
  row_index: RowIndex;
  values: Values;
  values_masked: ValuesMasked;
  is_last_row: IsLastRow;
  [k: string]: unknown;
}
export interface Values {
  [k: string]: string;
}
