// @vitest-environment jsdom
// The Reports Viewer's journey (ADR-145 Amendment 4 decision 10) across the case switch's reload:
// noted with the case, taken once, for that case alone, and never the alert's address.
import { afterEach, describe, expect, it, vi } from "vitest";

import { INVESTIGATION_ID_SESSION_KEY } from "../investigation/investigationId";
import {
  JOURNEY_KEY,
  journeyWords,
  startJourney,
  takeJourney,
  weeksFor,
  type AlertJourney,
} from "./journey";

afterEach(() => sessionStorage.clear());

const JOURNEY: AlertJourney = {
  to: "figures", caseId: "case-9", alertId: "a14", title: "Structuring alert in Operation Kestrel", rule: { label: "typology", typology: "structuring" }, weeks: 4,
}; // prettier-ignore

describe("the Reports Viewer's journey", () => {
  it("opens the alert's case as any case switch does, never the alert's address", () => {
    const go = vi.fn();
    startJourney(JOURNEY, go);
    expect(go).toHaveBeenCalledWith("/?investigation=case-9&from=case");
    expect(String(go.mock.calls[0]![0])).not.toContain("/alerts/");
    expect(sessionStorage.getItem(INVESTIGATION_ID_SESSION_KEY)).toBe("case-9");
  });

  it("is taken once, for its own case alone", () => {
    startJourney(JOURNEY, () => {});
    expect(takeJourney("case-9")).toEqual(JOURNEY);
    expect(takeJourney("case-9")).toBeNull();
    startJourney(JOURNEY, () => {});
    expect(takeJourney("another-case")).toBeNull();
    expect(sessionStorage.getItem(JOURNEY_KEY)).toBeNull();
  });

  it("drops a note it did not write", () => {
    sessionStorage.setItem(
      JOURNEY_KEY,
      JSON.stringify({ to: "alert", caseId: "case-9", alertId: "a14" }),
    );
    expect(takeJourney("case-9")).toBeNull();
    sessionStorage.setItem(JOURNEY_KEY, "{not json");
    expect(takeJourney("case-9")).toBeNull();
  });

  it("opens on the shortest period that holds the alert", () => {
    const now = new Date("2026-11-08T12:00:00Z");
    expect(weeksFor("2026-11-07T12:00:00Z", now)).toBe(4);
    expect(weeksFor("2026-09-01T12:00:00Z", now)).toBe(12);
    expect(weeksFor("2026-06-01T12:00:00Z", now)).toBe(26);
    expect(weeksFor("2024-01-01T12:00:00Z", now)).toBe(52);
  });

  it("names the alert by the title Home showed for it", () => {
    expect(journeyWords(JOURNEY)).toBe("alert: Structuring alert in Operation Kestrel");
  });
});
