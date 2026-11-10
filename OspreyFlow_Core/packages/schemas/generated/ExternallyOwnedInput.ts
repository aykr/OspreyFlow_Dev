// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type ClientId = string;

/**
 * *Owned externally* (decision 11): the one service identity that may trigger the pipeline
 * (ADR-141 open question 1, taken per pipeline: the strict option), and the version it runs.
 */
export interface ExternallyOwnedInput {
  client_id: ClientId;
}
