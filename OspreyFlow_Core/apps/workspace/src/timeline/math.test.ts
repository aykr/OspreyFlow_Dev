import { describe, expect, it } from "vitest";

import type { HistogramBucket } from "../../../../packages/schemas/generated";
import { allOnOneDay, bucketLabel, bucketRangeOfWindow, windowFromBucketRange, windowFromZoomPercent } from "./math";

const BUCKETS: HistogramBucket[] = [
  { start: "2026-01-01T00:00:00Z", end: "2026-01-02T00:00:00Z", count: 3 },
  { start: "2026-01-02T00:00:00Z", end: "2026-01-03T00:00:00Z", count: 5 },
  { start: "2026-01-03T00:00:00Z", end: "2026-01-04T00:00:00Z", count: 1 },
  { start: "2026-01-04T00:00:00Z", end: "2026-01-05T00:00:00Z", count: 8 },
  { start: "2026-01-05T00:00:00Z", end: "2026-01-06T00:00:00Z", count: 2 },
];

describe("windowFromZoomPercent", () => {
  it("spans the full range at 0-100%", () => {
    expect(windowFromZoomPercent(BUCKETS, 0, 100)).toEqual({
      validFrom: "2026-01-01T00:00:00Z",
      validTo: "2026-01-06T00:00:00Z",
    });
  });

  it("resolves a mid-range window to the nearest bucket boundaries", () => {
    expect(windowFromZoomPercent(BUCKETS, 25, 75)).toEqual({
      validFrom: "2026-01-02T00:00:00Z",
      validTo: "2026-01-05T00:00:00Z",
    });
  });

  it("is order-independent — a reversed start/end still resolves low-to-high", () => {
    expect(windowFromZoomPercent(BUCKETS, 75, 25)).toEqual(
      windowFromZoomPercent(BUCKETS, 25, 75),
    );
  });

  it("returns null for an empty bucket list", () => {
    expect(windowFromZoomPercent([], 0, 100)).toBeNull();
  });

  it("returns null when the resolved bucket has no start/end (e.g. weekday_hour buckets)", () => {
    const cyclical: HistogramBucket[] = [{ weekday: 0, hour: 9, count: 4 }];
    expect(windowFromZoomPercent(cyclical, 0, 100)).toBeNull();
  });
});

// ADR-097 step 3 (design review item 13): a case whose dated events all fall on one day is shown by
// the hour, and each bucket's label says what it covers.
describe("allOnOneDay and bucketLabel", () => {
  const day = (start: string, count: number) => ({
    start,
    end: new Date(Date.parse(start) + 86_400_000).toISOString(),
    count,
  });

  it("is true when every bucket with events starts on the same day", () => {
    expect(allOnOneDay([day("2026-01-01T00:00:00Z", 0), day("2026-01-02T00:00:00Z", 5), day("2026-01-03T00:00:00Z", 0)])).toBe(true);
    expect(allOnOneDay([day("2026-01-01T00:00:00Z", 2), day("2026-01-02T00:00:00Z", 5)])).toBe(false);
  });

  it("is false with no events at all, so an empty case stays as it is (ADR-087)", () => {
    expect(allOnOneDay([day("2026-01-01T00:00:00Z", 0)])).toBe(false);
    expect(allOnOneDay([])).toBe(false);
  });

  it("labels a daily bucket by its date and an hourly one by its hour", () => {
    expect(bucketLabel("2026-01-02T00:00:00Z", 86_400)).toBe("2026-01-02");
    expect(bucketLabel("2026-01-02T14:00:00Z", 3_600)).toBe("14:00");
    expect(bucketLabel(undefined, 3_600)).toBe("");
  });
});

describe("windowFromBucketRange (a drag across the bars)", () => {
  it("is from the first bar's start to the last bar's end, whichever way the drag went", () => {
    expect(windowFromBucketRange(BUCKETS, 1, 3)).toEqual({ validFrom: "2026-01-02T00:00:00Z", validTo: "2026-01-05T00:00:00Z" });
    expect(windowFromBucketRange(BUCKETS, 3, 1)).toEqual({ validFrom: "2026-01-02T00:00:00Z", validTo: "2026-01-05T00:00:00Z" });
  });

  it("holds a drag past either end to the bars there are", () => {
    expect(windowFromBucketRange(BUCKETS, -2, 99)).toEqual({ validFrom: "2026-01-01T00:00:00Z", validTo: "2026-01-06T00:00:00Z" });
    expect(windowFromBucketRange([], 0, 1)).toBeNull();
  });
});

describe("bucketRangeOfWindow (drawing a window set another way)", () => {
  it("is the bars the window covers", () => {
    expect(bucketRangeOfWindow(BUCKETS, { validFrom: "2026-01-02T00:00:00Z", validTo: "2026-01-05T00:00:00Z" })).toEqual([1, 3]);
    expect(bucketRangeOfWindow(BUCKETS, { validFrom: "2030-01-01T00:00:00Z", validTo: null })).toBeNull();
  });
});
