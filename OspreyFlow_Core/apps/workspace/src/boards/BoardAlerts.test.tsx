// @vitest-environment jsdom
// The boards' Alerts panel (ADR-146 decision 9): the case's open alerts, as the Conduit counts them
// for this reader, on a drawing board; the rows are words there, never a way to work an alert; a
// reader the case's figures are not for is shown no panel.
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { MonitoringFigures } from "../../../../packages/schemas/generated";
import { BOARD_ALERT_WEEKS, BoardAlerts } from "./BoardAlerts";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

// Synthetic (rule 9), as the Conduit counts the case's open alerts for this reader.
const MONITORING: MonitoringFigures = {
  raised_by_rule: [], closed_by_outcome: [], time_to_close: [], hotlist_matches: [], team: [],
  open_by_source: [{ label: "typology", typology: "structuring", age: "under a day", count: 1 }],
};  // prettier-ignore
const API = { apiBaseUrl: "http://conduit.test", bearerToken: "t", investigationId: "c1" };
const json = (status: number, body: unknown) => new Response(JSON.stringify(body), { status });

function conduit(report: Response): string[] {
  const asked: string[] = [];
  vi.stubGlobal("fetch", vi.fn(async (raw: string) => {
    const url = new URL(raw);
    asked.push(`${url.pathname}${url.search}`);
    if (url.pathname.endsWith("/reports")) return report;
    return json(200, [{
      alert: { id: "a1", rule_id: "typology:r", owner_id: "o", mode: "full", referent_node_ids: [],
               created_at: "2026-11-08T09:00:00Z", status: "open", typology: "structuring" },
      summary: "Alpha Ltd a1", kind: "typology" }]);
  }));  // prettier-ignore
  return asked;
}

describe("the boards' Alerts panel", () => {
  it("shows the case's open alerts as the Conduit counts them, as words with nothing to open", async () => {
    const asked = conduit(json(200, { monitoring: MONITORING }));
    render(<BoardAlerts api={API} />);
    expect(await screen.findByRole("table", { name: "Open alerts by source and age" })).toBeTruthy();
    expect(asked).toContain(`/v1/investigations/c1/reports?weeks=${BOARD_ALERT_WEEKS}`);
    await waitFor(() => expect(screen.getByText(/Alpha Ltd a1/)).toBeTruthy());
    expect(screen.queryByRole("button", { name: /open/i })).toBeNull();
  });

  it("is not shown to a reader the case's figures are not for", async () => {
    const asked = conduit(json(403, { error: "forbidden" }));
    const { container } = render(<BoardAlerts api={API} />);
    await waitFor(() => expect(asked.length).toBeGreaterThan(0));
    expect(container.innerHTML).toBe("");
  });
});
