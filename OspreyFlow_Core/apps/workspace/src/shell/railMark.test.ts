// ADR-145 Amendments 14 and 15: the rail holds panel openers alone (the owner's navigation decision); an opener
// is never pressed, only expanded while its panel is open. A view's marker is the top bar's view switch.
import { describe, expect, it } from "vitest";

import { EXPLORE_DETAILS, ON_THE_RAIL, PANEL_OPENERS, railMark } from "./railLayout";

describe("railMark", () => {
  it("expands a panel's opener while its panel is open and never presses it; the rail holds openers alone (Amendment 15)", () => {
    const state = { view: "dashboards", open: new Set(["history"] as const) };
    const marks = Object.fromEntries([...ON_THE_RAIL, ...EXPLORE_DETAILS].map((id) => [id, railMark(id, state)]));
    expect(marks).toEqual({ explore: { expanded: false }, questions: { expanded: false }, history: { expanded: true } });
    expect(EXPLORE_DETAILS).toEqual([]);
  });

  it("names every panel opener among the rail's entries", () => {
    for (const id of PANEL_OPENERS) expect([...ON_THE_RAIL, ...EXPLORE_DETAILS]).toContain(id);
  });
});
