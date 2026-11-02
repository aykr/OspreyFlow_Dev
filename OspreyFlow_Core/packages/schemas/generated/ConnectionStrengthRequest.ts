// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type EdgeIds = string[] | null;

/**
 * `POST /v1/investigations/{id}/connection-strength`: the links to explain, or every link of
 * the working set the reader may see when none are named.
 */
export interface ConnectionStrengthRequest {
  edge_ids?: EdgeIds;
  [k: string]: unknown;
}
