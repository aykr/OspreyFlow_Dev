// ADR-110 decision 7: the structured choices (hourly, daily, weekdays, weekly, or an advanced cron
// expression) and the cron each saves as — and an existing schedule read back as the same choice,
// so reopening the Publish screen never turns a daily schedule into an "advanced" one.
import { describe, expect, it } from "vitest";

import { choiceOf, cronOf, type ScheduleChoice } from "./scheduleChoice";

const CASES: [ScheduleChoice, string][] = [
  [{ kind: "hourly", minute: 0 }, "0 * * * *"],
  [{ kind: "hourly", minute: 30 }, "30 * * * *"],
  [{ kind: "daily", time: "06:00" }, "0 6 * * *"],
  [{ kind: "daily", time: "18:45" }, "45 18 * * *"],
  [{ kind: "weekdays", time: "07:30" }, "30 7 * * 1-5"],
  [{ kind: "weekly", day: 1, time: "09:15" }, "15 9 * * 1"],
  [{ kind: "weekly", day: 0, time: "23:00" }, "0 23 * * 0"],
];

describe("schedule choices", () => {
  it.each(CASES)("%j saves as %s and reads back as itself", (choice, cron) => {
    expect(cronOf(choice)).toBe(cron);
    expect(choiceOf(cron)).toEqual(choice);
  });

  it("keeps any other expression as advanced, unchanged", () => {
    expect(choiceOf("0 6 1 * *")).toEqual({ kind: "cron", cron: "0 6 1 * *" });
    expect(cronOf({ kind: "cron", cron: "  0 6 1 * * " })).toBe("0 6 1 * *");
  });

  it("has no cron when not scheduled, and reads no schedule as not scheduled", () => {
    expect(cronOf({ kind: "none" })).toBeNull();
    expect(choiceOf(null)).toEqual({ kind: "none" });
    expect(choiceOf("")).toEqual({ kind: "none" });
  });

  it("gives no cron for a time that is not a time, rather than a wrong one", () => {
    expect(cronOf({ kind: "daily", time: "" })).toBeNull();
    expect(cronOf({ kind: "daily", time: "25:00" })).toBeNull();
    expect(cronOf({ kind: "hourly", minute: 60 })).toBeNull();
  });
});
