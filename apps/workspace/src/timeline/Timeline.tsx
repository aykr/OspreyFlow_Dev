// The timeline — `docs/02_GLASS_FRONTEND.md` §3.4,
// `08_ACCEPTANCE_SCENARIOS.md` A4/A5/A11. Density strip (bucketed event
// counts) with a drag-to-select brush, plus a cyclical weekday×hour mode —
// the two temporal modes this checkpoint's acceptance scenarios actually
// exercise. Playback, multi-track and cross-case overlay are named in §3.4
// too but exercised by no A1-A11 step; deferred, not built here
// (`07_BUILD_PLAN.md` Phase 5 Checkpoint 2 plan, "Deferred past this
// phase").
//
// ECharts, used imperatively via a ref/instance — the same pattern this
// codebase already uses for Sigma (`canvas/GlassCanvas.tsx`) and MapLibre
// (`map/MapView.tsx`), not a declarative React wrapper. Imported through
// `echarts/core` with only the pieces this component uses registered, not
// the full bundle.
import * as echarts from "echarts/core";
import { BarChart, HeatmapChart } from "echarts/charts";
import {
  DataZoomComponent,
  GridComponent,
  TooltipComponent,
  VisualMapComponent,
} from "echarts/components";
import { CanvasRenderer } from "echarts/renderers";
import { useEffect, useRef, useState } from "react";

import type {
  Histogram,
  HistogramRequest,
} from "../../../../packages/schemas/generated";
import { fetchHistogram } from "../analytics/api";
import {
  BORDER_SUBTLE_DARK_HEX,
  BRASS_HEX,
  SEQ_HEX,
  TEXT_SECONDARY_DARK_HEX,
} from "../color/tokens";
import { buildEventFilter, type CrossFilterStore } from "../crossfilter/store";
import { Button } from "../design/primitives/Button";
import { windowFromZoomPercent } from "./math";

echarts.use([
  BarChart,
  HeatmapChart,
  DataZoomComponent,
  GridComponent,
  TooltipComponent,
  VisualMapComponent,
  CanvasRenderer,
]);

const WEEKDAY_LABELS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
const HOUR_LABELS = Array.from({ length: 24 }, (_, h) => String(h));

// `AnalyticsPort.histogram`'s `interval_seconds` has no "size this to the
// window" mode yet — `02_GLASS_FRONTEND.md` §3.4's own "bucketed
// automatically to the window" is a fuller feature than A3-A11 needs. A
// fixed daily bucket is this checkpoint's deliberate scope reduction,
// flagged rather than silently assumed.
const DAILY_INTERVAL_SECONDS = 24 * 60 * 60;

type TimelineMode = "density" | "cyclical";

export interface TimelineProps {
  apiBaseUrl: string;
  bearerToken: string;
  investigationScope: string;
  crossFilterStore: CrossFilterStore;
  /** Called only when the brush changes or the filter is cleared — never
   * read reactively, so a fresh array on every `App` render never forces
   * this component to redo anything (the `EMPTY_NODE_COORDINATES`/
   * `EMPTY_DIMMED_SET` stable-reference lesson, applied to a callback
   * instead of a value here since a working set's node ids have no single
   * stable snapshot to hold onto). */
  getNodeIds: () => readonly string[];
}

