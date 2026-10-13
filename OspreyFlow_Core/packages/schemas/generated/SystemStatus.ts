// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type Version = string | null;
export type Name = string;
export type Ok = boolean;
export type Millis = number;
export type Detail = string | null;
export type Components = ComponentHealth[];
export type Role = "extraction" | "vision" | "transcription" | "embedding";
export type Model = string;
export type RunsAt = string;
export type LocalModel = string | null;
export type Models = ModelRoleStatus[];
export type ModelNotice = string | null;
export type Current = string;
export type CheckedAt = string;
export type Latest = string | null;
export type UpdateAvailable = boolean;
export type Notes = string | null;
export type Url = string | null;
export type Problem = string | null;

/**
 * The Admin area's *System* screen (ADR-110 Amendment 1): each component, asked as the screen
 * opens — what the harness's preflight showed before launch, for a running deployment.
 */
export interface SystemStatus {
  version?: Version;
  components: Components;
  models?: Models;
  model_notice?: ModelNotice;
  update?: UpdateNotice | null;
  [k: string]: unknown;
}
/**
 * One part of the running deployment, asked just now: whether it answered, and how fast.
 */
export interface ComponentHealth {
  name: Name;
  ok: Ok;
  millis: Millis;
  detail?: Detail;
  [k: string]: unknown;
}
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
/**
 * The last `ospreyflow update --check` (ADR-114 Amendment 8 point 2), as it wrote it.
 */
export interface UpdateNotice {
  current: Current;
  checked_at: CheckedAt;
  latest: Latest;
  update_available: UpdateAvailable;
  notes: Notes;
  url: Url;
  problem: Problem;
  [k: string]: unknown;
}
