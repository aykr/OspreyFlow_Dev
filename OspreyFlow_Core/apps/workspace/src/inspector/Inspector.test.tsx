// @vitest-environment jsdom
import Graph from "graphology";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { Edge, Node } from "../../../../packages/schemas/generated";
import { Inspector, type InspectorProps } from "./Inspector";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const link = {
  edge: {
    id: "e7",
    type: "ASSOCIATED_WITH",
    source: "a",
    target: "b",
    occurrences: 1,
    provenance: { state: "asserted", sources: [], first_seen: "2026-01-01T00:00:00Z" },
  } as unknown as Edge,
  source: undefined,
  target: undefined,
  directed: true,
};

const assessment: NonNullable<InspectorProps["assessment"]> = {
  apiBaseUrl: "http://api.test",
  bearerToken: "tok",
  investigationId: "inv-1",
  workingSetGraph: new Graph(),
  onHighlightNodes: () => undefined,
};

function stubNotes() {
  const fetchMock = vi.fn(async (url: string) => ({
    ok: true,
    status: 200,
    json: async () =>
      url.includes("/notes")
        ? { notes: [] }
        : url.includes("/history")
          ? { changes: [], truncated: false }
          : url.includes("/events")
            ? { total: 0, offset: 0, limit: 50, events: [] } // ADR-089: a link with no events
            : url.includes("/yardstick")
              ? { bands: [{ label: "Likely", lower: 0.55, upper: 0.75 }] } // the real answer's shape
              : url.includes("/judgements")
                ? { judgements: [] }
                : url.includes("/gaps")
                  ? { gaps: [] }
                  : url.includes("/assumptions")
                    ? { assumptions: [] }
                    : {},
  }));
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

describe("Inspector — a selected link", () => {
  it("shows the link's details and a Notes section for that link", async () => {
    const fetchMock = stubNotes();
    render(<Inspector node={null} link={link} assessment={assessment} />);
    expect(screen.getByText("ASSOCIATED_WITH")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Notes" })); // ADR-096: folded at first
    expect(screen.getByRole("region", { name: "Notes" })).toBeTruthy();
    await waitFor(() =>
      expect(fetchMock.mock.calls.map(([url]) => String(url))).toContain(
        "http://api.test/v1/investigations/inv-1/links/e7/notes",
      ),
    );
    expect(await screen.findByText("No notes on this link yet.")).toBeTruthy();
  });

  it("offers no Notes when the case is not wired up (no investigation to keep them in)", () => {
    stubNotes();
    render(<Inspector node={null} link={link} />);
    expect(screen.getByText("ASSOCIATED_WITH")).toBeTruthy();
    expect(screen.queryByRole("region", { name: "Notes" })).toBeNull();
  });

  it("shows no link Notes for a selected node", () => {
    const fetchMock = stubNotes();
    const node = { id: "a", type: "Person", properties: {}, provenance: { state: "asserted", sources: [], first_seen: "x" } } as unknown as Node;
    render(<Inspector node={node} assessment={assessment} />);
    expect(screen.queryByRole("region", { name: "Notes" })).toBeNull();
    expect(fetchMock.mock.calls.some(([url]) => String(url).includes("/notes"))).toBe(false);
  });
  it("offers a change and a history for an ordinary link, once the ends and the ontology are known (ADR-080)", async () => {
    stubNotes();
    const person = { id: "a", type: "Person", properties: {}, provenance: { state: "asserted", sources: [], first_seen: "x" } } as unknown as Node;
    render(
      <Inspector
        node={null}
        link={{ ...link, source: person, target: { ...person, id: "b" } }}
        assessment={assessment}
        linkEditing={{ edgeTypes: [], openChangeSignal: 0, openNoteSignal: 0, onChanged: () => undefined }}
      />,
    );
    // ADR-096: each part folds under its own header.
    expect(screen.getByRole("button", { name: "Change this link" })).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Change history" }));
    expect(await screen.findByRole("region", { name: "Change history" })).toBeTruthy();
  });

  it("offers neither to a same-as link: that is confirmed or marked, not edited", async () => {
    stubNotes();
    const person = { id: "a", type: "Person", properties: {}, provenance: { state: "asserted", sources: [], first_seen: "x" } } as unknown as Node;
    render(
      <Inspector
        node={null}
        link={{ ...link, edge: { ...link.edge, type: "SAME_AS" }, source: person, target: { ...person, id: "b" } }}
        assessment={assessment}
        linkEditing={{ edgeTypes: [], openChangeSignal: 0, openNoteSignal: 0, onChanged: () => undefined }}
      />,
    );
    expect(screen.queryByRole("button", { name: "Change this link" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Change history" })).toBeNull();
    expect(screen.getByRole("button", { name: "Notes" })).toBeTruthy();
  });
});

describe("Inspector sections (ADR-096)", () => {
  const person = { id: "a", type: "Person", properties: { family_name: "Lay" }, provenance: { state: "asserted", sources: [{ document_id: "d1", locator: "p.1" }], first_seen: "x" } } as unknown as Node;
  const editing = { edgeTypes: [], openChangeSignal: 0, openNoteSignal: 0, openEventsSignal: 0, onChanged: () => undefined };
  const header = (name: RegExp | string) => screen.getByRole("button", { name });

  function mountLink(over: Partial<NonNullable<InspectorProps["linkEditing"]>> = {}) {
    stubNotes();
    return render(
      <Inspector
        node={null}
        link={{ ...link, source: person, target: { ...person, id: "b" } }}
        assessment={assessment}
        linkEditing={{ ...editing, ...over }}
      />,
    );
  }

  it("a link shows its details open and every other part folded", () => {
    mountLink();
    expect(header("Details").getAttribute("aria-expanded")).toBe("true");
    for (const name of ["Change this link", "Notes", /^Events/, "Change history"]) {
      expect(header(name).getAttribute("aria-expanded")).toBe("false");
    }
    expect(screen.getByText("ASSOCIATED_WITH")).toBeTruthy();
    expect(screen.queryByRole("region", { name: "Notes" })).toBeNull(); // hidden while folded
  });

  it("a header opens and closes its part", () => {
    mountLink();
    fireEvent.click(header("Notes"));
    expect(header("Notes").getAttribute("aria-expanded")).toBe("true");
    expect(screen.getByRole("region", { name: "Notes" })).toBeTruthy();
    fireEvent.click(header("Notes"));
    expect(screen.queryByRole("region", { name: "Notes" })).toBeNull();
  });

  it("opening Change this link opens the form itself", () => {
    mountLink();
    fireEvent.click(header("Change this link"));
    expect(screen.getByLabelText("Link type")).toBeTruthy();
  });

  it("a link-menu hand-over opens its part", () => {
    const view = mountLink();
    view.rerender(
      <Inspector
        node={null}
        link={{ ...link, source: person, target: { ...person, id: "b" } }}
        assessment={assessment}
        linkEditing={{ ...editing, openNoteSignal: 1 }}
      />,
    );
    expect(header("Notes").getAttribute("aria-expanded")).toBe("true");
  });

  it("a half-written note survives its part being folded", async () => {
    mountLink();
    fireEvent.click(header("Notes"));
    const box = (await screen.findByRole("textbox", { name: /note/i })) as HTMLTextAreaElement;
    fireEvent.change(box, { target: { value: "Half a thought" } });
    fireEvent.click(header("Notes"));
    fireEvent.click(header("Notes"));
    expect((screen.getByRole("textbox", { name: /note/i }) as HTMLTextAreaElement).value).toBe("Half a thought");
  });

  it("a node's parts replace the tabs, Properties open", () => {
    stubNotes();
    render(<Inspector node={person} assessment={assessment} />);
    expect(screen.queryByRole("tab")).toBeNull();
    expect(header("Properties").getAttribute("aria-expanded")).toBe("true");
    expect(screen.getAllByText("Lay")).toHaveLength(2); // the header's name and the property
    for (const name of ["Relationships", "Provenance", "Source", "Judgements"]) {
      expect(header(name).getAttribute("aria-expanded")).toBe("false");
    }
    fireEvent.click(header("Source"));
    expect(screen.getByText("d1 · p.1")).toBeTruthy();
  });

  it("with no node selected, Judgements is open", () => {
    stubNotes();
    render(<Inspector node={null} assessment={assessment} />);
    expect(header("Judgements").getAttribute("aria-expanded")).toBe("true");
  });
});

describe("Inspector states (ADR-097 step 1, design review item 4)", () => {
  const node = (id: string, type: string, properties: Record<string, unknown>) =>
    ({ id, type, properties, provenance: { state: "asserted", sources: [], first_seen: "x" } }) as unknown as Node;
  const lay = node("p1", "Person", { family_name: "Lay", employer: "Enron" });
  const skilling = node("p2", "Person", { family_name: "Skilling", employer: "Enron" });
  const phone = node("e1", "Endpoint", { value_normalised: "07911123456" });

  function graphOf(nodes: Node[], edges: [string, string, string, string][]) {
    const graph = new Graph({ multi: true });
    for (const n of nodes) graph.addNode(n.id, { data: n });
    for (const [id, type, source, target] of edges) {
      graph.addEdgeWithKey(id, source, target, { data: { id, type, source, target } });
    }
    return graph;
  }

  it("one node: its type and name head the panel, and its links in view are counted by type", () => {
    stubNotes();
    const graph = graphOf([lay, skilling, phone], [
      ["k1", "ASSOCIATE_OF", "p1", "p2"],
      ["k2", "USES", "p1", "e1"],
      ["k3", "ASSOCIATE_OF", "p1", "e1"],
    ]);
    render(<Inspector node={lay} assessment={{ ...assessment, workingSetGraph: graph }} />);
    expect(screen.getByRole("heading", { name: /Person.*p1|Lay/ })).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Relationships" }));
    const rows = screen.getAllByRole("listitem").map((li) => li.textContent);
    expect(rows).toContain("Associate of2"); // the display name (ADR-091)
    expect(rows).toContain("Uses1");
  });

  it("several nodes: a summary by type, what they share, and the links between them", () => {
    stubNotes();
    const graph = graphOf([lay, skilling, phone], [
      ["k1", "ASSOCIATE_OF", "p1", "p2"],
      ["k2", "USES", "p1", "e1"],
    ]);
    render(
      <Inspector
        node={lay}
        selection={{ nodes: [lay, skilling], onCentre: vi.fn(), onRemove: vi.fn() }}
        assessment={{ ...assessment, workingSetGraph: graph }}
      />,
    );
    expect(screen.getByRole("button", { name: "Summary" }).getAttribute("aria-expanded")).toBe("true");
    expect(screen.getByText("2 Person")).toBeTruthy();
    expect(screen.getByText(/employer/)).toBeTruthy(); // shared by both, with one value
    expect(screen.queryByText(/family_name/)).toBeNull(); // different values: not shared
    fireEvent.click(screen.getByRole("button", { name: "Links between them (1)" }));
    expect(screen.getByText("Associate of")).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Properties" })).toBeNull(); // not one node's view
    // ADR-115 E4 (review item 2): the selection bar's count is the only one — the Inspector repeats
    // neither "2 nodes" nor "Selected (2)".
    expect(screen.queryByText("2 nodes")).toBeNull();
    expect(screen.getByRole("button", { name: "Selected" })).toBeTruthy();
  });

  it("nothing selected: says how to begin, with one action", () => {
    render(<Inspector node={null} />);
    expect(screen.getByText("Select a node, or press / to search.")).toBeTruthy();
  });
});
