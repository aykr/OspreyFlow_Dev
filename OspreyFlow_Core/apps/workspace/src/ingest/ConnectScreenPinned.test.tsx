// @vitest-environment jsdom
//
// ADR-108, 10 October 2026: the Connect gate rehosted whole under a pipeline's source node — found
// missing from phase B when the owner met a source panel of two bare text fields. Pinned to one
// draft, the screen shows that draft's form (file, connector catalogue, marking, legal basis),
// hides the Sources sidebar (the canvas is the navigation), and offers the way back.
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ConnectScreen } from "./ConnectScreen";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const DRAFT = {
  recipe_id: "r1",
  version: 1,
  status: "draft",
  label: "Carrier B intake",
  connector_profile: "generic-csv",
  source_location: "/ingest/carrier-b.csv",
  handling: { classification: "OFFICIAL" },
  legal_basis: "RIPA s22",
  owning_unit: "u",
  created_by: "a",
  created_at: "2026-10-10T00:00:00Z",
  ready_for_profile: true,
};

function stub() {
  const patches: Record<string, unknown>[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      const method = init?.method ?? "GET";
      const path = String(url).replace("http://api", "");
      let body: unknown;
      if (path === "/v1/ingest/connectors")
        body = [{ id: "generic-csv", label: "CSV file", group: "Generic", structured: true, available: true }];
      else if (path === "/v1/handling-scheme")
        body = {
          name: "uk-le",
          classification: ["PUBLIC", "OFFICIAL"],
          handling_codes: { P: { label: "Permissive", dissemination: "permitted" } },
        };
      else if (path === "/v1/investigations/inv-1/ingest/recipes" && method === "GET") body = [DRAFT];
      else if (path === "/v1/investigations/inv-1/ingest/source-files") body = { root: "/r", files: [] };
      else if (path === "/v1/investigations/inv-1/ingest/recipes/r1" && method === "PATCH") {
        patches.push(JSON.parse(String(init?.body)) as Record<string, unknown>);
        body = DRAFT;
      } else throw new Error(`unexpected request ${method} ${path}`);
      return { ok: true, status: 200, json: async () => body };
    }),
  );
  return patches;
}

describe("ConnectScreen pinned to a pipeline's draft", () => {
  it("shows that draft's form without the Sources sidebar, and saves as an update", async () => {
    const patches = stub();
    render(
      <ConnectScreen
        investigationId="inv-1"
        apiBaseUrl="http://api"
        bearerToken="tok"
        recipeId="r1"
        onBack={vi.fn()}
      />,
    );
    const label = await screen.findByDisplayValue("Carrier B intake");
    expect(label).toBeTruthy();
    expect(screen.queryByText("+ New source")).toBeNull();
    expect(screen.queryByRole("button", { name: "Continue to Profile" })).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    await waitFor(() => expect(patches).toHaveLength(1));
    expect(patches[0]!.label).toBe("Carrier B intake");
  });

  it("offers Back to the pipeline, which fires onBack", async () => {
    stub();
    const onBack = vi.fn();
    render(
      <ConnectScreen
        investigationId="inv-1"
        apiBaseUrl="http://api"
        bearerToken="tok"
        recipeId="r1"
        onBack={onBack}
      />,
    );
    fireEvent.click(await screen.findByRole("button", { name: "Back to the pipeline" }));
    expect(onBack).toHaveBeenCalledTimes(1);
  });
});
