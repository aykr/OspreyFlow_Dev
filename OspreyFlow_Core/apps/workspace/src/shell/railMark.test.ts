// ADR-145 Amendment 14 decision 3: one place, one marker. A place is pressed while it is the view open; a
// panel's opener is never pressed, only expanded while its panel is open.
import { describe, expect, it } from "vitest";

import { EXPLORE_DETAILS, ON_THE_RAIL, PANEL_OPENERS, railMark } from "./railLayout";

describe("railMark", () => {
  it("presses the place open and nothing else; expands a panel's opener and never presses it", () => {
    const state = { view: "dashboards", open: new Set(["cases", "history"] as const) };
    const marks = Object.fromEntries([...ON_THE_RAIL, ...EXPLORE_DETAILS].map((id) => [id, railMark(id, state)]));
    expect(marks).toEqual({
      cases: { expanded: true },
      explore: { expanded: false },
      questions: { expanded: false },
      dashboards: { pressed: true },
      history: { expanded: true },
      ownership: { pressed: false },
      strength: { pressed: false },
    });
  });

  it("names every panel opener among the rail's entries", () => {
    for (const id of PANEL_OPENERS) expect([...ON_THE_RAIL, ...EXPLORE_DETAILS]).toContain(id);
  });
});
