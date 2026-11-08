// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type Name = string;
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

/**
 * *Save what I see as a view* (ADR-144 decision 4): a name and exactly one of a node selection
 * or a filter, with the layout, timeline range and threshold the reader had.
 */
export interface CaseViewInput {
  name: Name;
  node_ids?: NodeIds;
  filter?: ViewFilter | null;
  layout?: Layout;
  window?: Interval | null;
  threshold?: Threshold;
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
