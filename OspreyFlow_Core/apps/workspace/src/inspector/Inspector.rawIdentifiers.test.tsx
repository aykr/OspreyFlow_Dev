// @vitest-environment jsdom
//
// Build order step 30 (the owner, 4 November 2026; CLAUDE.md rule 7): the Inspector shows no raw
// identifier. The 3 November rehearsal found three on screen: a link's "Type ID SHARED_CELL_WITH"
// (ADR-091 decision 4, withdrawn by Amendment 1), a node's store id, and a Location's `site_ref`
// ("pid:est1:wing:F"). The data below is shaped as the Prison Intelligence case serves it. If any of
// these tests fails, a raw key, id or internal reference is back on an analyst's screen.
import Graph from "graphology";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { Edge, Node } from "../../../../packages/schemas/generated";
import { Inspector, type InspectorProps } from "./Inspector";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const WING: Node = {
  id: "01M6GZP7WX0H06ZCM4T8ZBXEFJ",
  type: "Location",
  properties: {
    name: "Wing F",
    site_ref: "pid:est1:wing:F",
    geometry_ref: "pid:geo:est1:wing:F",
  },
  handling: { classification: "OFFICIAL", handling_code: "P", originator: "unit-hmp", owning_unit: "unit-hmp" },
  provenance: {
    state: "asserted",
    sources: [{ document_id: "/var/lib/osprey/ingest/uploaded/prison-intelligence/sites.csv", locator: "row 4" }],
    first_seen: "2026-10-01T09:00:00Z",
  },
} as unknown as Node;

const PRINCIPAL: Node = {
  id: "01M6GZQ1AB2C3D4E5F6G7H8J9K",
  type: "Person",
  properties: { family_name: "Ashby", given_names: "Dean", prison_number: "A1234BC" },
  provenance: { state: "asserted", sources: [], first_seen: "2026-10-01T09:00:00Z" },
} as unknown as Node;

const DOCUMENT: Node = {
  id: "01M6GZR9ZZ0000000000000001",
  type: "Document",
  properties: {
    title: "Intelligence report 0417",
    event_id: "01M6GZS0000000000000000002",
    message_id: "<0417.report@hmp.example>",
    object_ref: "media/01M6GZS0000000000000000003",
  },
  provenance: { state: "asserted", sources: [], first_seen: "2026-10-01T09:00:00Z" },
} as unknown as Node;

const SHARED_CELL: Edge = {
  id: "01M6GZT4EDGE00000000000004",
  type: "SHARED_CELL_WITH",
  source: PRINCIPAL.id,
  // The other end is not on the canvas: the Inspector has only its id to go on.
  target: "01M6GZU8OFFSCREEN000000005",
  occurrences: 2,
  provenance: {
    state: "asserted",
    sources: [{ document_id: "/var/lib/osprey/ingest/uploaded/prison-intelligence/cells.csv", locator: "row 0" }],
    first_seen: "2026-10-01T09:00:00Z",
  },
} as unknown as Edge;

const assessment: NonNullable<InspectorProps["assessment"]> = {
  apiBaseUrl: "http://api.test",
  bearerToken: "tok",
  investigationId: "inv-1",
  workingSetGraph: new Graph(),
  onHighlightNodes: () => undefined,
};

function stubFetch() {
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => ({ ok: true, status: 200, json: async () => ({ notes: [], changes: [], events: [], total: 0 }) })),
  );
}

/** Every text an analyst can read in the Inspector, every folded part opened first. */
function everythingShown(): string {
  for (const header of screen.queryAllByRole("button", { expanded: false })) fireEvent.click(header);
  return document.body.textContent ?? "";
}

describe("the Inspector shows no raw identifier (build order step 30)", () => {
  it("a Location: no store id, no site_ref, no geometry reference, no server path", () => {
    render(<Inspector node={WING} />);
    const shown = everythingShown();
    expect(shown).toContain("Wing F");
    for (const raw of [WING.id, "site_ref", "pid:est1:wing:F", "geometry_ref", "pid:geo:", "/var/lib/osprey"]) {
      expect(shown).not.toContain(raw);
    }
    expect(screen.queryByText("ID")).toBeNull();
  });

  it("a property is named as a person reads it, not by its key", () => {
    render(<Inspector node={PRINCIPAL} />);
    const shown = everythingShown();
    expect(shown).toContain("Prison number");
    expect(shown).toContain("A1234BC");
    expect(shown).not.toContain("prison_number");
    expect(shown).not.toContain("family_name");
    expect(shown).not.toContain(PRINCIPAL.id);
  });

  it("a Document: none of the stores' own keys (event, message, object)", () => {
    render(<Inspector node={DOCUMENT} />);
    const shown = everythingShown();
    expect(shown).toContain("Intelligence report 0417");
    for (const raw of [DOCUMENT.id, "01M6GZS0000000000000000002", "<0417.report@hmp.example>", "media/01M6GZS"]) {
      expect(shown).not.toContain(raw);
    }
  });

  it("a link: no Type ID, no type key, no id for an end that is not on the canvas", () => {
    stubFetch();
    render(
      <Inspector
        node={null}
        link={{ edge: SHARED_CELL, source: PRINCIPAL, target: undefined, directed: false }}
        assessment={assessment}
      />,
    );
    const shown = everythingShown();
    expect(shown).toContain("Shared cell with");
    expect(shown).toContain("Ashby, Dean");
    for (const raw of ["Type ID", "SHARED_CELL_WITH", SHARED_CELL.id, SHARED_CELL.target, "/var/lib/osprey"]) {
      expect(shown).not.toContain(raw);
    }
  });

  it("several selected: the shared property is named, not keyed, and no internal reference is offered", () => {
    const other = { ...WING, id: "01M6GZV2SECOND00000000006", properties: { ...WING.properties, name: "Wing G" } } as Node;
    render(
      <Inspector
        node={null}
        selection={{ nodes: [WING, other], onCentre: () => undefined, onRemove: () => undefined }}
      />,
    );
    const shown = everythingShown();
    for (const raw of ["site_ref", "geometry_ref", "pid:geo:", WING.id, other.id]) {
      expect(shown).not.toContain(raw);
    }
  });
});
