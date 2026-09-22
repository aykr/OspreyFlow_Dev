import { describe, expect, it } from "vitest";

import type { TimeWindow } from "../crossfilter/store";
import {
  instantAtFraction,
  itemsUpTo,
  PLAYBACK_DURATION_MS_AT_1X,
  playbackFraction,
} from "./math";

describe("playbackFraction", () => {
  it("is 0 at the start", () => {
    expect(playbackFraction(0, 1)).toBe(0);
  });

  it("reaches 1 exactly at the full duration, at 1x", () => {
    expect(playbackFraction(PLAYBACK_DURATION_MS_AT_1X, 1)).toBe(1);
  });

  it("is clamped to 1, never overshoots past the end of the window", () => {
    expect(playbackFraction(PLAYBACK_DURATION_MS_AT_1X * 10, 1)).toBe(1);
  });

  it("speed multiplies how fast the fraction advances, not what the whole window means", () => {
    // Half the duration at 2x covers the same ground as the full duration at 1x.
    expect(playbackFraction(PLAYBACK_DURATION_MS_AT_1X / 2, 2)).toBe(1);
    // Half the duration at 0.5x covers a quarter of the window.
    expect(playbackFraction(PLAYBACK_DURATION_MS_AT_1X / 2, 0.5)).toBeCloseTo(0.25);
  });

  it("never goes negative for a negative elapsed value", () => {
    expect(playbackFraction(-500, 1)).toBe(0);
  });
});

describe("instantAtFraction", () => {
  const window: TimeWindow = {
    validFrom: "2026-01-01T00:00:00.000Z",
    validTo: "2026-01-02T00:00:00.000Z",
  };

  it("is the window's own start at fraction 0", () => {
    expect(instantAtFraction(window, 0).toISOString()).toBe("2026-01-01T00:00:00.000Z");
  });

  it("is the window's own end at fraction 1", () => {
    expect(instantAtFraction(window, 1).toISOString()).toBe("2026-01-02T00:00:00.000Z");
  });

  it("is the midpoint at fraction 0.5", () => {
    expect(instantAtFraction(window, 0.5).toISOString()).toBe("2026-01-01T12:00:00.000Z");
  });

  it("collapses to validFrom for an open-ended window with no validTo", () => {
    const open: TimeWindow = { validFrom: "2026-01-01T00:00:00.000Z", validTo: null };
    expect(instantAtFraction(open, 0.5).toISOString()).toBe("2026-01-01T00:00:00.000Z");
  });

  it("clamps an out-of-range fraction rather than extrapolating past the window", () => {
    expect(instantAtFraction(window, 2).toISOString()).toBe("2026-01-02T00:00:00.000Z");
    expect(instantAtFraction(window, -1).toISOString()).toBe("2026-01-01T00:00:00.000Z");
  });
});

describe("itemsUpTo", () => {
  const items = [
    { occurred_at: "2026-01-01T08:00:00Z", id: "a" },
    { occurred_at: "2026-01-01T09:00:00Z", id: "b" },
    { occurred_at: "2026-01-01T10:00:00Z", id: "c" },
  ];

  it("reveals nothing before the first item's own timestamp", () => {
    expect(itemsUpTo(items, new Date("2026-01-01T07:00:00Z"))).toEqual([]);
  });

  it("reveals items at or before the instant, in order, and stops at the first one after it", () => {
    expect(itemsUpTo(items, new Date("2026-01-01T09:00:00Z"))).toEqual([items[0], items[1]]);
  });

  it("reveals every item once the instant is at or past the last one", () => {
    expect(itemsUpTo(items, new Date("2026-01-01T12:00:00Z"))).toEqual(items);
  });

  it("REGRESSION: does not silently reveal a later item while an earlier one is still withheld — proving this is a real ordered cutoff, not merely a length check", () => {
    // A deliberately out-of-order input: if this function only checked
    // *count*, not each item's own timestamp against the cutoff, it could
    // reveal "b" (out of order, timestamped after the cutoff) while still
    // technically returning the "right number" of items. The `break` on
    // the first item past cutoff, not a filter, is what this proves.
    const outOfOrder = [
      { occurred_at: "2026-01-01T08:00:00Z", id: "a" },
      { occurred_at: "2026-01-01T11:00:00Z", id: "b-too-late" },
    ];
    expect(itemsUpTo(outOfOrder, new Date("2026-01-01T09:00:00Z"))).toEqual([outOfOrder[0]]);
  });
});
