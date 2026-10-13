// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type Current = string;
export type CheckedAt = string;
export type Latest = string | null;
export type UpdateAvailable = boolean;
export type Notes = string | null;
export type Url = string | null;
export type Problem = string | null;

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
