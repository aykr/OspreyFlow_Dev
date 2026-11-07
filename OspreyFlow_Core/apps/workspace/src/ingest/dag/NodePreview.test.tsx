// @vitest-environment jsdom
// *Preview* on one node (ADR-140 decision 14): the rows a source reads, the graph Map would make,
// each read with the person's own token through the existing routes only, so the server's masking
// is the Preview's (rule 4; `tests/ingest/test_node_preview_access.py` proves those reads).
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("../../canvas/GlassCanvas", () => ({ GlassCanvas: () => <p>dry-run-graph</p> }));

import { NodePreview, PREVIEW_ROWS } from "./NodePreview";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

function serve(lastRow: number, masked = false) {
  const calls: { url: string; method: string; auth: string | null }[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      const path = new URL(String(url)).pathname;
      calls.push({ url: path, method: init?.method ?? "GET", auth: new Headers(init?.headers).get("Authorization") });
      const sample = path.match(/\/map\/sample-rows\/(\d+)$/);
      if (sample) {
        const index = Number(sample[1]);
        return new Response(JSON.stringify({ row_index: index, values: { caller: masked ? "Xxx-0000" : `SYN-${index}` },
          values_masked: masked, is_last_row: index === lastRow }));  // prettier-ignore
      }
      if (path.endsWith("/verify"))
        return new Response(JSON.stringify({ rows_read: 3, sample_is_whole_source: true, values_masked: false,
          entities_by_type: { Person: { created: 2, referenced: 1 } }, edges_by_type: { KNOWS: { created: 1 } },
          rejections: [{ reason: "bad number", count: 1, samples: [] }], nodes: [], edges: [] }));  // prettier-ignore
      if (path === "/v1/ontology") return new Response(JSON.stringify({ version: 1, entity_types: [], edge_types: [] }));
      return new Response("{}", { status: 404 });
    }),
  );
  return calls;
}

const props = { apiBaseUrl: "http://studio.invalid", bearerToken: "persons-own-token", investigationId: "inv-1", recipeId: "r1" };

describe("Preview on a node", () => {
  it("reads a source's rows from row 0 until the last, with the person's own token, and nothing else", async () => {
    const calls = serve(2);
    render(<NodePreview {...props} node={{ id: "s", kind: "source", label: "Call log", config: {} }} />);
    fireEvent.click(screen.getByRole("button", { name: "Run preview" }));
    expect(await screen.findByText("A sample: the first 3 rows.")).toBeTruthy();
    expect(calls.map((c) => c.url)).toEqual([0, 1, 2].map((i) => `/v1/investigations/inv-1/ingest/recipes/r1/map/sample-rows/${i}`));
    expect(calls.every((c) => c.auth === "Bearer persons-own-token")).toBe(true);
    expect(screen.getByText("SYN-2")).toBeTruthy();
  });

  it("stops at its cap and says the source has more", async () => {
    const calls = serve(99);
    render(<NodePreview {...props} node={{ id: "s", kind: "source", label: "Call log", config: {} }} />);
    fireEvent.click(screen.getByRole("button", { name: "Run preview" }));
    expect(await screen.findByText(`A sample: the first ${PREVIEW_ROWS} rows, and the source has more.`)).toBeTruthy();
    expect(calls).toHaveLength(PREVIEW_ROWS);
  });

  it("shows the server's masked values as given, and says they are masked", async () => {
    serve(0, true);
    render(<NodePreview {...props} node={{ id: "s", kind: "profile", label: "Profile", config: {} }} />);
    fireEvent.click(screen.getByRole("button", { name: "Run preview" }));
    expect(await screen.findByText(/masked to their shape/)).toBeTruthy();
    expect(screen.getByText("Xxx-0000")).toBeTruthy();
  });

  it("previews Map as the graph the dry run would make, through the dry run alone", async () => {
    const calls = serve(0);
    render(<NodePreview {...props} node={{ id: "m", kind: "map", label: "Map", config: {} }} />);
    fireEvent.click(screen.getByRole("button", { name: "Run preview" }));
    expect(await screen.findByText("From a sample of 3 rows: 2 would be created, 1 referenced, 1 links; 1 rows rejected.")).toBeTruthy();
    expect(screen.getByText("dry-run-graph")).toBeTruthy();
    expect(calls.filter((c) => c.method === "POST").map((c) => c.url)).toEqual(["/v1/investigations/inv-1/ingest/recipes/r1/verify"]);
    expect(calls.every((c) => c.auth === "Bearer persons-own-token")).toBe(true);
  });

  it("asks nothing for a step with no preview yet", () => {
    const calls = serve(0);
    render(<NodePreview {...props} node={{ id: "x", kind: "extract", label: "Extract", config: {} }} />);
    expect(screen.getByText(/no preview yet/)).toBeTruthy();
    expect(calls).toHaveLength(0);
  });
});
