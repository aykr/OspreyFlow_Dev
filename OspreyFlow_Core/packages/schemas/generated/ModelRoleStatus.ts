// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type Role = "extraction" | "vision" | "transcription" | "embedding";
export type Model = string;
export type RunsAt = string;
export type LocalModel = string | null;

/**
 * One model role and where it runs (ADR-114 decision 11, Amendment 6).
 */
export interface ModelRoleStatus {
  role: Role;
  model: Model;
  runs_at: RunsAt;
  local_model?: LocalModel;
  [k: string]: unknown;
}
