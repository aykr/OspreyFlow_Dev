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
