// @vitest-environment jsdom
// ADR-127 decision 5, Amendment 10 (unit B2-5b): Verify counts the rows the case already holds as
// a run would, and meets the same two refusals in words. It goes through the real fetch wrappers,
// so what a server's 409 body says is what the screen shows.
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("../../canvas/GlassCanvas", () => ({
  GlassCanvas: () => <div>preview canvas</div>,
}));

import { VerifyScreen } from "./VerifyScreen";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const REPORT = {
  rows_read: 40,
  sample_is_whole_source: true,
  rows_deduplicated: 3,
  nodes: [],
  edges: [],
  entities_by_type: {},
  edges_by_type: {},
  rejections: [],
};

function serve(verify: { status: number; body: unknown }) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      const path = String(url);
      const method = init?.method ?? "GET";
      const json = (status: number, payload: unknown) =>
        ({ ok: status < 400, status, json: async () => payload }) as Response;
      if (path.endsWith("/verify") && method === "POST") return json(verify.status, verify.body);
      if (path.endsWith("/v1/ontology")) return json(200, { entity_types: [], edge_types: [] });
      if (/\/ingest\/recipes\/r1$/.test(path)) return json(200, { label: "Carrier B intake" });
      return json(404, { error: "not_found" });
    }),
  );
}

async function runVerify() {
  render(<VerifyScreen apiBaseUrl="http://api" investigationId="inv-1" bearerToken="t" recipeId="r1" onBack={() => undefined} />);
  fireEvent.click(await screen.findByRole("button", { name: /Run verify/i }));
}

describe("Verify: a dry run into a case that already holds rows", () => {
  it("says how many rows the case already holds, as a run would skip them", async () => {
    serve({ status: 200, body: { ...REPORT, rows_already_loaded: 37 } });
    await runVerify();
    expect(await screen.findByText("37 rows already loaded into this case, would be skipped")).toBeTruthy();
    // The duplicates folded within the file are a different count and stay as they were.
    expect(screen.getByText(/3 deduplicated/)).toBeTruthy();
  });

  it("says it in the singular for one row", async () => {
    serve({ status: 200, body: { ...REPORT, rows_already_loaded: 1 } });
    await runVerify();
    expect(await screen.findByText("1 row already loaded into this case, would be skipped")).toBeTruthy();
  });

  it("says nothing about it when none were already loaded", async () => {
    serve({ status: 200, body: { ...REPORT, rows_already_loaded: 0 } });
    await runVerify();
    await screen.findByText(/40 row\(s\) read/);
    expect(screen.queryByText(/already loaded into this case/)).toBeNull();
  });

  it("reads a changed deduplicate key as the words the server gave, with the count and no id", async () => {
    const message =
      "this recipe's `deduplicate` has changed since rows were loaded into this case: revert the 1 load(s) that kept keys under the earlier definition, then run it again";
    serve({ status: 409, body: { error: "deduplicate_changed", loads: 1, message } });
    await runVerify();
    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toContain("revert the 1 load(s)");
    expect(alert.textContent).not.toMatch(/409|deduplicate_changed|unknown_error|POST /);
  });

  it("reads a run already in progress as the words the server gave", async () => {
    const message = "another run of this recipe into this case is in progress; run it again when it has finished";
    serve({ status: 409, body: { error: "run_in_progress", message } });
    await runVerify();
    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toContain("another run of this recipe into this case is in progress");
    expect(alert.textContent).not.toMatch(/409|run_in_progress|unknown_error|POST /);
  });
});
