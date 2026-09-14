// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py and _pending_port_placeholders.py, via generate_ts.py
export type RowIndex = number;
export type Reason = string;
export type Sample = string;

/**
 * One rejected row, grouped by cause in the load report — never a
 * silent coercion (`01_DOMAIN_MODEL.md` §7).
 */
export interface RejectionRecord {
  row_index: RowIndex;
  reason: Reason;
  sample: Sample;
  [k: string]: unknown;
}
