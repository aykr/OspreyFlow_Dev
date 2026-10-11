// @vitest-environment jsdom
// ADR-113 stage 5: a trend drawn says its periods as days, in the words the print document uses.
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
    expect(screen.getByText("From 14 September 2026 to 28 September 2026; the tallest bar is 350.")).toBeTruthy();
    expect(screen.getByRole("img").getAttribute("aria-label")).toBe(
      "Payments by channel: one bar for each of 3 weeks, from 14 September 2026 to 28 September 2026",
    );
    expect(screen.getByTitle("Week of 21 September 2026: 250")).toBeTruthy();
  });
});
