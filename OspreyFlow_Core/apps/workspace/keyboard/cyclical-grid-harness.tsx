// Build order step 18c (the 3 November rehearsal's D3): the weekly grid drawn as the timeline draws
// it (`Timeline.tsx`: `echarts/core` with the same pieces registered, `cyclicalOption`, the option
// replaced on the same chart, then the rectangle brush taken and emptied), once with no cell chosen
// and again with the weekend chosen. `cyclical-grid.spec.ts` reads each cell's middle colour after
// each drawing. `?cells` draws the second time with the weekend chosen.
import * as echarts from "echarts/core";
import { HeatmapChart } from "echarts/charts";
import { BrushComponent, GridComponent, TooltipComponent, VisualMapComponent } from "echarts/components";
import { CanvasRenderer } from "echarts/renderers";

import { cellsFromChoice, cyclicalOption, WEEKEND_DAYS } from "../src/timeline/cyclicalOption";

echarts.use([HeatmapChart, BrushComponent, GridComponent, TooltipComponent, VisualMapComponent, CanvasRenderer]);

// Every cell holds events, as the prison case's grid does; Sunday 14:00 the busiest.
const data = Array.from({ length: 168 }, (_, i) => [i % 24, Math.floor(i / 24), i === 6 * 24 + 14 ? 2244 : 300 + ((i * 37) % 900)]);
const box = document.getElementById("grid")!;
const chart = echarts.init(box);

function draw(cells: ReturnType<typeof cellsFromChoice> | null): void {
  chart.setOption(
    cyclicalOption({ data, max: 2244, colours: ["#e6f2f2", "#005a5a"], text: "#505a5f", cells, shade: "#0b0c0c" }),
    true,
  );
  chart.dispatchAction({ type: "takeGlobalCursor", key: "brush", brushOption: { brushType: "rect", brushMode: "single" } });
  chart.dispatchAction({ type: "brush", areas: [] });
}

/** Each cell's middle colour, the chart's layers put together as the page shows them. */
function colours(): number[][] {
  const layers = Array.from(box.querySelectorAll("canvas"));
  const first = layers[0]!;
  const scale = first.width / first.getBoundingClientRect().width;
  const flat = document.createElement("canvas");
  flat.width = first.width;
  flat.height = first.height;
  const ctx = flat.getContext("2d")!;
  for (const layer of layers) ctx.drawImage(layer, 0, 0);
  return data.map(([hour, weekday]) => {
    const [x, y] = chart.convertToPixel({ seriesIndex: 0 }, [hour!, weekday!]) as number[];
    return Array.from(ctx.getImageData(Math.round(x! * scale), Math.round(y! * scale), 1, 1).data);
  });
}

const weekend = new URLSearchParams(window.location.search).has("cells");
draw(null);
setTimeout(() => {
  const before = colours();
  draw(weekend ? cellsFromChoice(WEEKEND_DAYS, 0, 23) : null);
  setTimeout(() => {
    (window as unknown as { gridColours: unknown }).gridColours = { before, after: colours() };
  }, 300);
}, 300);
