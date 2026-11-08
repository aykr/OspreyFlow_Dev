// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type Id = string;
export type CaseId = string;
export type Name = string;
export type PrincipalId = string;
export type CreatedAt = string;
export type Shared = boolean;
export type NodeIds = NodeId[] | null;
export type NodeId = string;
export type EntityTypes = string[] | null;
export type ValidFrom = string | null;
export type ValidTo = string | null;
export type X = number;
export type Y = number;
export type ValidFrom1 = string;
export type ValidTo1 = string | null;
export type Threshold = number | null;
export type Drawing = boolean;
export type ConvertedFromCase = string | null;

/**
 * A view as stored and listed (ADR-144 decisions 1 and 3). Private to `created_by` until
 * shared; deleted only by its creator; deleting it deletes nothing else.
 */
export interface CaseView {
  id: Id;
  case_id: CaseId;
  name: Name;
  created_by: PrincipalId;
  created_at: CreatedAt;
  shared?: Shared;
  node_ids?: NodeIds;
  filter?: ViewFilter | null;
  layout?: Layout;
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
export interface Layout {
  [k: string]: NodePosition;
}
/**
 * Where a node sits on the view's canvas.
 */
export interface NodePosition {
  x: X;
  y: Y;
}
export interface Interval {
  valid_from: ValidFrom1;
  valid_to?: ValidTo1;
  [k: string]: unknown;
}
