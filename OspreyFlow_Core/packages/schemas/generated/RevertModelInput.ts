// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type Version = number;

/**
 * `POST /v1/datasets/{dataset_id}/model/revert`: the earlier version to copy into a new draft
 * (N+2, never a rewrite of it).
 */
export interface RevertModelInput {
  version: Version;
}
