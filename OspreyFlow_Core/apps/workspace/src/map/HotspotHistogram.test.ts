import { describe, expect, it } from "vitest";

import type { Histogram } from "../../../../packages/schemas/generated";
import { rankTargetIdBuckets } from "./HotspotHistogram";

describe("rankTargetIdBuckets", () => {
  it("ranks buckets highest-count first", () => {
    const histogram: Histogram = {
      bucketing: "categorical",
      total: 6,
      buckets: [
        { label: "cell-a", count: 1 },
        { label: "cell-b", count: 4 },
        { label: "cell-c", count: 1 },
      ],
    };
    expect(rankTargetIdBuckets(histogram)).toEqual([
      { key: "cell-b", count: 4, label: "cell-b" },
      { key: "cell-a", count: 1, label: "cell-a" },
      { key: "cell-c", count: 1, label: "cell-c" },
    ]);
  });

  it("drops a bucket with no label", () => {
    const histogram: Histogram = {
      bucketing: "categorical",
      total: 1,
      buckets: [{ label: null, count: 1 }],
    };
    expect(rankTargetIdBuckets(histogram)).toEqual([]);
  });

  it("returns an empty array for an undefined histogram", () => {
    expect(rankTargetIdBuckets(undefined)).toEqual([]);
  });
});
