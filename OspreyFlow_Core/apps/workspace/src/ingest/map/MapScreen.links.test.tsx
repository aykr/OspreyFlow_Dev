// @vitest-environment jsdom
//
// ADR-127 Amendment 13's recorded gap (rule 13), through the whole screen: a link in the row template
// is listed beside the canvas and opens in the inspector when chosen; a link is made from the two
// ends and the type chosen in the list's own form and arrives selected; and the saved row template
// carries what was done. The canvas is a stand-in with no keyboard path of its own, as the real one
// has none, so everything below is reached through the list.
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { RowTemplate } from "../../../../../packages/schemas/generated";
import { MapScreen } from "./MapScreen";

const ONTOLOGY = {
  version: 1,
  entity_types: [
    {
      name: "Endpoint",
      pole_class: "object",
      channel: "ochre",
      shape: "circle",
      properties: [{ name: "value_normalised", type: "string" }],
    },
  ],
  edge_types: [
    { name: "COMMUNICATED_WITH", from: ["Endpoint"], to: ["Endpoint"], temporal: true, basis: "direct" },
    { name: "OWNS", from: ["Endpoint"], to: ["Endpoint"], basis: "direct" },
  ],
};
const TEMPLATE: RowTemplate = {
  entities: [
    { ref: "a", pole_class: "object", type: "Endpoint", on_match: "create", properties: {} },
    { ref: "b", pole_class: "object", type: "Endpoint", on_match: "create", properties: {} },
  ],
  edges: [{ type: "COMMUNICATED_WITH", from: "a", to: "b", properties: {} }],
} as unknown as RowTemplate;

const saved: RowTemplate[] = [];

vi.mock("../api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../api")>();
  return {
    ...actual,
    fetchDraft: vi.fn(async () => ({
      recipe_id: "r1",
      label: "Carrier B",
      row_template: TEMPLATE,
      unmapped_fields: [],
      handling: { classification: "OFFICIAL", handling_code: "P", owning_unit: "unit-1", originator: "unit-1" },
    })),
    fetchProfile: vi.fn(async () => ({
      columns: [{ name: "started" }, { name: "ended" }].map((c) => ({ ...c, sample_size: 1, null_count: 0, distinct_count: 1 })),
    })),
    fetchOntologySchema: vi.fn(async () => ONTOLOGY),
    fetchTransforms: vi.fn(async () => [{ name: "datetime", arity: 1 }]),
    fetchHandlingScheme: vi.fn(async () => ({ classification: ["OFFICIAL"], handling_codes: { P: { label: "P" } } })),
    fetchSampleRow: vi.fn(async () => null),
    updateRowTemplate: vi.fn(async (_a: string, _b: string, _c: string, _d: string, template: RowTemplate) => {
      saved.push(template);
      return { recipe_id: "r1", label: "Carrier B", row_template: template, unmapped_fields: [], handling: {} };
    }),
  };
});

vi.mock("./MapCanvas", () => ({ MapCanvas: () => <div>canvas</div> }));

afterEach(() => {
  cleanup();
  saved.length = 0;
});

async function mount() {
  render(<MapScreen apiBaseUrl="" investigationId="inv-1" bearerToken="tok" recipeId="r1" onBack={() => undefined} />);
  await screen.findByText("+ entity");
}

