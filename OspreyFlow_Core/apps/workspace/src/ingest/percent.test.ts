// A share of a column's values, as the Profile and Map stages show it. 9 October 2026: 239 of 240
// phone numbers matched and the Profile said "msisdn 100%", which hid the one row that will be
// rejected. A rounded figure must not claim all or none when that is not true.
import { describe, expect, it } from "vitest";

import { percent } from "./percent";

describe("percent", () => {
  it("says 100% only when every value matched", () => {
    expect(percent(1)).toBe("100%");
    expect(percent(239 / 240)).toBe("99.6%");
    expect(percent(0.9999)).toBe("99.9%");
  });

  it("says 0% only when none did", () => {
    expect(percent(0)).toBe("0%");
    expect(percent(1 / 240)).toBe("0.4%");
    expect(percent(0.0001)).toBe("0.1%");
  });

  it("rounds a figure that is neither nearly all nor nearly none", () => {
    expect(percent(0.6)).toBe("60%");
    expect(percent(0.874)).toBe("87%");
  });
});
