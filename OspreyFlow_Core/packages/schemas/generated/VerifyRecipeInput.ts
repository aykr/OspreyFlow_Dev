// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type ModelVersion = number | null;

/**
 * Optional body of `POST …/ingest/recipes/{id}/verify` (ADR-140 decision 5): the domain-model
 * version the Test runs against. Omitted, it is the dataset's live version. It may name the open
 * draft only for a reader with `edit_target_model` on the dataset; for anyone else the draft's
 * version is answered exactly as a version that does not exist (422, the same words), so a tester
 * learns nothing of an unpublished draft (rule 3).
 */
export interface VerifyRecipeInput {
  model_version?: ModelVersion;
  [k: string]: unknown;
}