describe("Map: the links are reachable without a pointer", () => {
  it("lists the template's link beside the canvas", async () => {
    await mount();
    const list = screen.getByRole("list", { name: "Links" });
    expect(within(list).getByRole("button", { name: "Link 1: COMMUNICATED_WITH, a to b" })).toBeTruthy();
  });

  it("opens a link in the inspector when it is chosen from the list", async () => {
    await mount();
    expect(screen.queryByLabelText("When it occurred")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Link 1: COMMUNICATED_WITH, a to b" }));
    expect(screen.getByLabelText("When it occurred")).toBeTruthy();
  });

  it("binds its time and its end from columns, and the saved row template carries both", async () => {
    await mount();
    fireEvent.click(screen.getByRole("button", { name: "Link 1: COMMUNICATED_WITH, a to b" }));
    fireEvent.change(screen.getByLabelText("When it occurred"), { target: { value: "column" } });
    fireEvent.change(screen.getByLabelText("When it ended"), { target: { value: "column" } });
    fireEvent.change(screen.getByLabelText("Column holding when it ended"), { target: { value: "ended" } });
    fireEvent.click(screen.getByRole("button", { name: "Save draft" }));
    await waitFor(() => expect(saved).toHaveLength(1));
    const [edge] = saved[0]!.edges ?? [];
    expect(edge!.temporal).toEqual({
      at: { field: "started" },
      valid_to: { field: "ended", transform: "datetime" },
    });
  });

  it("makes a link from the ends and the type chosen, and selects it", async () => {
    await mount();
    fireEvent.change(screen.getByLabelText("From entity"), { target: { value: "b" } });
    fireEvent.change(screen.getByLabelText("To entity"), { target: { value: "a" } });
    fireEvent.change(screen.getByLabelText("Link type"), { target: { value: "OWNS" } });
    fireEvent.click(screen.getByRole("button", { name: "Add link" }));
    // It is in the list, pressed, and open in the inspector (its type select shows OWNS too, beside
    // the form's own).
    const added = screen.getByRole("button", { name: "Link 2: OWNS, b to a" });
    expect(added.getAttribute("aria-pressed")).toBe("true");
    expect(screen.getAllByDisplayValue("OWNS")).toHaveLength(2);
    fireEvent.click(screen.getByRole("button", { name: "Save draft" }));
    await waitFor(() => expect(saved).toHaveLength(1));
    expect(saved[0]!.edges).toEqual([
      { type: "COMMUNICATED_WITH", from: "a", to: "b", properties: {} },
      { type: "OWNS", from: "b", to: "a", properties: {} },
    ]);
  });

  it("keeps the mouse path: the '+ link' button is still there", async () => {
    await mount();
    expect(screen.getByRole("button", { name: "+ link" })).toBeTruthy();
  });
});

describe("Map: the entities are reachable without a pointer", () => {
  it("lists the template's entities, and chooses one into the inspector", async () => {
    await mount();
    const list = screen.getByRole("list", { name: "Entities" });
    expect(within(list).getAllByRole("button").map((b) => b.getAttribute("aria-label"))).toEqual([
      "Entity 1: a (Endpoint)",
      "Entity 2: b (Endpoint)",
    ]);
    expect(screen.queryByLabelText("Entity ref")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Entity 2: b (Endpoint)" }));
    expect((screen.getByLabelText("Entity ref") as HTMLInputElement).value).toBe("b");
    expect(screen.getByRole("button", { name: "Entity 2: b (Endpoint)" }).getAttribute("aria-pressed")).toBe("true");
  });

  it("renames the chosen entity, which the list and the saved template follow", async () => {
    await mount();
    fireEvent.click(screen.getByRole("button", { name: "Entity 1: a (Endpoint)" }));
    fireEvent.change(screen.getByLabelText("Entity ref"), { target: { value: "payer" } });
    expect(screen.getByRole("button", { name: "Entity 1: payer (Endpoint)" }).getAttribute("aria-pressed")).toBe("true");
    // The link it ends follows its new ref.
    expect(screen.getByRole("button", { name: "Link 1: COMMUNICATED_WITH, payer to b" })).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Save draft" }));
    await waitFor(() => expect(saved).toHaveLength(1));
    expect(saved[0]!.entities.map((e) => e.ref)).toEqual(["payer", "b"]);
    expect(saved[0]!.edges![0]).toMatchObject({ from: "payer", to: "b" });
  });

  it("adds a property to the chosen entity, from a column, and the saved template carries it", async () => {
    await mount();
    fireEvent.click(screen.getByRole("button", { name: "Entity 1: a (Endpoint)" }));
    fireEvent.change(screen.getByLabelText("Add a property"), { target: { value: "value_normalised" } });
    fireEvent.change(screen.getByLabelText("Source column"), { target: { value: "ended" } });
    fireEvent.click(screen.getByRole("button", { name: "Save draft" }));
    await waitFor(() => expect(saved).toHaveLength(1));
    expect(saved[0]!.entities[0]!.properties).toEqual({ value_normalised: { field: "ended" } });
  });

  it("deletes the chosen entity and the links it ends", async () => {
    await mount();
    fireEvent.click(screen.getByRole("button", { name: "Entity 1: a (Endpoint)" }));
    fireEvent.click(screen.getByRole("button", { name: "Delete element" }));
    expect(screen.queryByRole("button", { name: "Entity 1: a (Endpoint)" })).toBeNull();
    expect(screen.queryByRole("list", { name: "Links" })).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Save draft" }));
    await waitFor(() => expect(saved).toHaveLength(1));
    expect(saved[0]!.entities.map((e) => e.ref)).toEqual(["b"]);
    expect(saved[0]!.edges).toEqual([]);
  });

  it("deletes the chosen link and leaves its entities", async () => {
    await mount();
    fireEvent.click(screen.getByRole("button", { name: "Link 1: COMMUNICATED_WITH, a to b" }));
    fireEvent.click(screen.getByRole("button", { name: "Delete element" }));
    expect(screen.queryByRole("list", { name: "Links" })).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Save draft" }));
    await waitFor(() => expect(saved).toHaveLength(1));
    expect(saved[0]!.edges).toEqual([]);
    expect(saved[0]!.entities).toHaveLength(2);
  });
});
