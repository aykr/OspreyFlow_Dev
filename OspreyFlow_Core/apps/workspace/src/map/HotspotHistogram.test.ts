import { describe, expect, it } from "vitest";

import type { EdgeTypeDef, Histogram } from "../../../../packages/schemas/generated";
import { locationEdgeTypeNames, rankTargetIdBuckets } from "./HotspotHistogram";

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

// 9 October 2026: on a case of phone records, "Hotspot cells" showed a full row of bars over a map
// with nothing on it. It ranked every event by its target, which for calls is the number called.
// A hotspot is a place: the panel counts only events on links that end at a Location.
describe("locationEdgeTypeNames", () => {
  it("names the link types that end at a Location, and no others", () => {
    const types = [
      { name: "PRESENT_AT", from: ["Person", "Device"], to: ["Location"] },
      { name: "COMMUNICATED_WITH", from: ["Endpoint"], to: ["Endpoint"] },
      { name: "USES", from: ["Person"], to: ["Endpoint", "Device"] },
    ] as unknown as EdgeTypeDef[];
    expect(locationEdgeTypeNames(types)).toEqual(["PRESENT_AT"]);
  });
});
