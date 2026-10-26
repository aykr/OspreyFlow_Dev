// @vitest-environment jsdom
// ADR-127 decision 5, Amendment 10 (unit B2-5b): the second run of a published recipe into one case
// must visibly create nothing, and say why. The run report names the rows the case had already
// loaded; the two refusals a deduplicating run can meet are read in words, with no id.
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { StudioRecipeDraft } from "../../../../../packages/schemas/generated";
import { PublishScreen } from "./PublishScreen";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const PUBLISHED = {
  recipe_id: "r1",
  version: 2,
  status: "published",
  label: "Carrier B intake",
  connector_profile: "generic-csv",
  source_location: "/exports/a.csv",
  handling: {},
  legal_basis: "RIPA s22",
  owning_unit: "unit-1",
  created_by: "a1",
  created_at: "2026-10-10T09:00:00Z",
  git_path: "recipes/r1.yaml",
  pipeline: null,
  unmapped_fields: [],
  ready_for_profile: true,
} as unknown as StudioRecipeDraft;

const REPORT = {
  load_id: "L2",
  recipe_id: "r1",
  recipe_version: 2,
  rows_read: 40,
  rows_deduplicated: 0,
  nodes_created: 0,
  nodes_referenced: 0,
  edges_created: 0,
  rejections: [],
};

function serve(run: { status: number; body: unknown }) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      const path = String(url);
      const method = init?.method ?? "GET";
      const json = (status: number, payload: unknown) =>
        ({ ok: status < 400, status, json: async () => payload }) as Response;
      if (path.endsWith("/run") && method === "POST") return json(run.status, run.body);
      if (/\/ingest\/recipes\/r1$/.test(path)) return json(200, PUBLISHED);
      return json(404, { error: "not_found" });
    }),
  );
}

async function runNow() {
  render(
    <PublishScreen apiBaseUrl="http://api" bearerToken="t" recipeId="r1" investigationId="inv-1" onBack={() => undefined} />,
  );
  fireEvent.click(await screen.findByRole("button", { name: /Run now/ }));
}

describe("Publish: a run into a case that already holds its rows", () => {
  it("says how many rows the case already held and skipped, beside the created counts", async () => {
    serve({ status: 200, body: { ...REPORT, rows_already_loaded: 40 } });
    await runNow();
    expect(await screen.findByText("40 rows already loaded into this case, skipped")).toBeTruthy();
    expect(screen.getByText("Nodes created: 0")).toBeTruthy();
  });

  it("says it in the singular for one row", async () => {
    serve({ status: 200, body: { ...REPORT, rows_already_loaded: 1 } });
    await runNow();
    expect(await screen.findByText("1 row already loaded into this case, skipped")).toBeTruthy();
  });

  it("says nothing about it when none were already loaded, or the report does not carry it", async () => {
    serve({ status: 200, body: { ...REPORT, rows_already_loaded: 0 } });
    await runNow();
    await screen.findByText("Nodes created: 0");
    expect(screen.queryByText(/already loaded into this case/)).toBeNull();
  });

  it("says it for a pipeline run too, from the total the run reports", async () => {
    serve({
      status: 200,
      body: {
        load_id: "L3", recipe_id: "r1", recipe_version: 2, branches: [], extracts: [], enriches: [],
        rows_read: 12, nodes_created: 0, nodes_referenced: 0, edges_created: 0, rejections: [],
        rows_already_loaded: 12,
      },
    });
    await runNow();
    expect(await screen.findByText("12 rows already loaded into this case, skipped")).toBeTruthy();
  });

  it("reads a changed deduplicate key as the words the server gave, with the count and no id", async () => {
    const message =
      "this recipe's `deduplicate` has changed since rows were loaded into this case: revert the 2 load(s) that kept keys under the earlier definition, then run it again";
    serve({ status: 409, body: { error: "deduplicate_changed", loads: 2, message } });
    await runNow();
    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toContain("revert the 2 load(s)");
    expect(alert.textContent).toContain("then run it again");
    expect(alert.textContent).not.toMatch(/409|deduplicate_changed|unknown_error/);
    expect(screen.queryByText(/Load id/)).toBeNull();
  });

  it("reads a run already in progress as the words the server gave", async () => {
    const message = "another run of this recipe into this case is in progress; run it again when it has finished";
    serve({ status: 409, body: { error: "run_in_progress", message } });
    await runNow();
    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toContain("another run of this recipe into this case is in progress");
    expect(alert.textContent).not.toMatch(/409|run_in_progress|unknown_error/);
  });
});
