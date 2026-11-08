// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type DatasetId = string;
export type InvestigationId = string;
export type Name = string;
export type State = "open" | "removed";
export type HomeCase = boolean;
export type Through = string | null;
export type Items = number;
export type Links = number;
export type SizeBytes = number;
export type Cases = AdminLinkedCase[];

export interface AdminDatasetCases {
  dataset_id: DatasetId;
  cases: Cases;
  [k: string]: unknown;
}
/**
 * One case linked to a dataset, as an administrator sees it (ADR-143 Amendment 2 decision 2):
 * its name, its state and its layer as counts. Never the layer's contents: no item, label or
 * property (rule 7). An open and a removed case carry exactly the same fields.
 */
export interface AdminLinkedCase {
  investigation_id: InvestigationId;
  name: Name;
  state: State;
  home_case?: HomeCase;
  through?: Through;
  items: Items;
  links: Links;
  size_bytes: SizeBytes;
}
