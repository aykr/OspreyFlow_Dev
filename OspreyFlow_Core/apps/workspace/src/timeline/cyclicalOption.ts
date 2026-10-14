// The weekly (cyclical) view's chart: hours along, days down, a cell's shade its count. Its colour key
// stands at the right-hand side in room the grid leaves for it — never over the hour labels
// (ADR-115 Amendment 2).

export const HOUR_LABELS = Array.from({ length: 24 }, (_, h) => String(h));
export const WEEKDAY_LABELS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

/** The width the key takes, which the grid leaves free beside it. */
export const KEY_WIDTH = 64;

export function cyclicalOption({
  data,
  max,
  colours,
  text,
}: {
  data: number[][];
  max: number;
  colours: readonly string[];
  text: string;
}) {
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
    series: [{ type: "heatmap" as const, data, label: { show: false } }],
    tooltip: {},
  };
}
