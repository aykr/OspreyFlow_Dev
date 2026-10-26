// ADR-127 decision 11: a link can be a span, and a span still running has no end. It reads as "from
// …  (open)", never as an end that is missing or "present", wherever a link's dates are shown.
import { describe, expect, it } from "vitest";

import { intervalText } from "./intervalText";

describe("intervalText", () => {
  it("reads a closed span as its two ends", () => {
    expect(intervalText({ valid_from: "2026-03-01", valid_to: "2026-03-09" })).toBe("2026-03-01 – 2026-03-09");
  });

  it("reads a span with no end as open, from its start", () => {
    expect(intervalText({ valid_from: "2026-03-01", valid_to: null })).toBe("from 2026-03-01 (open)");
    expect(intervalText({ valid_from: "2026-03-01" })).toBe("from 2026-03-01 (open)");
  });

  it("can shorten both ends to their dates", () => {
    expect(intervalText({ valid_from: "2026-03-01T09:00:00Z", valid_to: null }, { dateOnly: true })).toBe(
      "from 2026-03-01 (open)",
    );
    expect(
      intervalText({ valid_from: "2026-03-01T09:00:00Z", valid_to: "2026-03-09T17:00:00Z" }, { dateOnly: true }),
    ).toBe("2026-03-01 – 2026-03-09");
  });
});
