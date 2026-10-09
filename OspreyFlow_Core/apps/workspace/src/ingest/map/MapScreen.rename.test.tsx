// @vitest-environment jsdom
//
// 9 October 2026, the data engineer's journey: typing a new Ref for an entity in Map did nothing.
// The screen applied an entity's change by looking the entity up by its *new* ref, found none and
// dropped the change, so an entity could never be renamed (`rowTemplate.test.ts` already expected
// renamed refs, but only of a pure function, never of the screen). Renaming carries the entity's
// links with it, and a ref another entity holds is refused.
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { MapCanvasProps } from "./MapCanvas";
import { MapScreen } from "./MapScreen";

const ONTOLOGY = {
  version: 1,
  entity_types: [{ name: "Endpoint", pole_class: "object", channel: "ochre", shape: "circle" }],
  edge_types: [{ name: "COMMUNICATED_WITH", from: ["Endpoint"], to: ["Endpoint"] }],
};

vi.mock("../api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../api")>();
  return {
    ...actual,
    fetchDraft: vi.fn(async () => ({
      id: "r1",
      label: "Carrier B",
      row_template: null,
      unmapped_fields: [],
      handling: { classification: "OFFICIAL", handling_code: "P", owning_unit: "unit-1", originator: "unit-1" },
    })),
    fetchProfile: vi.fn(async () => ({ columns: [] })),
    fetchOntologySchema: vi.fn(async () => ONTOLOGY),
    fetchTransforms: vi.fn(async () => []),
    fetchHandlingScheme: vi.fn(async () => ({ classifications: [], handling_codes: [] })),
    fetchSampleRow: vi.fn(async () => null),
  };
});

// The Sigma canvas, as one button per entity and a line per link, so a test can pick an entity and
// read what the template now holds.
vi.mock("./MapCanvas", () => ({
  MapCanvas: ({ template, onSelect }: MapCanvasProps) => (
    <div>
      {template.entities.map((e) => (
        <button key={e.ref} onClick={() => onSelect({ kind: "entity", ref: e.ref })}>
          node {e.ref}
        </button>
      ))}
      {(template.edges ?? []).map((edge, i) => (
        <span key={i}>{`link ${edge.from}→${edge.to}`}</span>
      ))}
    </div>
  ),
}));

afterEach(cleanup);

async function mount(): Promise<void> {
  render(
    <MapScreen apiBaseUrl="" investigationId="inv-1" bearerToken="tok" recipeId="r1" onBack={() => undefined} />,
  );
  await screen.findByText("+ entity");
}

function refField(): HTMLInputElement {
  return screen.getByDisplayValue(/^(e\d+|a|b)$/) as HTMLInputElement;
}

describe("an entity's ref can be renamed in Map", () => {
  it("takes the new ref", async () => {
    await mount();
    fireEvent.click(screen.getByText("+ entity"));
    fireEvent.change(refField(), { target: { value: "a" } });
    expect(screen.getByText("node a")).toBeTruthy();
    expect(screen.queryByText("node e1")).toBeNull();
    expect(refField().value).toBe("a");
  });

  it("carries the entity's links with it", async () => {
    await mount();
    fireEvent.click(screen.getByText("+ entity"));
    fireEvent.click(screen.getByText("+ entity"));
    fireEvent.click(screen.getByText("+ link"));
    fireEvent.click(screen.getByText("node e1"));
    fireEvent.click(screen.getByText("node e2"));
    expect(screen.getByText("link e1→e2")).toBeTruthy();
    fireEvent.click(screen.getByText("node e1"));
    fireEvent.change(refField(), { target: { value: "a" } });
    expect(screen.getByText("link a→e2")).toBeTruthy();
  });

  it("refuses a ref another entity holds", async () => {
    await mount();
    fireEvent.click(screen.getByText("+ entity"));
    fireEvent.click(screen.getByText("+ entity"));
    fireEvent.change(refField(), { target: { value: "e1" } });
    expect(screen.getByText("node e2")).toBeTruthy();
    expect(screen.getAllByText("node e1")).toHaveLength(1);
  });
});
