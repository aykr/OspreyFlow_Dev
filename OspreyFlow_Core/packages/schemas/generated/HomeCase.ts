// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type DatasetId = string;
export type InvestigationId = string;
export type MadeAt = string;
export type PrincipalId = string;

/**
 * A dataset's home case (ADR-145 Amendment 4 decision 2): holds its reports, its dataset-wide
 * alerts and its promotion reviews; cannot be removed while the dataset exists. Every source,
 * composite and drawn dataset has one; an analyst layer never does.
 */
export interface HomeCase {
  dataset_id: DatasetId;
  investigation_id: InvestigationId;
  made_at: MadeAt;
  made_by: PrincipalId;
}
