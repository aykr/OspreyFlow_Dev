// @vitest-environment jsdom
// Rule 3, ADR-127 Amendment 25: releasing held rows loads them, and the route's answer is withheld
// where the releaser may not view every marking the rows were written at. The panel must say so,
// never "0 link(s) made" (ADR-124 option A′: a withheld count says that it withholds).
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { HeldRowsPanel } from "./HeldRowsPanel";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const HELD = {
  id: "h1", investigation_id: "inv-1", recipe_id: "r1", recipe_version: 1, load_id: "L1",
  source: "pid_conflicts.csv", row_index: 4, row: { a: "1" }, rule_id: "rule-1", reason: "no screen",
  handling: { classification: "OFFICIAL", handling_code: "P", originator: "u", owning_unit: "u" },
  held_at: "2026-10-26T09:00:00Z",
};

function serve(release: unknown) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      const json = (payload: unknown) => ({ ok: true, status: 200, json: async () => payload }) as Response;
      if (String(url).endsWith("/release") && init?.method === "POST") return json(release);
      return json([HELD]);
    }),
  );
}

async function release() {
  render(<HeldRowsPanel apiBaseUrl="http://api" bearerToken="t" investigationId="inv-1" level="author" />);
  fireEvent.click(await screen.findByRole("button", { name: "Release and load" }));
  return screen.findByRole("status");
}

describe("HeldRowsPanel", () => {
  it("reads a held row counted from 1 (ADR-131)", async () => {
    serve({ load_id: "L2", edges_created: 0, nodes_created: 0, rule_notes: [] });
    render(<HeldRowsPanel apiBaseUrl="http://api" bearerToken="t" investigationId="inv-1" level="author" />);
    expect(await screen.findByText(/^Row 5: a 1$/)).toBeTruthy();
  });

  it("says how many links a release made", async () => {
    serve({ load_id: "L2", edges_created: 3, nodes_created: 0, rule_notes: [] });
    expect((await release()).textContent).toContain("3 link(s) made");
  });

  it("says counts are withheld, and draws no zero, when the release's answer is withheld", async () => {
    serve({ load_id: "L2", edges_created: 0, nodes_created: 0, rule_notes: [], withheld: true });
    const said = (await release()).textContent ?? "";
    expect(said).toMatch(/Counts withheld — .*above your clearance.*another unit/);
    expect(said).not.toMatch(/link\(s\) made/);
  });
});