export function Timeline({
  apiBaseUrl,
  bearerToken,
  investigationScope,
  crossFilterStore,
  getNodeIds,
}: TimelineProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<echarts.ECharts | null>(null);
  const [mode, setMode] = useState<TimelineMode>("density");
  const [histogram, setHistogram] = useState<Histogram | null>(null);
  const [selectedNodeIds, setSelectedNodeIds] = useState<string[] | null>(
    crossFilterStore.store.getState().selectedNodeIds,
  );
  const [activeWindow, setActiveWindow] = useState(
    crossFilterStore.store.getState().window,
  );

  useEffect(
    () =>
      crossFilterStore.store.subscribe((state) => {
        setSelectedNodeIds(state.selectedNodeIds);
        setActiveWindow(state.window);
      }),
    [crossFilterStore],
  );

  // The density strip and cyclical view always show the *full* time range
  // regardless of the timeline's own active brush window — only the
  // node-id restriction (from a canvas/histogram/map-cell selection)
  // narrows what they draw. Filtering the strip by its own brush would
  // hide the un-brushed portion, defeating its exploratory purpose
  // (`02_GLASS_FRONTEND.md` §3.4's "drag to select a window" implies
  // dragging across a strip that already shows everything).
  useEffect(() => {
    const filter = buildEventFilter(investigationScope, null, selectedNodeIds);
    const request: HistogramRequest =
      mode === "density"
        ? {
            filter,
            bucketing: "fixed_interval",
            interval_seconds: DAILY_INTERVAL_SECONDS,
          }
        : { filter, bucketing: "weekday_hour" };
    let cancelled = false;
    void fetchHistogram(apiBaseUrl, bearerToken, request).then((result) => {
      if (!cancelled) setHistogram(result);
    });
    return () => {
      cancelled = true;
    };
  }, [apiBaseUrl, bearerToken, investigationScope, selectedNodeIds, mode]);

  useEffect(() => {
    if (!containerRef.current) return;
    const chart = echarts.init(containerRef.current);
    chartRef.current = chart;
    return () => {
      chart.dispose();
      chartRef.current = null;
    };
  }, []);

  useEffect(() => {
    const chart = chartRef.current;
    if (!chart || !histogram) return;

    if (mode === "density") {
      const buckets = histogram.buckets;
      chart.off("datazoom");
      chart.setOption(
        {
          backgroundColor: "transparent",
          grid: { left: 8, right: 8, top: 8, bottom: 40, containLabel: true },
          xAxis: {
            type: "category",
            data: buckets.map((b) => (b.start ?? "").slice(0, 10)),
            axisLine: { lineStyle: { color: BORDER_SUBTLE_DARK_HEX } },
            axisLabel: { color: TEXT_SECONDARY_DARK_HEX, fontSize: 11 },
          },
          yAxis: {
            type: "value",
            axisLine: { lineStyle: { color: BORDER_SUBTLE_DARK_HEX } },
            axisLabel: { color: TEXT_SECONDARY_DARK_HEX, fontSize: 11 },
            splitLine: { lineStyle: { color: BORDER_SUBTLE_DARK_HEX } },
          },
          dataZoom: [
            { type: "slider", height: 20, bottom: 4 },
            { type: "inside" },
          ],
          series: [
            {
              type: "bar",
              data: buckets.map((b) => b.count),
              itemStyle: { color: BRASS_HEX },
              barMinWidth: 1,
            },
          ],
          tooltip: { trigger: "axis" },
        },
        true,
      );

      // Reading the range back off `getOption()` after the event, as a
      // start/end *percentage* pair, sidesteps whether ECharts reports a
      // category axis's own dataZoom range as indices or as matching data
      // values (it is not consistent between the two) — a percentage is
      // unambiguous regardless of axis type. `windowFromZoomPercent`
      // (`./math.ts`) does the actual (tested) conversion.
      chart.on("datazoom", () => {
        const option = chart.getOption() as {
          dataZoom?: Array<{ start?: number; end?: number }>;
        };
        const zoom = option.dataZoom?.[0];
        if (zoom?.start == null || zoom.end == null) return;
        const window = windowFromZoomPercent(buckets, zoom.start, zoom.end);
        if (!window) return;
        crossFilterStore.store.getState().setWindow(window);
        void crossFilterStore.refresh(getNodeIds());
      });
    } else {
      const buckets = histogram.buckets;
      const data = buckets.map((b) => [b.hour ?? 0, b.weekday ?? 0, b.count]);
      const max = Math.max(1, ...buckets.map((b) => b.count));
      chart.setOption(
        {
          backgroundColor: "transparent",
          grid: { left: 48, right: 16, top: 8, bottom: 24, containLabel: true },
          xAxis: {
            type: "category",
            data: HOUR_LABELS,
            axisLabel: { color: TEXT_SECONDARY_DARK_HEX, fontSize: 11 },
            splitArea: { show: true },
          },
          yAxis: {
            type: "category",
            data: WEEKDAY_LABELS,
            axisLabel: { color: TEXT_SECONDARY_DARK_HEX, fontSize: 11 },
            splitArea: { show: true },
          },
          visualMap: {
            min: 0,
            max,
            calculable: true,
            orient: "horizontal",
            left: "center",
            bottom: 0,
            inRange: { color: SEQ_HEX },
            textStyle: { color: TEXT_SECONDARY_DARK_HEX },
          },
          series: [{ type: "heatmap", data, label: { show: false } }],
          tooltip: {},
        },
        true,
      );
    }
  }, [histogram, mode, crossFilterStore, getNodeIds]);

  useEffect(() => {
    function handleResize() {
      chartRef.current?.resize();
    }
    globalThis.addEventListener("resize", handleResize);
    return () => globalThis.removeEventListener("resize", handleResize);
  }, []);

  function commitWindowInput(field: "validFrom" | "validTo", value: string) {
    const next = {
      validFrom: activeWindow?.validFrom ?? "",
      validTo: activeWindow?.validTo ?? null,
    };
    if (field === "validFrom") next.validFrom = value;
    else next.validTo = value || null;
    if (!next.validFrom) return;
    crossFilterStore.store.getState().setWindow(next);
    void crossFilterStore.refresh(getNodeIds());
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100%" }}>
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: "var(--sp-8)",
          padding: "var(--sp-4) var(--sp-8)",
        }}
      >
        <Button aria-pressed={mode === "density"} onClick={() => setMode("density")}>
          Density
        </Button>
        <Button aria-pressed={mode === "cyclical"} onClick={() => setMode("cyclical")}>
          Cyclical
        </Button>
        {mode === "density" && (
          <>
            {/* `02_GLASS_FRONTEND.md` §3.4: "Brush endpoints are editable
                as text." Editing a field updates the active filter
                immediately; the slider's own handles move on the next
                histogram refetch rather than live-tracking a keystroke. */}
            <input
              type="text"
              aria-label="Brush window start"
              placeholder="from (ISO)"
              defaultValue={activeWindow?.validFrom ?? ""}
              onBlur={(e) => commitWindowInput("validFrom", e.target.value)}
              style={{ width: 180 }}
            />
            <input
              type="text"
              aria-label="Brush window end"
              placeholder="to (ISO)"
              defaultValue={activeWindow?.validTo ?? ""}
              onBlur={(e) => commitWindowInput("validTo", e.target.value)}
              style={{ width: 180 }}
            />
          </>
        )}
        {(activeWindow || selectedNodeIds) && (
          <Button
            onClick={() => {
              crossFilterStore.store.getState().clearFilter();
              void crossFilterStore.refresh(getNodeIds());
            }}
          >
            Clear filter
          </Button>
        )}
      </div>
      <div ref={containerRef} style={{ flex: 1, minHeight: 0 }} />
    </div>
  );
}
