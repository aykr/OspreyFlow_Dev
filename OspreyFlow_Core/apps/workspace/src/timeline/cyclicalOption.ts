// The weekly (cyclical) view's chart: hours along, days down, a cell's shade its count. Its colour key
// stands at the right-hand side in room the grid leaves for it — never over the hour labels
// (ADR-115 Amendment 2).

export const HOUR_LABELS = Array.from({ length: 24 }, (_, h) => String(h));
export const WEEKDAY_LABELS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

/** One cell of the weekly grid: the weekday (0 = Monday) and the hour (0-23). */
export type Cell = {
  weekday: number;
  hour: number;
};

/** Saturday and Sunday, in the weekly histogram's numbering (0 = Monday). */
export const WEEKEND_DAYS: readonly number[] = [5, 6];

const clampIndex = (i: number, last: number) => Math.min(last, Math.max(0, Math.round(i)));

/** The cells a dragged rectangle covers: `xRange` along the hours, `yRange` down the days, either
 * way round, held to the grid. The rounding is the density brush's own (`math.ts`'s
 * `windowFromBucketRange`): a position is the nearest cell's. */
export function cellsFromRange(
  xRange: readonly [number, number],
  yRange: readonly [number, number],
): Cell[] {
  const h0 = clampIndex(Math.min(...xRange), 23);
  const h1 = clampIndex(Math.max(...xRange), 23);
  const d0 = clampIndex(Math.min(...yRange), 6);
  const d1 = clampIndex(Math.max(...yRange), 6);
  const cells: Cell[] = [];
  for (let hour = h0; hour <= h1; hour += 1) {
    for (let weekday = d0; weekday <= d1; weekday += 1) cells.push({ weekday, hour });
  }
  return cells;
}

/** The cells the "Choose cells" control describes: the days ticked, over the hours from `from` to
 * `to` (either way round, held to 0-23), each hour on each day. No day ticked is no cells. */
export function cellsFromChoice(days: readonly number[], from: number, to: number): Cell[] {
  const lo = clampIndex(Math.min(from, to), 23);
  const hi = clampIndex(Math.max(from, to), 23);
  const cells: Cell[] = [];
  for (const weekday of [...days].sort((a, b) => a - b)) {
    for (let hour = lo; hour <= hi; hour += 1) cells.push({ weekday, hour });
  }
  return cells;
}

/** The width the key takes, which the grid leaves free beside it. */
export const KEY_WIDTH = 64;

export function cyclicalOption({
  data,
  max,
  colours,
  text,
  cells = null,
  shade = "#888888",
}: {
  data: number[][];
  max: number;
  colours: readonly string[];
  text: string;
  /** The cells chosen (ADR-130 decision 2): drawn with a border in `shade`; the grid stays whole. */
  cells?: readonly Cell[] | null;
  shade?: string;
}) {
  const chosen = new Set((cells ?? []).map((c) => `${c.hour}:${c.weekday}`));
  const mark = { borderColor: shade, borderWidth: 2 };
  const drawn: Array<number[] | { value: number[]; itemStyle: typeof mark }> = data.map((d) =>
    chosen.has(`${d[0]}:${d[1]}`) ? { value: d, itemStyle: mark } : d,
  );
  // A chosen cell with no events is still drawn, so the choice can be seen.
  const present = new Set(data.map((d) => `${d[0]}:${d[1]}`));
  for (const key of chosen) {
    if (present.has(key)) continue;
    const [hour, weekday] = key.split(":").map(Number) as [number, number];
    drawn.push({ value: [hour, weekday, 0], itemStyle: mark });
  }
  return {
    backgroundColor: "transparent",
    grid: { left: 48, right: KEY_WIDTH, top: 8, bottom: 24, containLabel: true },
    xAxis: {
      type: "category" as const,
      data: HOUR_LABELS,
      axisLabel: { color: text, fontSize: 11 },
      splitArea: { show: true },
    },
    yAxis: {
      type: "category" as const,
      data: WEEKDAY_LABELS,
      axisLabel: { color: text, fontSize: 11 },
      splitArea: { show: true },
    },
    visualMap: {
      min: 0,
      max,
      calculable: true,
      orient: "vertical" as const,
      right: 0,
      top: "middle" as const,
      itemWidth: 12,
      itemHeight: 90,
      inRange: { color: [...colours] },
      textStyle: { color: text },
    },
    // The drag across cells (ADR-130 decision 2): a rectangle on the grid's own two axes.
    brush: {
      xAxisIndex: 0,
      yAxisIndex: 0,
      brushType: "rect" as const,
      brushMode: "single" as const,
      transformable: true,
      throttleType: "debounce" as const,
      throttleDelay: 200,
      brushStyle: { borderWidth: 1, color: `${shade}33`, borderColor: shade },
    },
    toolbox: { show: false },
    series: [{ type: "heatmap" as const, data: drawn, label: { show: false } }],
    tooltip: {},
  };
}
