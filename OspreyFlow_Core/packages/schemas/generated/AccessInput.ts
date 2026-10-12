// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type Clearance = string;
export type OrgUnit = string;
export type ReceivableHandlingCodes = string[];

/**
 * What a person may see (ADR-114 Amendment 5): clearance, unit and the handling codes they may
 * receive — none above the administrator's own.
 */
export interface AccessInput {
  clearance: Clearance;
  org_unit: OrgUnit;
  receivable_handling_codes?: ReceivableHandlingCodes;
  [k: string]: unknown;
}
