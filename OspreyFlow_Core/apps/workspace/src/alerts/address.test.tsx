// @vitest-environment jsdom
// ADR-146 decision 6: the address asks the Conduit which case the alert is worked in, and a 404 is
// the one answer for an alert that does not exist and for one the reader may not see (rule 3).
import { renderHook, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { INVESTIGATION_ID_SESSION_KEY } from "../investigation/investigationId";
import { alertInItsCaseUrl, evidenceCase, openAlertInItsCase, openRulesOnCase, useAlertAtAddress } from "./address";

afterEach(() => {
  vi.unstubAllGlobals();
  sessionStorage.clear();
});

const json = (status: number, body: unknown) => new Response(JSON.stringify(body), { status });

describe("an alert at its address", () => {
  it("is found in the case the Conduit names, asked for by its id alone", async () => {
    const fetched = vi.fn(async () => json(200, { investigation_id: "c2", explanation: { alert: { id: "a 1" } } }));
    vi.stubGlobal("fetch", fetched);
    const { result } = renderHook(() => useAlertAtAddress("http://x", "t", "a 1"));
    await waitFor(() => expect(result.current?.status).toBe("found"));
    expect(result.current).toMatchObject({ status: "found", caseId: "c2" });
    expect(fetched).toHaveBeenCalledWith("http://x/v1/alerts/a%201", { headers: { Authorization: "Bearer t" } });
  });

  it("is missing on a 404, whatever the reason the Conduit had", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => json(404, { error: "alert_not_found" })));
    const { result } = renderHook(() => useAlertAtAddress("http://x", "t", "a1"));
    await waitFor(() => expect(result.current).toEqual({ status: "missing" }));
  });

  it("says another refusal in words, never as a missing alert", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => json(403, { detail: { error: "place_required" } })));
    const { result } = renderHook(() => useAlertAtAddress("http://x", "t", "a1"));
    await waitFor(() => expect(result.current?.status).toBe("failed"));
  });

  it("asks nothing with no address", () => {
    const fetched = vi.fn();
    vi.stubGlobal("fetch", fetched);
    const { result } = renderHook(() => useAlertAtAddress("http://x", "t", null));
    expect(result.current).toBeNull();
    expect(fetched).not.toHaveBeenCalled();
  });

  it("opens another case on the alert, keeping the address, as every case switch is opened", () => {
    const go = vi.fn();
    openAlertInItsCase("a1", "c 2", go);
    expect(go).toHaveBeenCalledWith("/alerts/a1?investigation=c%202&from=case");
    expect(alertInItsCaseUrl("a1", "c 2")).toBe("/alerts/a1?investigation=c%202&from=case");
    expect(sessionStorage.getItem(INVESTIGATION_ID_SESSION_KEY)).toBe("c 2");
    openRulesOnCase("c3", go);
    expect(go).toHaveBeenLastCalledWith("/rules?investigation=c3&from=case");
  });
});

// The orchestrator's independent review of L2.9, item 6: *Open the evidence* saves into the alert's own
// case, never whichever case happens to be open.
describe("the case Open the evidence saves into", () => {
  const evidence = { alertId: "a1", title: "Structuring", nodeIds: ["n1"], caseId: "c1" };
  const found = (caseId: string) => ({ status: "found" as const, caseId, explanation: { alert: { id: "a1" } } as never });

  it("is the alert's own case, when it is the one open", () => {
    expect(evidenceCase(evidence, "c1", null)).toEqual({ caseId: "c1" });
    expect(evidenceCase(evidence, "c1", { alertId: "a1", state: found("c1") })).toEqual({ caseId: "c1" });
  });

  it("is refused when the alert was read in another case than the one open", () => {
    expect(evidenceCase(evidence, "c2", null)).toEqual({ refused: expect.stringMatching(/another case/) });
    expect(evidenceCase(evidence, null, null)).toEqual({ refused: expect.stringMatching(/another case/) });
  });

  it("is refused when the address says the alert is worked in another case", () => {
    expect(evidenceCase(evidence, "c1", { alertId: "a1", state: found("c2") })).toEqual({ refused: expect.stringMatching(/another case/) });
    // Another alert's address says nothing of this one.
    expect(evidenceCase(evidence, "c1", { alertId: "a9", state: found("c2") })).toEqual({ caseId: "c1" });
  });
});
