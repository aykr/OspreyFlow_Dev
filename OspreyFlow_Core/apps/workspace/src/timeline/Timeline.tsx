// The timeline — `spec/02_GLASS_FRONTEND.md` §3.4,
// `08_ACCEPTANCE_SCENARIOS.md` A4/A5/A11/B16/B18. Density strip (bucketed
// event counts) with a drag-to-select brush, plus a cyclical weekday×hour
// mode — the two temporal modes the A1-A11 acceptance scenario
// exercised, built there.
//
// Playback and the cross-case overlay are built here
// (a "small,
// incremental additions" characterisation was checked against this file's
// own then-current state and did not hold; both were real, from-scratch
// work, not a small addition). Multi-track mode (§3.4's own "one row per
// selected entity") is *not* built here — B16's own cross-case overlay
// needed only a second investigation's own track against a shared axis,
// which this file's own two-grid layout below satisfies without needing
// the more general per-entity multi-track mode; that remains its own,
// separately-scoped, disclosed gap.
//
// ECharts, used imperatively via a ref/instance — the same pattern this
// codebase already uses for Sigma (`canvas/GlassCanvas.tsx`) and MapLibre
// (`map/MapView.tsx`), not a declarative React wrapper. Imported through
// `echarts/core` with only the pieces this component uses registered, not
// the full bundle.
import * as echarts from "echarts/core";
import { BarChart, HeatmapChart } from "echarts/charts";
import {
  BrushComponent,
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
import { activePalette } from "../color/palette";
import { currentTheme, onThemeChange, type Theme } from "../theme/theme";
import { buildEventFilter, type CrossFilterStore } from "../crossfilter/store";
import { Button } from "../design/primitives/Button";
import { Select } from "../design/primitives/Select";
import { PLAYBACK_SPEEDS, usePlayback } from "../playback/usePlayback";
import { allOnOneDay, bucketLabel, bucketRangeOfWindow, windowFromBucketRange } from "./math";

echarts.use([
  BarChart,
  BrushComponent,
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
/** A case whose dated events all fall on one day is drawn by the hour (ADR-097 step 3). */
const HOURLY_INTERVAL_SECONDS = 60 * 60;
/** `--mono`, mirrored for the chart's canvas: tick values are literal numbers and dates. */
const MONO_FONT = "'IBM Plex Mono', ui-monospace, monospace";

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
  /** The links in the view, so a brush can dim a link with no event in the window (ADR-087). */
  getEdgeIds?: () => readonly string[];
  /** B16's own cross-case overlay (`08_ACCEPTANCE_SCENARIOS.md`) — a second
   * investigation's own `investigation_scope` to fetch and render as a
   * second track sharing this component's own time axis. `undefined`
   * renders the single-track view unchanged, the same optional-prop shape
   * `geoBins`/`onMapReady` already use elsewhere in this codebase for a
   * feature not every caller wants mounted. */
  crossCaseInvestigationScope?: string;
  /** B18's own playback clock, surfaced here since the timeline is where
   * `02_GLASS_FRONTEND.md` §3.4 places play/pause/speed — a sibling
   * surface (the map's own snail trail) reads the same `fraction` this
   * callback reports, so both animate off one clock, never two that could
   * drift apart. Called on every animation frame while playing; a caller
   * that doesn't need playback (no snail trail mounted) simply omits it. */
  onPlaybackFractionChange?: (fraction: number) => void;
  /** Called as the analyst types the id of a second investigation to overlay. When given, the
   * timeline's own bar offers an `Overlay another case` button that reveals the box (it was a
   * separate row above the timeline that was always showing). */
  onCrossCaseScopeChange?: (investigationId: string) => void;
}

export function Timeline({
  apiBaseUrl,
  bearerToken,
  investigationScope,
  crossFilterStore,
  getNodeIds,
  getEdgeIds,
  crossCaseInvestigationScope,
  onPlaybackFractionChange,
  onCrossCaseScopeChange,
}: TimelineProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<echarts.ECharts | null>(null);
  const [mode, setMode] = useState<TimelineMode>("density");
  // The two boxes for typing exact dates, and the box for a second investigation's id, are tucked
  // behind a button each: they are rarely used and sat in the bar all the time.
  const [datesOpen, setDatesOpen] = useState(false);
  const [overlayOpen, setOverlayOpen] = useState(false);
  const [histogram, setHistogram] = useState<Histogram | null>(null);
  const [bucketSeconds, setBucketSeconds] = useState(DAILY_INTERVAL_SECONDS);
  const [moreOpen, setMoreOpen] = useState(false);
  // `null` until the first answer: the strip is not declared empty before it has been asked.
  const hasEvents = histogram === null || histogram.total > 0;
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

  // B18's own playback clock — driven off the active brush window, since
  // "animate the brush forward" (`02_GLASS_FRONTEND.md` §3.4) has nothing
  // to animate across without one set.
  const playback = usePlayback(activeWindow);
  useEffect(() => {
    onPlaybackFractionChange?.(playback.fraction);
  }, [playback.fraction, onPlaybackFractionChange]);

  // B16's own cross-case overlay — a second investigation's own histogram,
  // fetched with the *same* filter shape as the primary track (no node-id
  // restriction; `02_GLASS_FRONTEND.md` §3.4's own "events from a second
  // investigation on a distinct track" names no cross-filter narrowing for
  // the overlay itself) so the two tracks' own bucket boundaries line up
  // exactly on the shared axis below.
  const [crossCaseHistogram, setCrossCaseHistogram] =
    useState<Histogram | null>(null);
  useEffect(() => {
    if (!crossCaseInvestigationScope) {
      setCrossCaseHistogram(null);
      return;
    }
    const request: HistogramRequest = {
      filter: buildEventFilter(crossCaseInvestigationScope, null, null),
      bucketing: "fixed_interval",
      interval_seconds: DAILY_INTERVAL_SECONDS,
    };
    let cancelled = false;
    void fetchHistogram(apiBaseUrl, bearerToken, request).then((result) => {
      if (!cancelled) setCrossCaseHistogram(result);
    });
    return () => {
      cancelled = true;
    };
  }, [apiBaseUrl, bearerToken, crossCaseInvestigationScope]);

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
    void (async () => {
      const daily = await fetchHistogram(apiBaseUrl, bearerToken, request);
      // One day of events reads as one bar: ask again by the hour (not with an overlay, whose daily
      // buckets must line up with these).
      if (mode === "density" && !crossCaseInvestigationScope && allOnOneDay(daily.buckets)) {
        const hourly = await fetchHistogram(apiBaseUrl, bearerToken, {
          ...request,
          interval_seconds: HOURLY_INTERVAL_SECONDS,
        });
        if (cancelled) return;
        setBucketSeconds(HOURLY_INTERVAL_SECONDS);
        setHistogram(hourly);
        return;
      }
      if (cancelled) return;
      setBucketSeconds(DAILY_INTERVAL_SECONDS);
      setHistogram(daily);
    })();
    return () => {
      cancelled = true;
    };
  }, [apiBaseUrl, bearerToken, investigationScope, selectedNodeIds, mode, crossCaseInvestigationScope]);

  useEffect(() => {
    if (!containerRef.current) return;
    const chart = echarts.init(containerRef.current);
    chartRef.current = chart;
    // ADR-086: the strip's own box changes when the timeline's sash is dragged, with no window
    // resize to tell the chart; the observer does.
    const observer =
      typeof ResizeObserver === "function" ? new ResizeObserver(() => chart.resize()) : null;
    observer?.observe(containerRef.current);
    return () => {
      observer?.disconnect();
      chart.dispose();
      chartRef.current = null;
    };
  }, []);

  // The chart paints to a canvas, so it cannot follow the page's theme by itself: draw it again
  // when the theme changes (ADR-070).
  const [theme, setTheme] = useState<Theme>(currentTheme());
  useEffect(() => onThemeChange(setTheme), []);

  useEffect(() => {
    const chart = chartRef.current;
    if (!chart || !histogram) return;
    const palette = activePalette();
    const borderSubtleHex = palette.borderSubtle;
    const textSecondaryHex = palette.textSecondary;
    // The bars are data, so the data ramp's step 4, not brass (ADR-097, DESIGN.md §3.5).
    const barHex = palette.seq[3];
    const seqHex = palette.seq;
    // The range brush, from the tokens rather than the chart library's own blue (review item 6).
    const brush = {
      backgroundColor: palette.surfaceRaised,
      fillerColor: palette.surfaceHover,
      borderColor: palette.borderSubtle,
      handleStyle: { color: palette.borderStrong, borderColor: palette.borderStrong },
      moveHandleStyle: { color: palette.borderStrong },
      dataBackground: { lineStyle: { color: palette.borderStrong }, areaStyle: { color: palette.borderSubtle } },
      selectedDataBackground: { lineStyle: { color: palette.textSecondary }, areaStyle: { color: palette.borderStrong } },
      textStyle: { color: palette.textSecondary },
    };

    if (mode === "density") {
      const buckets = histogram.buckets;
      chart.off("datazoom");

      // B16's own cross-case overlay: a second grid stacked below the
      // primary track, sharing the *same* category data on its own xAxis
      // — identical bucket boundaries at identical pixel positions is what
      // makes the two tracks read as "against a shared axis"
      // (`08_ACCEPTANCE_SCENARIOS.md` B16's own literal wording), not one
      // ECharts axis object literally shared between two grids (ECharts
      // has no such primitive for two independent grids). Only the bottom
      // track's own axis labels render, so the pair reads as one shared
      // axis rather than two competing label rows.
      const overlayActive = crossCaseHistogram != null;
      const primaryHeight = overlayActive ? "38%" : undefined;
      const categoryData = buckets.map((b) => bucketLabel(b.start, bucketSeconds));
      // ADR-097 step 3: tick labels are literal values, in mono; counts are whole numbers.
      const tick = { color: textSecondaryHex, fontSize: 11, fontFamily: MONO_FONT };

      chart.setOption(
        {
          backgroundColor: "transparent",
          grid: overlayActive
            ? [
                {
                  left: 8,
                  right: 8,
                  top: 8,
                  height: primaryHeight,
                  containLabel: true,
                },
                {
                  left: 8,
                  right: 8,
                  bottom: 40,
                  height: "38%",
                  containLabel: true,
                },
              ]
            : { left: 8, right: 8, top: 8, bottom: 40, containLabel: true },
          xAxis: overlayActive
            ? [
                {
                  type: "category",
                  gridIndex: 0,
                  data: categoryData,
                  axisLabel: { show: false },
                  axisLine: { lineStyle: { color: borderSubtleHex } },
                },
                {
                  type: "category",
                  gridIndex: 1,
                  data: categoryData,
                  axisLine: { lineStyle: { color: borderSubtleHex } },
                  axisLabel: tick,
                },
              ]
            : {
                type: "category",
                data: categoryData,
                axisLine: { lineStyle: { color: borderSubtleHex } },
                axisLabel: tick,
              },
          yAxis: overlayActive
            ? [
                {
                  type: "value",
                minInterval: 1,
                  gridIndex: 0,
                  axisLine: { lineStyle: { color: borderSubtleHex } },
                  axisLabel: tick,
                  splitLine: { lineStyle: { color: borderSubtleHex } },
                },
                {
                  type: "value",
                minInterval: 1,
                  gridIndex: 1,
                  axisLine: { lineStyle: { color: borderSubtleHex } },
                  axisLabel: tick,
                  splitLine: { lineStyle: { color: borderSubtleHex } },
                },
              ]
            : {
                type: "value",
                minInterval: 1,
                axisLine: { lineStyle: { color: borderSubtleHex } },
                axisLabel: tick,
                splitLine: { lineStyle: { color: borderSubtleHex } },
              },
          // The slider zooms the axis (a stray early date can squeeze the rest); it does not filter.
          // The window is selected by dragging across the bars: the brush below (§3.4).
          dataZoom: overlayActive
            ? [{ type: "slider", height: 16, bottom: 4, xAxisIndex: [0, 1], ...brush }]
            : [{ type: "slider", height: 20, bottom: 4, ...brush }],
          brush: {
            xAxisIndex: 0,
            brushType: "lineX",
            brushMode: "single",
            transformable: true,
            throttleType: "debounce",
            throttleDelay: 200,
            brushStyle: { borderWidth: 1, color: palette.surfaceHover, borderColor: palette.textSecondary },
            outOfBrush: { colorAlpha: 0.35 },
          },
          toolbox: { show: false },
          series: overlayActive
            ? [
                {
                  type: "bar",
                  xAxisIndex: 0,
                  yAxisIndex: 0,
                  data: buckets.map((b) => b.count),
                  itemStyle: { color: barHex },
                  barMinWidth: 1,
                  name: "this investigation",
                },
                {
                  type: "bar",
                  xAxisIndex: 1,
                  yAxisIndex: 1,
                  data: categoryData.map((label) => {
                    const match = crossCaseHistogram?.buckets.find(
                      (b) => bucketLabel(b.start, DAILY_INTERVAL_SECONDS) === label,
                    );
                    return match?.count ?? 0;
                  }),
                  // The overlaid case, two steps lighter than this one's, so the two read apart.
                  itemStyle: { color: seqHex[1] },
                  barMinWidth: 1,
                  name: crossCaseInvestigationScope,
                },
              ]
            : [
                {
                  type: "bar",
                  data: buckets.map((b) => b.count),
                  itemStyle: { color: barHex },
                  barMinWidth: 1,
                },
              ],
          tooltip: { trigger: "axis" },
        },
        true,
      );

      // `02_GLASS_FRONTEND.md` §3.4: "drag to select a window". A drag across the bars is the
      // brush; its range of bars becomes the window, which dims the graph. Found 6 October 2026: a
      // drag went to the chart's pan-and-zoom instead, which has nothing to pan at full range.
      chart.off("brushEnd");
      chart.dispatchAction({
        type: "takeGlobalCursor",
        key: "brush",
        brushOption: { brushType: "lineX", brushMode: "single" },
      });
      // A window set another way (Set exact dates, the overlay's case) is drawn as the brush too.
      const current = crossFilterStore.store.getState().window;
      const shown = current ? bucketRangeOfWindow(buckets, current) : null;
      if (shown) {
        chart.dispatchAction({
          type: "brush",
          areas: [{ brushType: "lineX", xAxisIndex: 0, coordRange: shown }],
        });
      }
      chart.on("brushEnd", (params: unknown) => {
        if (histogram.total === 0) return; // ADR-087: no brush where there are no dated events
        const areas = (params as { areas?: Array<{ coordRange?: [number, number] }> }).areas ?? [];
        const range = areas[0]?.coordRange;
        if (!range) return;
        const window = windowFromBucketRange(buckets, range[0], range[1]);
        if (!window) return;
        crossFilterStore.store.getState().setWindow(window);
        void crossFilterStore.refresh(getNodeIds(), getEdgeIds?.());
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
            axisLabel: { color: textSecondaryHex, fontSize: 11 },
            splitArea: { show: true },
          },
          yAxis: {
            type: "category",
            data: WEEKDAY_LABELS,
            axisLabel: { color: textSecondaryHex, fontSize: 11 },
            splitArea: { show: true },
          },
          visualMap: {
            min: 0,
            max,
            calculable: true,
            orient: "horizontal",
            left: "center",
            bottom: 0,
            inRange: { color: seqHex },
            textStyle: { color: textSecondaryHex },
          },
          series: [{ type: "heatmap", data, label: { show: false } }],
          tooltip: {},
        },
        true,
      );
    }
  }, [
    histogram,
    mode,
    crossFilterStore,
    getNodeIds,
    getEdgeIds,
    crossCaseHistogram,
    crossCaseInvestigationScope,
    theme,
    bucketSeconds,
  ]);

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
    void crossFilterStore.refresh(getNodeIds(), getEdgeIds?.());
  }

  return (
    <div
      style={{ display: "flex", flexDirection: "column", height: "100%" }}
      /* **How many tracks are drawn against this axis — round 13cde.**
       *
       * The chart is one `<canvas>`, so a second track is invisible to anything that is not
       * looking at pixels, and B16's own claim ("both event sets render on distinct tracks
       * against a shared axis") had no tier that could prove it. This is the component's own
       * state, published once rather than re-derived: `overlayActive` below is the same
       * `crossCaseHistogram != null`, and if the two ever disagreed the ECharts option and this
       * attribute would be describing different charts. `live/scenario-b-timeline.spec.ts` is
       * what fails if the overlay stops adding its grid. */
      data-timeline-tracks={crossCaseHistogram != null ? 2 : 1}
      /* How many events the overlay track is actually drawing. A second investigation
       * with no events still produces a `Histogram` (an empty one), so `data-timeline-
       * tracks` alone would read 2 for an overlay of nothing onto something — a test
       * against it would pass without the row being true. */
      data-timeline-overlay-events={crossCaseHistogram?.total ?? 0}
    >
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: "var(--sp-8)",
          padding: "var(--sp-4) var(--sp-8)",
        }}
      >
        {/* ADR-097 step 3 (design review item 13): the mode switch is one segmented control in the
            header; setting exact dates and overlaying another case are in its overflow menu. */}
        <div role="group" aria-label="Timeline view" className="segmented">
          <button
            type="button"
            className="segmented__item"
            aria-pressed={mode === "density"}
            onClick={() => setMode("density")}
          >
            Density
          </button>
          <button
            type="button"
            className="segmented__item"
            aria-pressed={mode === "cyclical"}
            onClick={() => setMode("cyclical")}
          >
            Cyclical
          </button>
        </div>
        {bucketSeconds < DAILY_INTERVAL_SECONDS && mode === "density" && (
          <span className="timeline__note">By the hour: every dated event is on one day</span>
        )}
        <span style={{ flex: 1 }} />
        {(activeWindow || selectedNodeIds) && (
          <Button
            onClick={() => {
              crossFilterStore.store.getState().clearFilter();
              void crossFilterStore.refresh(getNodeIds(), getEdgeIds?.());
            }}
          >
            Clear filter
          </Button>
        )}
        {hasEvents && activeWindow && (
          <>
            {/* B18's own playback control — `02_GLASS_FRONTEND.md` §3.4:
                "animate the brush forward at 0.5x to 8x." Disabled with no
                active brush window: there is nothing to animate across yet
                (the same reasoning the input fields above already assume
                by rendering only in density mode). */}
            <Button
              aria-label={
                playback.isPlaying ? "Pause playback" : "Play playback"
              }
              aria-pressed={playback.isPlaying}
              onClick={() =>
                playback.isPlaying ? playback.pause() : playback.play()
              }
            >
              {playback.isPlaying ? "Pause" : "Play"}
            </Button>
            <Select
              aria-label="Playback speed"
              value={String(playback.speed)}
              onChange={(e) =>
                playback.setSpeed(
                  Number(e.target.value) as typeof playback.speed,
                )
              }
            >
              {PLAYBACK_SPEEDS.map((speed) => (
                <option key={speed} value={speed}>
                  {speed}×
                </option>
              ))}
            </Select>
          </>
        )}
        {(hasEvents && mode === "density") || onCrossCaseScopeChange ? (
          <span className="timeline__more">
            <button
              type="button"
              className="btn btn--quiet"
              aria-label="More timeline options"
              aria-expanded={moreOpen}
              title="More timeline options"
              onClick={() => setMoreOpen((open) => !open)}
            >
              ⋯
            </button>
            {moreOpen && (
              <div className="timeline__menu" role="group" aria-label="More timeline options">
                {hasEvents && mode === "density" && (
                  <Button aria-expanded={datesOpen} onClick={() => setDatesOpen((open) => !open)}>
                    Set exact dates
                  </Button>
                )}
                {mode === "density" && datesOpen && (
                  <span style={{ display: "flex", gap: "var(--sp-4)" }}>
                    {/* `02_GLASS_FRONTEND.md` §3.4: "Brush endpoints are editable as text." Editing a
                        field updates the active filter immediately; the slider's own handles move on
                        the next histogram refetch rather than live-tracking a keystroke. */}
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
                  </span>
                )}
                {onCrossCaseScopeChange && (
                  <Button aria-expanded={overlayOpen} onClick={() => setOverlayOpen((open) => !open)}>
                    Overlay another case
                    {crossCaseInvestigationScope ? `: ${crossCaseInvestigationScope}` : ""}
                  </Button>
                )}
                {onCrossCaseScopeChange && overlayOpen && (
                  <input
                    id="cross-case-scope"
                    type="text"
                    aria-label="Cross-case overlay investigation id"
                    placeholder="investigation id"
                    value={crossCaseInvestigationScope ?? ""}
                    onChange={(e) => onCrossCaseScopeChange(e.target.value)}
                    style={{ width: 200 }}
                  />
                )}
              </div>
            )}
          </span>
        ) : null}
      </div>
      {/* ADR-087: a case with no dated events says so, and offers no brush and no playback, so the
          graph is never dimmed for a reason the analyst cannot see. The chart stays mounted but
          out of sight, so a case that gains events later needs no remount. */}
      {!hasEvents && (
        <p role="status" style={{ margin: "var(--sp-8)", color: "var(--text-secondary)" }}>
          No dated events in this case. The timeline, its brush and playback need events with a date,
          which this case&rsquo;s data does not carry.
        </p>
      )}
      <div
        ref={containerRef}
        style={{ flex: 1, minHeight: 0, display: hasEvents ? undefined : "none" }}
        aria-hidden={!hasEvents}
      />
    </div>
  );
}
