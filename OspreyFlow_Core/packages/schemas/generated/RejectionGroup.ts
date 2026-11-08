// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type Reason = string;
export type Count = number;
export type RowIndex = number;
export type Reason1 = string;
export type Sample = string;
export type Table = string;
export type RowIndex1 = number;
export type LoadId = string | null;
export type Side = ("left" | "right") | null;
export type Refs = RejectionRef[];
export type Classification = string;
export type HandlingCode = string;
export type ActionCode = string | null;
export type SanitisationCode = string | null;
export type OrgUnitId = string;
export type ReviewDate = string | null;
export type LegalBasis = string | null;
export type SampleUnreadable = boolean;
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
  refs?: Refs;
  marking?: Handling | null;
  sample_unreadable?: SampleUnreadable;
  [k: string]: unknown;
}
/**
 * ADR-140 Amendment 12: a row a rejection came from, in a staged run. The table it is a row of
 * (a source's name, `reference_list:<name>@v<n>`, or a staged step's table), its row number, the
 * load that read it (a source row's; `None` for a list row or a staged table's row) and, for a
 * Join, the side. **No row key, raw or hashed** (rule 7;
 * `tests/schemas/test_staging_report_schemas.py`).
 */
export interface RejectionRef {
  table: Table;
  row_index: RowIndex1;
  load_id?: LoadId;
  side?: Side;
}
export interface Handling {
  classification: Classification;
  handling_code: HandlingCode;
  action_code?: ActionCode;
  sanitisation_code?: SanitisationCode;
  originator: OrgUnitId;
  owning_unit: OrgUnitId;
  review_date?: ReviewDate;
  legal_basis?: LegalBasis;
  [k: string]: unknown;
}
