// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type Id = string;
export type CaseId = string;
export type Name = string;
export type PrincipalId = string;
export type CreatedAt = string;
export type Shared = boolean;
export type Chosen = number | null;
export type EntityTypes = string[] | null;
export type ValidFrom = string | null;
export type ValidTo = string | null;
export type ValidFrom1 = string;
export type ValidTo1 = string | null;
export type Threshold = number | null;
export type Drawing = boolean;
export type ConvertedFromCase = string | null;

/**
 * A view as listed and answered (ADR-144 decisions 1 and 3). Private to `created_by` until
 * shared; deleted only by its creator; deleting it deletes nothing else.
 *
 * **What it never carries:** the chosen nodes' ids or their positions. Those are kept by the
 * Conduit alone (`services/api/case_views.py`'s stored view), because a shared view's selection is
 * its creator's, and naming an id the reader may not see would tell them it exists (rules 3
 * and 7). `chosen` counts the selection; opening the view (`CaseViewOpened`) gives the items and
 * positions the reader may see now.
 */
export interface CaseView {
  id: Id;
  case_id: CaseId;
  name: Name;
  created_by: PrincipalId;
  created_at: CreatedAt;
  shared?: Shared;
  chosen?: Chosen;
  filter?: ViewFilter | null;
  window?: Interval | null;
  threshold?: Threshold;
  drawing?: Drawing;
  converted_from_case?: ConvertedFromCase;
}
/**
 * What a filtered view keeps (ADR-124 decision 2's filter, ADR-144 decision 1): entity types,
 * a date window, or both. Applied to the reader's own projection of the case and nothing else.
 */
export interface ViewFilter {
  entity_types?: EntityTypes;
  valid_from?: ValidFrom;
  valid_to?: ValidTo;
}
export interface Interval {
  valid_from: ValidFrom1;
  valid_to?: ValidTo1;
  [k: string]: unknown;
}
