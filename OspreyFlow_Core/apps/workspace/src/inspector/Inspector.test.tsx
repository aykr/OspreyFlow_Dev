// @vitest-environment jsdom
import Graph from "graphology";
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { Edge, Node } from "../../../../packages/schemas/generated";
import { forgetIconChoicesForTest, setIconChoice } from "../canvas/iconChoices";
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
  const person = { id: "a", type: "Person", properties: { family_name: "Ashby" }, provenance: { state: "asserted", sources: [{ document_id: "d1", locator: "p.1" }], first_seen: "x" } } as unknown as Node;
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
    expect(screen.getAllByText("Ashby")).toHaveLength(2); // the header's name and the property
    for (const name of ["Relationships", "Provenance", "Source", "Judgements"]) {
      expect(header(name).getAttribute("aria-expanded")).toBe("false");
    }
    fireEvent.click(header("Source"));
    expect(screen.getByText("d1 · p.1")).toBeTruthy();
  });

  it("a source row reads counted from 1, the row under the header as row 1 (ADR-131)", () => {
    stubNotes();
    const fromRow = {
      ...person,
      provenance: { state: "asserted", sources: [{ document_id: "calls.csv", locator: "row 0" }], first_seen: "x" },
    } as unknown as Node;
    render(<Inspector node={fromRow} assessment={assessment} />);
    fireEvent.click(header("Source"));
    expect(screen.getByText("calls.csv · row 1")).toBeTruthy();
  });

  it("a node whose sources are withheld says so in Source, and never that none were recorded", () => {
    stubNotes();
    const withheld = {
      ...person,
      provenance: { state: "asserted", sources: [], sources_withheld: true, first_seen: "x" },
    } as unknown as Node;
    render(<Inspector node={withheld} assessment={assessment} />);
    fireEvent.click(header("Source"));
    expect(screen.getByText("Its sources are in data this case does not read")).toBeTruthy();
    expect(screen.queryByText(/No sources recorded/)).toBeNull();
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
  const ashby = node("p1", "Person", { family_name: "Ashby", employer: "Fixture Corp" });
  const holloway = node("p2", "Person", { family_name: "Holloway", employer: "Fixture Corp" });
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
    const graph = graphOf([ashby, holloway, phone], [
      ["k1", "ASSOCIATE_OF", "p1", "p2"],
      ["k2", "USES", "p1", "e1"],
      ["k3", "ASSOCIATE_OF", "p1", "e1"],
    ]);
    render(<Inspector node={ashby} assessment={{ ...assessment, workingSetGraph: graph }} />);
    expect(screen.getByRole("heading", { name: /Person.*p1|Ashby/ })).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Relationships" }));
    const rows = screen.getAllByRole("listitem").map((li) => li.textContent);
    expect(rows).toContain("Associate of2"); // the display name (ADR-091)
    expect(rows).toContain("Uses1");
  });

  it("several nodes: a summary by type, what they share, and the links between them", () => {
    stubNotes();
    const graph = graphOf([ashby, holloway, phone], [
      ["k1", "ASSOCIATE_OF", "p1", "p2"],
      ["k2", "USES", "p1", "e1"],
    ]);
    render(
      <Inspector
        node={ashby}
        selection={{ nodes: [ashby, holloway], onCentre: vi.fn(), onRemove: vi.fn() }}
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

  // ADR-115 E4 (review item 4; the reference's Inspector): one node carries its marking beside its
  // type, its properties in a 96px key column, its relationships with Expand and an honest caption,
  // and its provenance with the stroke the canvas draws it with.
  it("one node: its marking, a key column, Expand on its relationships, and its provenance's stroke", () => {
    stubNotes();
    const inferred = {
      id: "p9", type: "Person", properties: { family_name: "Okafor" },
      provenance: { state: "inferred", sources: [], first_seen: "x" },
      handling: { classification: "OFFICIAL-SENSITIVE" },
    } as unknown as Node; // prettier-ignore
    const expand = vi.fn();
    render(<Inspector node={inferred} assessment={assessment} onExpand={expand} />);
    expect(screen.getByLabelText("Marking").textContent).toBe("OFFICIAL-SENSITIVE");
    const keys = document.querySelector(".inspector-keys") as HTMLElement;
    expect(keys.tagName).toBe("DL");
    fireEvent.click(screen.getByRole("button", { name: "Relationships" }));
    expect(screen.getByText("Drawn in this view. Expand counts the rest in the store before anything is drawn.")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Expand Okafor" }));
    expect(expand).toHaveBeenCalledWith("p9");
    fireEvent.click(screen.getByRole("button", { name: "Provenance" }));
    expect(document.querySelector(".provenance-stroke line")?.getAttribute("stroke-dasharray")).toBe("4 3");
  });

  it("one node without a marking or a way to expand shows neither", () => {
    stubNotes();
    render(<Inspector node={ashby} assessment={assessment} />);
    expect(screen.queryByLabelText("Marking")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Relationships" }));
    expect(screen.queryByRole("button", { name: /^Expand/ })).toBeNull();
  });

  it("nothing selected: says how to begin, with one action", () => {
    render(<Inspector node={null} />);
    expect(screen.getByText("Select a node, or press / to search.")).toBeTruthy();
  });
});

// ADR-128 Decision 4 (B7): the Inspector says which icon a value stands for.
describe("Inspector: a value icon", () => {
  const endpointVisual = {
    channel: "cyan",
    shape: "hexagon",
    icon: "device",
    iconByValue: { property: "endpoint_kind", icons: { handle: "keypad", msisdn: "phone" } },
  } as const;
  const visualFor: NonNullable<InspectorProps["visualFor"]> = (type) =>
    type === "Endpoint" ? endpointVisual : { channel: "indigo", shape: "circle", icon: "person" };
  const endpointOf = (properties: Record<string, unknown>) =>
    ({ id: "e1", type: "Endpoint", properties, provenance: { state: "asserted", sources: [], first_seen: "x" } }) as unknown as Node;

  it("names the drawing and the value it stands for, when the node's value is mapped", () => {
    stubNotes();
    render(<Inspector node={endpointOf({ endpoint_kind: "handle" })} assessment={assessment} visualFor={visualFor} />);
    expect(screen.getByText("Icon for this value")).toBeTruthy();
    expect(screen.getByText("Keypad (endpoint kind handle)")).toBeTruthy();
  });

  it("says nothing of an icon for a value the map leaves out, or a node without the property", () => {
    stubNotes();
    const { rerender } = render(<Inspector node={endpointOf({ endpoint_kind: "email" })} assessment={assessment} visualFor={visualFor} />);
    expect(screen.queryByText("Icon for this value")).toBeNull();
    rerender(<Inspector node={endpointOf({})} assessment={assessment} visualFor={visualFor} />);
    expect(screen.queryByText("Icon for this value")).toBeNull();
  });

  it("says nothing of an icon for a type that has no rule", () => {
    stubNotes();
    const person = { id: "a", type: "Person", properties: { endpoint_kind: "handle" }, provenance: { state: "asserted", sources: [], first_seen: "x" } } as unknown as Node;
    render(<Inspector node={person} assessment={assessment} visualFor={visualFor} />);
    expect(screen.queryByText("Icon for this value")).toBeNull();
  });
});


// The renderer gives the analyst's own choice for the type precedence over a value icon, so the
// Inspector must not name an icon the node is not drawn with.
describe("Inspector: a value icon the analyst's choice replaces", () => {
  const visualFor: NonNullable<InspectorProps["visualFor"]> = () => ({
    channel: "cyan",
    shape: "hexagon",
    icon: "device",
    iconByValue: { property: "endpoint_kind", icons: { handle: "keypad" } },
  });
  const endpoint = { id: "e1", type: "Endpoint", properties: { endpoint_kind: "handle" }, provenance: { state: "asserted", sources: [], first_seen: "x" } } as unknown as Node;

  afterEach(() => forgetIconChoicesForTest());

  it("says nothing of it once a drawing is chosen for the type, and says it again when the choice goes", async () => {
    forgetIconChoicesForTest();
    stubNotes();
    render(<Inspector node={endpoint} assessment={assessment} visualFor={visualFor} />);
    expect(screen.getByText("Icon for this value")).toBeTruthy();
    act(() => {
      setIconChoice("Endpoint", { kind: "glyph", name: "shield" });
    });
    expect(screen.queryByText("Icon for this value")).toBeNull();
    act(() => {
      setIconChoice("Endpoint", null);
    });
    expect(screen.getByText("Icon for this value")).toBeTruthy();
  });
});
