// @vitest-environment jsdom
//
// Migrated in phase 6 from `MapScreen.*.test.tsx`: the same assertions, against the Map editor as the Studio hosts it.
// Build order step 30 (the owner, 4 November 2026; CLAUDE.md rule 7): the Studio's Map names a link
// type as a person reads it ("Held at"), never by its ontology key ("HELD_AT"): in the list of the
// template's links, in the form that makes one, in the inspector of a chosen link, and on the canvas.
// The 3 November rehearsal found the keys on screen. The key stays the value each select sends and
// the template stores. If any of these fails, a link-type key is back on screen.
import Graph from "graphology";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { paletteFor } from "../../color/palette";
import type { OntologySchema, RowTemplate } from "../../../../../packages/schemas/generated";
import { MapEditor } from "./MapEditor";
import { STRIP } from "./mapEditorTestSupport";
import { syncTemplateGraph } from "./mapGraphSync";

// As the NIEM pack declares them: no label, so the name is read in sentence case (ADR-091 decision 2),
// and one with a declared label, which wins.
const ONTOLOGY = {
  version: 14,
  entity_types: [
    { name: "Person", pole_class: "person", channel: "cyan", shape: "circle", properties: [{ name: "prison_number", type: "string" }] },
    { name: "Location", pole_class: "location", channel: "ochre", shape: "pin", properties: [{ name: "name", type: "string" }] },
  ],
  edge_types: [
    { name: "HELD_AT", from: ["Person"], to: ["Location"], basis: "direct", temporal: true },
    { name: "PASSES_ITEMS_TO", from: ["Person"], to: ["Person"], basis: "direct" },
    { name: "LOCATED_AT", from: ["Person"], to: ["Location"], basis: "direct", label: "Seen at" },
  ],
};

const TEMPLATE: RowTemplate = {
  entities: [
    { ref: "prisoner", pole_class: "person", type: "Person", on_match: "create", properties: {} },
    { ref: "cell", pole_class: "location", type: "Location", on_match: "reference", properties: {} },
  ],
  edges: [{ type: "HELD_AT", from: "prisoner", to: "cell", properties: {} }],
} as unknown as RowTemplate;

vi.mock("../api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../api")>();
  return {
    ...actual,
    fetchDraft: vi.fn(async () => ({
      recipe_id: "r1",
      label: "Cell moves",
      row_template: TEMPLATE,
      unmapped_fields: [],
      handling: { classification: "OFFICIAL", handling_code: "P", owning_unit: "unit-1", originator: "unit-1" },
    })),
    fetchProfile: vi.fn(async () => ({
      columns: [{ name: "prison_number" }, { name: "cell" }, { name: "moved_at" }].map((c) => ({
        ...c, sample_size: 1, null_count: 0, distinct_count: 1,
      })),
    })),
    fetchOntologySchema: vi.fn(async () => ONTOLOGY),
    fetchTransforms: vi.fn(async () => [{ name: "datetime", arity: 1 }]),
    fetchHandlingScheme: vi.fn(async () => ({ classification: ["OFFICIAL"], handling_codes: { P: { label: "P" } } })),
    fetchSampleRow: vi.fn(async () => null),
    updateRowTemplate: vi.fn(),
  };
});

vi.mock("./MapCanvas", () => ({ MapCanvas: () => <div>canvas</div> }));

afterEach(cleanup);

async function mount() {
  render(<MapEditor apiBaseUrl="" investigationId="inv-1" bearerToken="tok" recipeId="r1" pipeline={STRIP} mapNodeId="map" onStep={() => undefined} />);
  await screen.findByText("+ entity");
}

describe("the Studio map shows no link-type key (build order step 30)", () => {
  it("the list, the form and the inspector name the type; none shows its key", async () => {
    await mount();
    const link = screen.getByRole("button", { name: "Link 1: Held at, prisoner to cell" });
    fireEvent.click(link);
    await waitFor(() => expect(screen.getByLabelText("When it occurred")).toBeTruthy());
    const shown = document.body.textContent ?? "";
    expect(shown).toContain("Held at");
    for (const key of ["HELD_AT", "PASSES_ITEMS_TO", "LOCATED_AT"]) expect(shown).not.toContain(key);
    for (const element of document.querySelectorAll("[aria-label], [title]")) {
      const said = `${element.getAttribute("aria-label") ?? ""} ${element.getAttribute("title") ?? ""}`;
      expect(said).not.toMatch(/[A-Z]+_[A-Z_]+/);
    }
  });

  it("a declared label wins over the derived one", async () => {
    await mount();
    const offered = [...(screen.getByLabelText("Link type") as HTMLSelectElement).options].map((o) => o.textContent);
    expect(offered).toEqual(["Held at", "Seen at"]);
  });

  it("the canvas draws the link under its name", () => {
    const graph = new Graph();
    syncTemplateGraph(graph, TEMPLATE, ONTOLOGY as unknown as OntologySchema, null, null, paletteFor("light"));
    expect(graph.edges().map((key) => graph.getEdgeAttribute(key, "label"))).toEqual(["Held at"]);
  });
});
