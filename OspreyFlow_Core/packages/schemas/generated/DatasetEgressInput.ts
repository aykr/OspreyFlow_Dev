// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type Egress = "none" | "contracted" | "any";

/**
 * `PUT /v1/admin/datasets/{dataset_id}/egress`: an administrator's change, audited.
 */
export interface DatasetEgressInput {
  egress: Egress;
  [k: string]: unknown;
}
