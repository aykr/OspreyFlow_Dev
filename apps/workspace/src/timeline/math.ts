// Pure math extracted out of `Timeline.tsx` so it is testable without an
// ECharts/canvas instance — the "pure-function-first" half of this
// checkpoint's own test plan.
import type { HistogramBucket } from "../../../../packages/schemas/generated";
import type { TimeWindow } from "../crossfilter/store";

/**
 * Converts an ECharts `dataZoom` start/end *percentage* pair (0-100) into
 * the `TimeWindow` those buckets cover. A percentage sidesteps whether
 * ECharts reports a category axis's own zoom range as indices or as
 * matching data values (`Timeline.tsx`'s own comment on `chart.on
 * ("datazoom", ...)`) — this function receives only the unambiguous form.
 *
 * Returns `null` when there's nothing to compute a window from — no
 * buckets, or a bucket at the resolved index missing its own
 * `start`/`end` (a `weekday_hour` bucket has neither; this should never be
 * called against one, but a defensive `null` beats a bad window silently
 * reaching the store).
 */
export function windowFromZoomPercent(
  buckets: readonly HistogramBucket[],
  startPercent: number,
  endPercent: number,
): TimeWindow | null {
  if (buckets.length === 0) return null;
  const startIndex = Math.round((startPercent / 100) * (buckets.length - 1));
  const endIndex = Math.round((endPercent / 100) * (buckets.length - 1));
  const start = buckets[Math.min(startIndex, endIndex)];
  const end = buckets[Math.max(startIndex, endIndex)];
  if (!start?.start || !end?.end) return null;
  return { validFrom: start.start, validTo: end.end };
}
