// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type DatasetId = string;
export type Name = string;
export type Added = boolean;

/**
 * A gazetteer a case's Author may add to the case, and whether it has (ADR-147 Amendment 2,
 * the owner's ruling 6): adding it copies its places into the case's own dataset, so the case
 * stays one dataset and keeps its loads. No count of places: a count would take in places above
 * the reader's clearance.
 */
export interface CaseGazetteer {
  dataset_id: DatasetId;
  name: Name;
  added: Added;
  [k: string]: unknown;
}
