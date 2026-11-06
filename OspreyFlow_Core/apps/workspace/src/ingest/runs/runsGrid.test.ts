import { describe, expect, it } from "vitest";

import type { ScheduleRunView } from "../../../../../packages/schemas/generated";
import { lastDays, rowCells, stateOf } from "./runsGrid";

function run(outcome: ScheduleRunView["outcome"], startedAt: string, extra: Partial<ScheduleRunView> = {}): ScheduleRunView {
  return { run_id: `r-${startedAt}`, trigger: "manual", started_at: startedAt, outcome, run_as: "osprey-demo-engineer", ...extra };
}

describe("the Runs grid", () => {
  it("counts back the last days, oldest first, ending today", () => {
    expect(lastDays(new Date("2026-11-05T18:00:00Z"), 3)).toEqual(["2026-11-03", "2026-11-04", "2026-11-05"]);
  });

  it("says a day needed a person when rows were held, even though the run succeeded", () => {
    expect(stateOf([run("succeeded", "2026-11-05T09:00:00Z", { rows_held: 2 })], false)).toBe("attention");
  });

  it("says a day needed a person when a run failed, was refused or was blocked", () => {
    for (const outcome of ["failed", "refused", "blocked"] as const) {
      expect(stateOf([run("succeeded", "2026-11-05T08:00:00Z"), run(outcome, "2026-11-05T09:00:00Z")], false)).toBe("attention");
    }
  });

  it("says succeeded only when every run that day loaded cleanly", () => {
    expect(stateOf([run("succeeded", "2026-11-05T09:00:00Z", { rows_held: 0 })], false)).toBe("succeeded");
  });

  it("marks only today as scheduled, and only when nothing ran", () => {
    const days = ["2026-11-04", "2026-11-05"];
    expect(rowCells([], days, true).map((c) => c.state)).toEqual(["none", "scheduled"]);
    expect(rowCells([run("succeeded", "2026-11-05T05:00:00Z")], days, true).map((c) => c.state)).toEqual(["none", "succeeded"]);
    expect(rowCells([], days, false).map((c) => c.state)).toEqual(["none", "none"]);
  });

  it("puts each run on its own day", () => {
    const cells = rowCells([run("succeeded", "2026-11-04T23:30:00Z"), run("refused", "2026-11-05T00:30:00Z")], ["2026-11-04", "2026-11-05"], false);
    expect(cells.map((c) => [c.state, c.runs.length])).toEqual([["succeeded", 1], ["attention", 1]]);
  });
});
