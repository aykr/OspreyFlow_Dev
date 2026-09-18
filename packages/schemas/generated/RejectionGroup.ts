// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and _pending_port_placeholders.py, via generate_ts.py
export type Reason = string;
export type Count = number;
export type RowIndex = number;
export type Reason1 = string;
export type Sample = string;
export type Samples = RejectionRecord[];

/**
 * §5: "The rejection report, grouped by cause with samples." `count`
 * is always the true total for this reason — `samples` is capped
 * (studio_verify.py), but the count itself never is, so a reason with
 * 400 rejections still reads as 400, not silently as however many
 * samples happened to ride along.
 */
export interface RejectionGroup {
  reason: Reason;
  count: Count;
  samples: Samples;
  [k: string]: unknown;
}
/**
 * One rejected row, grouped by cause in the load report — never a
 * silent coercion (`01_DOMAIN_MODEL.md` §7).
 */
export interface RejectionRecord {
  row_index: RowIndex;
  reason: Reason1;
  sample: Sample;
  [k: string]: unknown;
}
