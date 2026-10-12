// @vitest-environment jsdom
// ADR-115 E4 (DESIGN.md §5a, the reference's timeline): folded, the timeline is a 34px row that still
// says what the case holds over time — a small density strip and the date range, in mono — from the
// same histogram the open timeline draws.
import { cleanup, render, screen } from "@testing-library/react";
import { act } from "react";
import { afterEach, describe, expect, it } from "vitest";

import { forgetTimelineSummaryForTest, publishTimelineSummary } from "./timelineSummary";
import { TimelineStrip } from "./TimelineStrip";

afterEach(() => {
  cleanup();
  forgetTimelineSummaryForTest();
});

const DAYS = [
  { start: "2026-03-01T00:00:00Z", end: "2026-03-02T00:00:00Z", count: 2 },
  { start: "2026-03-02T00:00:00Z", end: "2026-03-03T00:00:00Z", count: 8 },
  { start: "2026-03-03T00:00:00Z", end: "2026-03-04T00:00:00Z", count: 0 },
  { start: "2026-03-04T00:00:00Z", end: "2026-03-05T00:00:00Z", count: 4 },
];

describe("the folded timeline's strip", () => {
  it("draws one bar a bucket, the tallest full height, and names the range in mono", () => {
    render(<TimelineStrip />);
    act(() => publishTimelineSummary({ bucketing: "fixed_interval", buckets: DAYS, total: 14 }));
    const bars = Array.from(document.querySelectorAll(".timeline-strip__bar")) as HTMLElement[];
    expect(bars.map((b) => b.style.height)).toEqual(["25%", "100%", "0%", "50%"]);
    const range = screen.getByText("2026-03-01 to 2026-03-04");
    expect(range.className).toContain("value");
  });

  it("says nothing it has not been given, and ignores the cyclical week", () => {
    render(<TimelineStrip />);
    expect(document.querySelectorAll(".timeline-strip__bar")).toHaveLength(0);
    act(() => publishTimelineSummary({ bucketing: "weekday_hour", buckets: [{ weekday: 1, hour: 9, count: 3 }], total: 3 }));
    expect(document.querySelectorAll(".timeline-strip__bar")).toHaveLength(0);
  });
});
