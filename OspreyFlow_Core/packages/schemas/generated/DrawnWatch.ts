// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type Id = string;
export type ItemId = string;
export type ElementId = string;
export type CaseId = string;
export type DatasetId = string | null;
export type PrincipalId = string;
export type CreatedAt = string;
export type EndedAt = string | null;
export type Kind = "drawn_watch";

/**
 * Amendment 2 decision 8: drawing an item sets a watch for it on the case's dataset, owned by
 * the item's author; withdrawing the item ends it. Its alerts' queue is L3.6's, with L2.10.
 */
export interface DrawnWatch {
  id: Id;
  item_id: ItemId;
  element_id: ElementId;
  case_id: CaseId;
  dataset_id: DatasetId;
  owner: PrincipalId;
  created_at: CreatedAt;
  ended_at?: EndedAt;
  kind?: Kind;
  [k: string]: unknown;
}
