// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and _pending_port_placeholders.py, via generate_ts.py
export type PrincipalId = string;
export type Clearance = string;
export type OrgUnitId = string;
export type ReceivableHandlingCodes = string[];
export type Roles = string[];

/**
 * Resolved by the Conduit from the session token and passed into every
 * `GraphPort` read. Two axes gate visibility (`01_DOMAIN_MODEL.md` §2.2):
 * `clearance` is a classification value from the deployment's active
 * handling scheme (`Handling.classification`), dominance-ordered;
 * `receivable_handling_codes` is the set of `Handling.handling_code`
 * values this principal may receive at all — checked only for a
 * `handling_code` whose scheme entry is `dissemination: restricted`, and
 * then also scoped to `org_unit` matching the record's `owning_unit` or
 * `originator`. `action_code` and `sanitisation_code` never gate a read —
 * the first constrains what may be *done*, the second is the export
 * gate's reason for existing.
 */
export interface Principal {
  id: PrincipalId;
  clearance: Clearance;
  org_unit: OrgUnitId;
  receivable_handling_codes?: ReceivableHandlingCodes;
  roles?: Roles;
  [k: string]: unknown;
}
