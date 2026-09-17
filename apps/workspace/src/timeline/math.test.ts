import { describe, expect, it } from "vitest";

import type { HistogramBucket } from "../../../../packages/schemas/generated";
import { windowFromZoomPercent } from "./math";

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
