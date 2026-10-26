// @vitest-environment jsdom
// ADR-096: the Query builder opens on its preview, the pattern with Preview and Run, and folds the
// rest; Connect appears once there are two nodes to connect.
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { OntologySchema } from "../../../../packages/schemas/generated";
import { QueryBuilderPanel } from "./QueryBuilderPanel";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const SCHEMA = {
  version: 1,
  entity_types: [{ name: "Person", pole_class: "person", channel: "indigo", shape: "circle", identifiers: [] }],
  edge_types: [{ name: "ASSOCIATE_OF", from: ["Person"], to: ["Person"] }],
} as unknown as OntologySchema;

function mount() {
  vi.stubGlobal("fetch", vi.fn(async () => ({ ok: true, status: 200, json: async () => ({ patterns: [] }) })));
  render(<QueryBuilderPanel investigationId="inv-1" apiBaseUrl="http://api.test" bearerToken="tok" schema={SCHEMA} />);
}

const header = (name: string) => screen.getByRole("button", { name });

describe("QueryBuilderPanel parts", () => {
  it("opens on the pattern, with Preview and Run, and folds adding, saving and loading", () => {
    mount();
    expect(header("Pattern").getAttribute("aria-expanded")).toBe("true");
    expect(screen.getByRole("button", { name: "Preview" })).toBeTruthy();
    expect(screen.getByText(/No pattern yet/)).toBeTruthy();
    expect(header("Add to the pattern").getAttribute("aria-expanded")).toBe("false");
    expect(header("Save and load").getAttribute("aria-expanded")).toBe("false");
    expect(screen.queryByRole("button", { name: "Add variable" })).toBeNull(); // hidden while folded
    expect(screen.queryByRole("button", { name: "Connect" })).toBeNull();
  });

  it("opening Add to the pattern offers Add variable, and two nodes bring Connect", () => {
    mount();
    fireEvent.click(header("Add to the pattern"));
    fireEvent.click(screen.getByRole("button", { name: "Add variable" }));
    fireEvent.click(screen.getByRole("button", { name: "Add variable" }));
    expect(screen.getAllByRole("group", { name: /^Pattern node/ })).toHaveLength(2);
    expect(header("Connect").getAttribute("aria-expanded")).toBe("false");
  });
});

// ADR-121: a value field on a node, offered the type's indexed text properties only.
const CONDITION_SCHEMA = {
  version: 1,
  entity_types: [
    {
      name: "Establishment",
      pole_class: "place",
      channel: "teal",
      shape: "square",
      identifiers: [],
      properties: [
        { name: "niu_area", type: "string", indexed: true },
        { name: "soct_region", type: "string", indexed: true },
        { name: "wing", type: "string", indexed: true },
        { name: "block", type: "string", indexed: true },
        { name: "secret_code", type: "string", indexed: true, sensitivity: "high" },
        { name: "note", type: "string" },
      ],
    },
  ],
  edge_types: [],
} as unknown as OntologySchema;

function mountWithConditions() {
  const fetchMock = vi.fn((url: string, init?: { body?: string }) => {
    void init;
    return Promise.resolve({
      ok: true,
      status: 200,
      json: async () => (String(url).endsWith("/preview") ? { estimated_count: 3, is_floor: false } : { patterns: [] }),
    });
  });
  vi.stubGlobal("fetch", fetchMock);
  render(
    <QueryBuilderPanel investigationId="inv-1" apiBaseUrl="http://api.test" bearerToken="tok" schema={CONDITION_SCHEMA} />,
  );
  fireEvent.click(header("Add to the pattern"));
  fireEvent.click(screen.getByRole("button", { name: "Add variable" }));
  return fetchMock;
}

describe("QueryBuilderPanel value field on a node", () => {
  it("offers only the indexed, non-sensitive text properties of the node's type", () => {
    mountWithConditions();
    const property = screen.getByRole("combobox", { name: "Condition property on a" }) as HTMLSelectElement;
    expect(Array.from(property.options).map((o) => o.value)).toEqual(["niu_area", "soct_region", "wing", "block"]);
  });

  it("adds a condition, shows it, and sends it in the preview as PatternNode.where", async () => {
    const fetchMock = mountWithConditions();
    fireEvent.change(screen.getByRole("combobox", { name: "Condition property on a" }), {
      target: { value: "niu_area" },
    });
    fireEvent.change(screen.getByRole("textbox", { name: "Condition value on a" }), { target: { value: "North" } });
    fireEvent.click(screen.getByRole("button", { name: "Add condition on a" }));
    expect(screen.getByText("niu_area = North")).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: "Preview" }));
    await screen.findByText("~3 matches");
    const call = fetchMock.mock.calls.find(([url]) => String(url).endsWith("/patterns/preview"));
    const body = JSON.parse(call?.[1]?.body ?? "{}");
    expect(body.nodes[0].where).toEqual({ niu_area: "North" });
  });

  it("removes a condition by its own button", () => {
    mountWithConditions();
    fireEvent.change(screen.getByRole("textbox", { name: "Condition value on a" }), { target: { value: "North" } });
    fireEvent.click(screen.getByRole("button", { name: "Add condition on a" }));
    fireEvent.click(screen.getByRole("button", { name: "Remove condition niu_area on a" }));
    expect(screen.queryByText("niu_area = North")).toBeNull();
  });

  it("stops offering the field at three conditions", () => {
    mountWithConditions();
    for (const [name, value] of [["niu_area", "A"], ["soct_region", "B"], ["wing", "C"]] as const) {
      fireEvent.change(screen.getByRole("combobox", { name: "Condition property on a" }), { target: { value: name } });
      fireEvent.change(screen.getByRole("textbox", { name: "Condition value on a" }), { target: { value } });
      fireEvent.click(screen.getByRole("button", { name: "Add condition on a" }));
    }
    expect(screen.getAllByText(/ = /)).toHaveLength(3);
    expect(screen.queryByRole("button", { name: "Add condition on a" })).toBeNull();
  });

  it("typing in the value field is not Delete on the node: Backspace keeps the node", () => {
    mountWithConditions();
    const value = screen.getByRole("textbox", { name: "Condition value on a" });
    fireEvent.keyDown(value, { key: "Backspace" });
    expect(screen.getAllByRole("group", { name: /^Pattern node/ })).toHaveLength(1);
  });

  it("offers no field for a type with nothing to match on", () => {
    vi.stubGlobal("fetch", vi.fn(async () => ({ ok: true, status: 200, json: async () => ({ patterns: [] }) })));
    render(<QueryBuilderPanel investigationId="inv-1" apiBaseUrl="http://api.test" bearerToken="tok" schema={SCHEMA} />);
    fireEvent.click(header("Add to the pattern"));
    fireEvent.click(screen.getByRole("button", { name: "Add variable" }));
    expect(screen.queryByRole("combobox", { name: "Condition property on a" })).toBeNull();
  });
});
