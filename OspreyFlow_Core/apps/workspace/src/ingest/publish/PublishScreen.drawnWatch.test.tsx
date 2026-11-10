// @vitest-environment jsdom
// L3.H1 (ADR-146 decision 4): a run's report says how many drawn-watch alerts the load raised for
// the one who ran it, in words, beside the counts; nothing when none, and nothing when the counts
// are withheld (the Conduit sends none then: `report_view`).
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { StudioRecipeDraft } from "../../../../../packages/schemas/generated";
import { drawnWatchWords } from "../../boards/drawnWatchWords";
import { PublishScreen } from "./PublishScreen";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const PUBLISHED = {
  recipe_id: "r1", version: 2, status: "published", label: "Nominals", connector_profile: "generic-csv",
  source_location: "/exports/a.csv", handling: {}, legal_basis: "RIPA s22", owning_unit: "unit-1",
  created_by: "a1", created_at: "2026-10-10T09:00:00Z", git_path: "recipes/r1.yaml", pipeline: null,
  unmapped_fields: [], ready_for_profile: true,
} as unknown as StudioRecipeDraft; // prettier-ignore

const REPORT = { load_id: "L2", recipe_id: "r1", recipe_version: 2, rows_read: 4, rows_deduplicated: 0, nodes_created: 4, nodes_referenced: 0, edges_created: 0, rejections: [] };

function serve(body: unknown) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      const path = String(url);
      const json = (status: number, payload: unknown) => ({ ok: status < 400, status, json: async () => payload }) as Response;
      if (path.endsWith("/run") && (init?.method ?? "GET") === "POST") return json(200, body);
      if (/\/ingest\/recipes\/r1$/.test(path)) return json(200, PUBLISHED);
      return json(404, { error: "not_found" });
    }),
  );
}

async function runNow() {
  render(<PublishScreen apiBaseUrl="http://api" bearerToken="t" recipeId="r1" investigationId="inv-1" onBack={() => undefined} mode="operate" />);
  fireEvent.click(await screen.findByRole("button", { name: /Run now/ }));
}

describe("a run's drawn-watch count", () => {
  it("is said in words, in the singular and the plural", () => {
    expect(drawnWatchWords(1)).toBe("This load raised 1 alert on your drawn items: it is in Rules and Monitoring › Alerts");
    expect(drawnWatchWords(3)).toBe("This load raised 3 alerts on your drawn items: they are in Rules and Monitoring › Alerts");
  });

  it("is said in the load result beside the counts", async () => {
    serve({ ...REPORT, drawn_watch_alerts: 2 });
    await runNow();
    expect(await screen.findByText(drawnWatchWords(2))).toBeTruthy();
    expect(screen.getByText("Nodes created: 4")).toBeTruthy();
  });

  it.each([
    ["the load met none", { ...REPORT, drawn_watch_alerts: 0 }],
    ["the report does not carry it", REPORT],
  ])("says nothing when %s", async (_, body) => {
    serve(body);
    await runNow();
    await screen.findByText("Nodes created: 4");
    expect(screen.queryByText(/on your drawn items/)).toBeNull();
  });

  it("says nothing when the counts are withheld (the Conduit sends none then)", async () => {
    serve({ load_id: "L2", recipe_id: "r1", recipe_version: 2, withheld: true, expert_steps: [] });
    await runNow();
    expect(await screen.findByText(/Counts withheld/)).toBeTruthy();
    expect(screen.queryByText(/on your drawn items/)).toBeNull();
  });
});
