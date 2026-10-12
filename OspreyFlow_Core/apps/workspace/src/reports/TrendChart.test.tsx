// @vitest-environment jsdom
// ADR-113 stage 5: a trend drawn says its periods as days, in the words the print document uses, and
// draws every period of its window — an empty one as an empty bar (Amendment 3, finding 4).
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { TrendChart } from "./TrendChart";
import { figures } from "./reportsTestKit";

afterEach(cleanup);

describe("TrendChart", () => {
  it("says the span and each bar's period as days, never as timestamps", () => {
    const f = figures();
    const at = (p: (typeof f.result.points)[number]) => ({ ...p, period_start: `${p.period_start}T00:00:00Z` });
    render(<TrendChart figures={{ ...f, result: { ...f.result, points: f.result.points.map(at) } }} />);
    expect(screen.getByText("From 13 July 2026 to 5 October 2026; the tallest bar is 350.")).toBeTruthy();
    expect(screen.getByRole("img").getAttribute("aria-label")).toBe(
      "Payments by channel: one bar for each of 13 weeks, from 13 July 2026 to 5 October 2026",
    );
    expect(screen.getByTitle("Week of 21 September 2026: 250")).toBeTruthy();
  });

  it("draws a week with no events as an empty bar in its place, never closing up the axis", () => {
    const f = figures();
    // As the server sends them: a full timestamp, not the day the bar is keyed by.
    const points = f.result.points
      .filter((p) => p.period_start !== "2026-09-21")
      .map((p) => ({ ...p, period_start: `${p.period_start}T00:00:00Z` }));
    const { container } = render(<TrendChart figures={{ ...f, result: { ...f.result, points } }} />);
    const bars = [...container.querySelectorAll("[data-period]")];
    expect(bars.slice(9).map((bar) => bar.getAttribute("data-period"))).toEqual(["2026-09-14", "2026-09-21", "2026-09-28", "2026-10-05"]);
    expect(bars.slice(9).map((bar) => bar.children.length)).toEqual([2, 0, 2, 0]);
    expect(screen.getByTitle("Week of 14 September 2026: 150")).toBeTruthy();
    expect(screen.getByTitle("Week of 21 September 2026: 0")).toBeTruthy();
    expect(screen.getByTitle("Week of 13 July 2026: 0")).toBeTruthy();
  });
});
