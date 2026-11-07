// @vitest-environment jsdom
//
// ADR-127 decision 3, Amendment 2 (B2-2b): Map reads the columns Connect declared for a marking
// from the draft's handling, offers an element exactly those, tells the analyst which declared part
// an element leaves unbound, saves the binding into the template, and shows the server's own cause
// when it refuses the save.
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { RowTemplate } from "../../../../../packages/schemas/generated";
import type { MapCanvasProps } from "./MapCanvas";
import { MapScreen } from "./MapScreen";

const ONTOLOGY = {
  version: 1,
  entity_types: [{ name: "Endpoint", pole_class: "object", channel: "ochre", shape: "circle" }],
  edge_types: [],
};

const draftHandling: { current: Record<string, unknown> } = { current: {} };
const saves: RowTemplate[] = [];
const refusal: { current: Error | null } = { current: null };

vi.mock("../api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../api")>();
  return {
    ...actual,
    fetchDraft: vi.fn(async () => ({
      id: "r1",
      label: "Carrier B",
      row_template: null,
      unmapped_fields: [],
      handling: draftHandling.current,
    })),
    fetchProfile: vi.fn(async () => ({ columns: [{ name: "marking" }, { name: "id" }] })),
    fetchOntologySchema: vi.fn(async () => ONTOLOGY),
    fetchTransforms: vi.fn(async () => []),
    fetchHandlingScheme: vi.fn(async () => ({
      name: "uk-le",
      classification: ["PUBLIC", "OFFICIAL", "SECRET"],
      handling_codes: { P: { label: "Permissive", dissemination: "permitted" } },
    })),
    fetchSampleRow: vi.fn(async () => null),
    updateRowTemplate: vi.fn(async (_u: string, _t: string, _i: string, _r: string, template: RowTemplate) => {
      saves.push(template);
      if (refusal.current) throw refusal.current;
      return { id: "r1", label: "Carrier B", row_template: template, unmapped_fields: [], handling: draftHandling.current };
    }),
  };
});

vi.mock("./MapCanvas", () => ({
  MapCanvas: ({ template, onSelect }: MapCanvasProps) => (
    <div>
      {template.entities.map((e) => (
        <button key={e.ref} onClick={() => onSelect({ kind: "entity", ref: e.ref })}>
          node {e.ref}
        </button>
      ))}
    </div>
  ),
}));

beforeEach(() => {
  draftHandling.current = { classification: "OFFICIAL", handling_columns: { classification: "marking" } };
  saves.length = 0;
  refusal.current = null;
});
afterEach(cleanup);

async function mountWithAnEntity() {
  render(
    <MapScreen apiBaseUrl="" investigationId="inv-1" bearerToken="tok" recipeId="r1" onBack={() => undefined} />,
  );
  fireEvent.click(await screen.findByText("+ entity"));
  fireEvent.click(screen.getByLabelText("Override handling for this element"));
}

const classificationBox = () => screen.getByLabelText("Classification for this element") as HTMLSelectElement;

describe("Map and the columns Connect declared", () => {
  it("offers the declared column for a part, and nothing for a part Connect did not declare", async () => {
    await mountWithAnEntity();
    const option = (box: HTMLSelectElement) => Array.from(box.options).find((o) => o.value === "__column__")!;
    expect(option(classificationBox()).disabled).toBe(false);
    expect(option(classificationBox()).textContent).toContain("marking");
    expect(option(screen.getByLabelText("Handling code for this element") as HTMLSelectElement).disabled).toBe(true);
  });

  it("tells the analyst a declared part the new element does not bind, then stops once it does", async () => {
    await mountWithAnEntity();
    expect(screen.getByRole("status").textContent).toMatch(/does not bind Classification/);
    fireEvent.change(classificationBox(), { target: { value: "__column__" } });
    expect(screen.queryByRole("status")).toBeNull();
  });

  it("saves the binding into the template as {field: <column>}", async () => {
    await mountWithAnEntity();
    fireEvent.change(classificationBox(), { target: { value: "__column__" } });
    fireEvent.click(screen.getByRole("button", { name: "Save draft" }));
    await waitFor(() => expect(saves).toHaveLength(1));
    expect(saves[0]!.entities[0]!.handling).toEqual({ classification: { field: "marking" } });
  });

  it("shows the server's cause for a refused save, word for word", async () => {
    const { RowTemplateSaveError } = await import("../api");
    const cause =
      "element 'e1' does not bind classification, which the source declares in column 'marking'.";
    refusal.current = new RowTemplateSaveError("recipe_rule", cause);
    await mountWithAnEntity();
    fireEvent.click(screen.getByRole("button", { name: "Save draft" }));
    const alert = await screen.findByText(cause);
    expect(alert.getAttribute("role")).toBe("alert");
  });
});
