// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type DatasetId = string;
export type InvestigationId = string;
export type Name = string;
export type Items = number;
export type Mergeable = boolean;
export type WhyNot = string | null;
export type Cases = RemovedCaseLayer[];

export interface RemovedCaseLayers {
  dataset_id: DatasetId;
  cases: Cases;
}
/**
 * A removed case reading the dataset, as its Authors see it in the Studio: counts only.
 */
export interface RemovedCaseLayer {
  investigation_id: InvestigationId;
  name: Name;
  items: Items;
  mergeable: Mergeable;
  why_not?: WhyNot;
}
