// @vitest-environment jsdom
// ADR-131: a rejected row is stored as its offset under the header, and Verify reads it counted
// from 1, so the first data row is row 1.
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
  rows_read: 2,
  sample_is_whole_source: true,
  rows_deduplicated: 0,
  nodes: [],
  edges: [],
  entities_by_type: {},
  edges_by_type: {},
  rejections: [{ reason: "no date", count: 1, samples: [{ row_index: 0, sample: "{'a': ''}" }] }],
};

describe("Verify: rejected rows", () => {
  it("reads the first data row as row 1", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string, init?: RequestInit) => {
        const path = String(url);
        const json = (status: number, payload: unknown) =>
          ({ ok: status < 400, status, json: async () => payload }) as Response;
        if (path.endsWith("/verify") && init?.method === "POST") return json(200, REPORT);
        if (path.endsWith("/v1/ontology")) return json(200, { entity_types: [], edge_types: [] });
        if (/\/ingest\/recipes\/r1$/.test(path)) return json(200, { label: "Carrier B intake" });
        return json(404, { error: "not_found" });
      }),
    );
    render(<VerifyScreen apiBaseUrl="http://api" investigationId="inv-1" bearerToken="t" recipeId="r1" onBack={() => undefined} />);
    fireEvent.click(await screen.findByRole("button", { name: /Run verify/i }));
    expect(await screen.findByText("row 1: {'a': ''}")).toBeTruthy();
  });
});
