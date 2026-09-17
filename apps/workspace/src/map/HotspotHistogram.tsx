// The "hotspot cells" filter panel — `08_ACCEPTANCE_SCENARIOS.md` A2/A3,
// `07_BUILD_PLAN.md` Phase 5 Checkpoint 2's "Filter panel wired for real
// onto the existing unwired Histogram.tsx" bullet.
//
// **Why this exists alongside the map's own geo_bins heat layer, not
// instead of it.** Manual verification against a live seeded HMP fixture
// found that `AnalyticsPort.geo_bins`'s precision ceiling (12 — enforced
// by `GeoBinRequest`'s own validator) cannot resolve individual grid
// cells at a single fixed site's scale: ten yards a few dozen metres
// apart collapsed into 2 bins even at maximum precision, nowhere near
// A2's "four hotspot cells". A *categorical* `cross_filter` dimension on
// `target_id` (the yard `Location` node each incident is `PRESENT_AT`)
// resolves per-cell exactly and reproduced the acceptance figure almost
// exactly (51.1% vs. the spec's ~52%) — `geo_bins` genuinely is the wrong
// tool for this scale; this panel is the real mechanism A2/A3 need. The
// heat layer stays, both because `02_GLASS_FRONTEND.md` §3.5 names it
// directly and because it remains correct at a coarser (city/region)
// scale this checkpoint's fixture doesn't happen to exercise.
import { useEffect, useState } from "react";

import type { Histogram as HistogramResult } from "../../../../packages/schemas/generated";
import { fetchCrossFilter } from "../analytics/api";
import { buildEventFilter, type CrossFilterStore } from "../crossfilter/store";
import { Histogram, type HistogramBucket as PanelBucket } from "../design/primitives/Histogram";

/** Pure — extracted so it is testable without a fetch mock or a mounted
 * component, matching this checkpoint's own "pure-function-first"
 * convention (`timeline/math.ts`). Ranked highest-count first; a bucket
 * with no `label` (shouldn't happen for `target_id`, defensive) is
 * dropped rather than rendered as an unclickable, unnamed bar. */
export function rankTargetIdBuckets(histogram: HistogramResult | undefined): PanelBucket[] {
  return (histogram?.buckets ?? [])
    .filter((b): b is typeof b & { label: string } => Boolean(b.label))
    .map((b) => ({ key: b.label, count: b.count, label: b.label }))
    .sort((a, b) => b.count - a.count);
}

export interface HotspotHistogramProps {
  apiBaseUrl: string;
  bearerToken: string;
  investigationScope: string;
  crossFilterStore: CrossFilterStore;
  /** Same "call only when something changes, never read reactively"
   * shape as `Timeline.tsx`'s own `getNodeIds` prop. */
  getNodeIds: () => readonly string[];
}

/** `target_id` is a whitelisted top-level field for `CATEGORICAL`
 * bucketing (`analytics_duckdb/adapter.py`'s `_TOP_LEVEL_FIELDS`) — the
 * same dimension `crossfilter/store.ts` itself already aggregates on to
 * compute the dimmed-id set, just surfaced here as a ranked, clickable
 * panel instead of only driving canvas dimming invisibly. */
const TARGET_ID_DIMENSION = {
  name: "target_id",
  bucketing: "categorical" as const,
  field: "target_id",
};

export function HotspotHistogram({
  apiBaseUrl,
  bearerToken,
  investigationScope,
  crossFilterStore,
  getNodeIds,
}: HotspotHistogramProps) {
  const [buckets, setBuckets] = useState<PanelBucket[]>([]);
  const [selectedKey, setSelectedKey] = useState<string | null>(null);

  // Reflects the timeline's active window (a *different* filter
  // dimension) but never its own prior selection — the same
  // self-exclusion `Timeline.tsx`'s own density strip applies to itself.
  useEffect(() => {
    let cancelled = false;
    async function refresh(window: ReturnType<CrossFilterStore["store"]["getState"]>["window"]) {
      const filter = buildEventFilter(investigationScope, window, null);
      const result = await fetchCrossFilter(apiBaseUrl, bearerToken, {
        filter,
        dimensions: [TARGET_ID_DIMENSION],
      });
      if (cancelled) return;
      setBuckets(rankTargetIdBuckets(result.target_id));
    }
    void refresh(crossFilterStore.store.getState().window);
    const unsubscribe = crossFilterStore.store.subscribe((state, prev) => {
      if (state.window === prev.window) return;
      void refresh(state.window);
    });
    return () => {
      cancelled = true;
      unsubscribe();
    };
  }, [apiBaseUrl, bearerToken, investigationScope, crossFilterStore]);

  return (
    <div style={{ height: "100%", display: "flex", flexDirection: "column" }}>
      <div
        style={{
          padding: "var(--sp-4) var(--sp-8)",
          fontSize: "var(--fs-12)",
          color: "var(--text-secondary)",
        }}
      >
        Hotspot cells
      </div>
      <div style={{ flex: 1, minHeight: 0 }}>
        <Histogram
          buckets={buckets}
          selectedKey={selectedKey}
          onSelect={(key) => {
            const next = selectedKey === key ? null : key;
            setSelectedKey(next);
            crossFilterStore.store.getState().setSelectedNodeIds(next ? [next] : null);
            void crossFilterStore.refresh(getNodeIds());
          }}
        />
      </div>
    </div>
  );
}
