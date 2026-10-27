// ADR-115 Amendment 2: the weekly view's colour key sits beside the hour axis, never over it. Found in
// the signed-in sitting, 14 October 2026: centred along the bottom, it covered the 10–12 o'clock labels.
import { describe, expect, it } from "vitest";

import {
  KEY_WIDTH,
  WEEKEND_DAYS,
  cellsFromChoice,
  cellsFromRange,
  cyclicalOption,
} from "./cyclicalOption";

describe("the weekly view's colour key", () => {
  const option = cyclicalOption({ data: [[9, 1, 4]], max: 4, colours: ["#eee", "#055"], text: "#555" });

  it("stands upright at the right-hand side, not along the bottom", () => {
    expect(option.visualMap.orient).toBe("vertical");
    expect(option.visualMap.right).toBe(0);
    expect(option.visualMap).not.toHaveProperty("bottom");
  });

  it("has room of its own: the grid stops short of it", () => {
    expect(option.grid.right).toBeGreaterThanOrEqual(KEY_WIDTH);
  });
});

describe("the weekly view's chosen cells (ADR-130 decision 2)", () => {
  const base = { data: [[9, 5, 4], [10, 5, 2]], max: 4, colours: ["#eee", "#055"], text: "#555" };

  it("draws the whole grid whether or not cells are chosen, the chosen ones marked", () => {
    const none = cyclicalOption(base);
    const some = cyclicalOption({ ...base, cells: [{ weekday: 5, hour: 9 }], shade: "#123456" });
    expect(some.series[0]!.data).toHaveLength(none.series[0]!.data.length);
    const marked = some.series[0]!.data.filter((d) => !Array.isArray(d));
    expect(marked).toHaveLength(1);
    expect(marked[0]).toMatchObject({ value: [9, 5, 4] });
    expect(none.series[0]!.data.every((d) => Array.isArray(d))).toBe(true);
  });

  it("marks a chosen cell that has no events too, so a chosen empty cell is still seen", () => {
    const option = cyclicalOption({ ...base, cells: [{ weekday: 0, hour: 0 }], shade: "#123456" });
    const marked = option.series[0]!.data.filter((d) => !Array.isArray(d));
    expect(marked).toHaveLength(1);
    expect(marked[0]).toMatchObject({ value: [0, 0, 0] });
  });

  it("is a rectangle brush on the heat map's own axes", () => {
    const option = cyclicalOption(base);
    expect(option.brush).toMatchObject({ brushType: "rect", xAxisIndex: 0, yAxisIndex: 0 });
  });
});

describe("cellsFromRange", () => {
  it("turns a dragged rectangle (hour and day positions, either way round) into its cells", () => {
    expect(cellsFromRange([8.6, 10.2], [4.8, 6.1])).toEqual(
      [9, 10].flatMap((hour) => [5, 6].map((weekday) => ({ weekday, hour }))),
    );
    expect(cellsFromRange([10.2, 8.6], [6.1, 4.8])).toEqual(cellsFromRange([8.6, 10.2], [4.8, 6.1]));
  });

  it("is held to the grid", () => {
    const cells = cellsFromRange([-3, 40], [-1, 9]);
    expect(cells).toHaveLength(24 * 7);
  });
});

describe("the options menu's cell choice", () => {
  it("a day set, an hour range and the Weekend shortcut give the cells", () => {
    expect(cellsFromChoice([5, 6], 9, 10)).toEqual(
      [5, 6].flatMap((weekday) => [9, 10].map((hour) => ({ weekday, hour }))),
    );
    expect(cellsFromChoice(WEEKEND_DAYS, 0, 23)).toHaveLength(48);
    expect(WEEKEND_DAYS).toEqual([5, 6]);
  });

  it("no day chosen is no cells, and a reversed hour range is read either way round", () => {
    expect(cellsFromChoice([], 0, 23)).toEqual([]);
    expect(cellsFromChoice([0], 11, 9)).toEqual(cellsFromChoice([0], 9, 11));
  });
});
