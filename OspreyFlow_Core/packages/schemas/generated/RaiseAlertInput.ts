// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type Title = string;
export type Severity = "low" | "medium" | "high";
export type Reason = string;
export type To = "case" | "dataset";
export type DatasetId = string | null;
/**
 * @minItems 1
 * @maxItems 200
 */
export type NodeIds = [NodeId, ...NodeId[]];
export type NodeId = string;
export type EdgeId = string;
/**
 * @maxItems 400
 */
export type EdgeIds = EdgeId[];
export type FoundBy = string | null;

/**
 * *Raise an alert…* (ADR-146 decision 7, R4): a title, a severity, a reason and where it goes,
 * with its evidence: the items and the query or question that found them. Refused at the route to
 * a case or dataset the raiser may not write, and a dataset alert citing an item that is not the
 * dataset's own (a drawn item, which only its case can see).
 */
export interface RaiseAlertInput {
  title: Title;
  severity?: Severity;
  reason: Reason;
  to?: To;
  dataset_id?: DatasetId;
  node_ids: NodeIds;
  edge_ids?: EdgeIds;
  found_by?: FoundBy;
  [k: string]: unknown;
}
