// ADR-113 Amendment 3, finding 4: a trend's periods are every period its window touches — Monday
// weeks or calendar months in UTC, as the AnalyticsPort suite pins them — never only those with events.
import { describe, expect, it } from "vitest";

import { periodsOf } from "./packText";
import { figures } from "./reportsTestKit";

describe("periodsOf", () => {
  it("names every Monday week the window touches, the empty ones too", () => {
    const weeks = periodsOf(figures());
    expect(weeks).toHaveLength(13);
    expect([weeks[0], weeks[12]]).toEqual(["2026-07-13", "2026-10-05"]);
    expect(weeks).toContain("2026-08-17");
  });

  it("names every calendar month the window touches", () => {
    const f = figures({ interval: "month" });
    const months = periodsOf({ ...f, result: { ...f.result, interval: "month", points: [] } });
    expect(months).toEqual(["2026-07-01", "2026-08-01", "2026-09-01", "2026-10-01"]);
  });

  it("keeps a point the window does not explain, rather than dropping it", () => {
    const f = figures();
    const points = [...f.result.points, { period_start: "2026-06-01T00:00:00Z", series: "card", value: 1 }];
    expect(periodsOf({ ...f, result: { ...f.result, points } })[0]).toBe("2026-06-01");
  });
});
