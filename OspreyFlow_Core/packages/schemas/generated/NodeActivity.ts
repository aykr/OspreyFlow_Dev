// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type RecentCount = number;
export type RecentTotal = number | null;
export type BaselineCount = number;
export type BaselineTotal = number | null;
export type FirstInWindow = string | null;
export type LastBeforeWindow = string | null;

/**
 * One subject's answer: counts and totals in the window and in the baseline before it; its
 * first movement in the window; its last before the window, however long before.
 */
export interface NodeActivity {
  recent_count: RecentCount;
  recent_total?: RecentTotal;
  baseline_count: BaselineCount;
  baseline_total?: BaselineTotal;
  first_in_window?: FirstInWindow;
  last_before_window?: LastBeforeWindow;
  [k: string]: unknown;
}
