// @vitest-environment jsdom
// The Matrix view (`02_GLASS_FRONTEND.md` §6; GDS remediation plan item A1): the working set as two
// real tables a screen reader can walk — captions, column headers, a row header per row, sortable
// columns, arrow-key movement between cells — with the selection the canvas uses.
import { act, cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { useState } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { makeEdge, makeNode } from "../testing/fixtures";
import { createWorkingSet, type WorkingSet } from "../workingset/store";
import { MatrixView, type MatrixViewProps } from "./MatrixView";

afterEach(cleanup);

function fixture(extraNodes = 0): WorkingSet {
  const ws = createWorkingSet();
  ws.store.getState().applyDelta({
    seq: 1,
    op: "snapshot",
    withheld: true,
    nodes: [
      makeNode("p1", { properties: { family_name: "OKAFOR", given_names: "Callum" } }),
      makeNode("p2", { properties: { family_name: "ADEYEMI", given_names: "Tola" } }),
      makeNode("p3", {
        properties: { family_name: "BRENNAN" },
        provenance: { state: "inferred", sources: [], first_seen: "2026-01-01T00:00:00Z" },
        handling: { classification: "SECRET", handling_code: "P", originator: "u", owning_unit: "u" },
      }),
      ...Array.from({ length: extraNodes }, (_, i) =>
        makeNode(`x${String(i).padStart(3, "0")}`, { properties: { family_name: `ZULU${String(i).padStart(3, "0")}` } }),
      ),
    ],
    edges: [makeEdge("l1", "p1", "p2"), makeEdge("l2", "p1", "p3", { type: "USES" })],
  });
  return ws;
}

function Harness(props: Partial<MatrixViewProps> & { ws: WorkingSet; initial?: string[] }) {
  const { ws, initial = [], ...rest } = props;
  const [selected, setSelected] = useState<string[]>(initial);
  const [link, setLink] = useState<string | null>(null);
  return (
    <MatrixView
      graph={ws.graph}
      store={ws.store}
      edgeTypes={[{ name: "USES", label: "Uses" }]}
      selectedNodeIds={selected}
      selectedEdgeId={link}
      onSelectNodes={setSelected}
      onSelectLink={setLink}
      onExpand={vi.fn()}
      onShowOnGraph={vi.fn()}
      {...rest}
    />
  );
}

const entities = () => screen.getByRole("grid", { name: /^Entities in this view/ });
const links = () => screen.getByRole("grid", { name: /^Links in this view/ });
const rowOf = (grid: HTMLElement, name: RegExp) =>
  within(grid).getAllByRole("row").find((r) => within(r).queryByRole("rowheader", { name }))!;

describe("MatrixView — the tables", () => {
  it("is two real tables, each with a caption, column headers and a row header per row", () => {
    render(<Harness ws={fixture()} />);
    expect(entities().tagName).toBe("TABLE");
    expect(entities().querySelector("caption")?.textContent).toMatch(/^Entities in this view, 3\./);
    const headers = within(entities()).getAllByRole("columnheader").map((h) => h.textContent);
    expect(headers).toEqual(["Name", "Type", "Marking", "Provenance", "Links in view", "Expand", "On the graph"]);
    expect(within(entities()).getAllByRole("rowheader").map((h) => h.textContent)).toEqual([
      "ADEYEMI, Tola",
      "BRENNAN",
      "OKAFOR, Callum",
    ]);
    expect(links().querySelector("caption")?.textContent).toMatch(/^Links in this view, 2\./);
    expect(within(links()).getAllByRole("columnheader").map((h) => h.textContent)).toEqual([
      "Link",
      "From",
      "To",
      "Marking",
      "Provenance",
    ]);
  });

  it("shows each node's marking as the Inspector does, and says inferred in words (rule 5)", () => {
    render(<Harness ws={fixture()} />);
    const brennan = rowOf(entities(), /BRENNAN/);
    expect(within(brennan).getByText("SECRET").className).toContain("marking-badge");
    expect(within(brennan).getByText("Inferred")).toBeTruthy();
    // The fifth column is "Links in view": OKAFOR has two links in this view.
    expect(rowOf(entities(), /OKAFOR/).children[4]?.textContent).toBe("2");
  });

  it("sorts by a column, saying which way in aria-sort and in the caption", () => {
    render(<Harness ws={fixture()} />);
    const name = within(entities()).getByRole("columnheader", { name: "Name" });
    expect(name.getAttribute("aria-sort")).toBe("ascending");
    fireEvent.click(within(name).getByRole("button", { name: "Name" }));
    expect(name.getAttribute("aria-sort")).toBe("descending");
    expect(within(entities()).getAllByRole("rowheader")[0]?.textContent).toBe("OKAFOR, Callum");
    expect(entities().querySelector("caption")?.textContent).toContain("Sorted by name, Z to A");
    const count = within(entities()).getByRole("columnheader", { name: "Links in view" });
    fireEvent.click(within(count).getByRole("button"));
    expect(count.getAttribute("aria-sort")).toBe("descending");
    expect(name.getAttribute("aria-sort")).toBeNull();
    expect(within(entities()).getAllByRole("rowheader")[0]?.textContent).toBe("OKAFOR, Callum");
  });

  it("pages a long view and says plainly which rows are shown (rule 2)", () => {
    render(<Harness ws={fixture(250)} />);
    expect(entities().querySelector("caption")?.textContent).toContain("Rows 1 to 100 of 253.");
    expect(within(entities()).getAllByRole("rowheader")).toHaveLength(100);
    fireEvent.click(screen.getByRole("button", { name: "Next page of entities" }));
    expect(entities().querySelector("caption")?.textContent).toContain("Rows 101 to 200 of 253.");
    fireEvent.click(screen.getByRole("button", { name: "Next page of entities" }));
    expect(within(entities()).getAllByRole("rowheader")).toHaveLength(53);
    expect((screen.getByRole("button", { name: "Next page of entities" }) as HTMLButtonElement).disabled).toBe(true);
  });

  it("follows the working set: a node removed from it leaves the table at once", () => {
    const ws = fixture();
    render(<Harness ws={ws} />);
    expect(rowOf(entities(), /BRENNAN/)).toBeTruthy();
    act(() => ws.store.getState().applyDelta({ seq: 2, op: "remove", node_ids: ["p3"] }));
    expect(within(entities()).queryByRole("rowheader", { name: /BRENNAN/ })).toBeNull();
    expect(within(links()).getAllByRole("row")).toHaveLength(2); // the header and l1
  });

  it("never shows anything the working set does not hold, nor a number about what is withheld", () => {
    const ws = fixture();
    expect(ws.store.getState().withheld).toBe(true);
    render(<Harness ws={ws} />);
    const text = document.body.textContent ?? "";
    expect(text).not.toMatch(/withheld|not cleared|hidden/i);
    // Only the three nodes and two links held: one row each, plus the headers.
    expect(within(entities()).getAllByRole("row")).toHaveLength(4);
    expect(within(links()).getAllByRole("row")).toHaveLength(3);
  });

  it("marks a row the cross-filter dims, and keeps it", () => {
    render(<Harness ws={fixture()} dimmedNodeIds={new Set(["p2"])} />);
    expect(within(rowOf(entities(), /ADEYEMI/)).getByText("Dimmed by filter")).toBeTruthy();
  });

  it("says so when the working set is empty, rather than drawing empty tables", () => {
    render(<Harness ws={createWorkingSet()} />);
    expect(screen.queryByRole("grid")).toBeNull();
    expect(screen.getByText(/Nothing is in this view yet/)).toBeTruthy();
  });
});

describe("MatrixView — selection, the same one the canvas uses", () => {
  it("shows the selection it is given as selected rows", () => {
    render(<Harness ws={fixture()} initial={["p3"]} />);
    expect(rowOf(entities(), /BRENNAN/).getAttribute("aria-selected")).toBe("true");
    expect(rowOf(entities(), /OKAFOR/).getAttribute("aria-selected")).toBe("false");
    expect(entities().getAttribute("aria-multiselectable")).toBe("true");
  });

  it("selecting a row tells the caller: a click replaces the selection, Ctrl+click adds to it", () => {
    const onSelectNodes = vi.fn();
    render(<Harness ws={fixture()} onSelectNodes={onSelectNodes} selectedNodeIds={["p1"]} />);
    fireEvent.click(within(rowOf(entities(), /BRENNAN/)).getByRole("rowheader"));
    expect(onSelectNodes).toHaveBeenLastCalledWith(["p3"]);
    fireEvent.click(within(rowOf(entities(), /BRENNAN/)).getByRole("rowheader"), { ctrlKey: true });
    expect(onSelectNodes).toHaveBeenLastCalledWith(["p1", "p3"]);
  });

  it("opens on the page that holds the selection made on the canvas", () => {
    render(<Harness ws={fixture(250)} initial={["x200"]} />);
    expect(entities().querySelector("caption")?.textContent).toContain("Rows 201 to 253 of 253.");
    expect(rowOf(entities(), /ZULU200/).getAttribute("aria-selected")).toBe("true");
  });

  it("selecting a link row selects that link", () => {
    const onSelectLink = vi.fn();
    render(<Harness ws={fixture()} onSelectLink={onSelectLink} />);
    fireEvent.click(within(links()).getAllByRole("rowheader")[0]!);
    expect(onSelectLink).toHaveBeenCalledWith(expect.stringMatching(/^l[12]$/));
  });

  it("offers Expand and Show on the graph on each row, named for the row", () => {
    const onExpand = vi.fn();
    const onShowOnGraph = vi.fn();
    render(<Harness ws={fixture()} onExpand={onExpand} onShowOnGraph={onShowOnGraph} />);
    fireEvent.click(screen.getByRole("button", { name: "Expand OKAFOR, Callum" }));
    expect(onExpand).toHaveBeenCalledWith("p1");
    fireEvent.click(screen.getByRole("button", { name: "Show OKAFOR, Callum on the graph" }));
    expect(onShowOnGraph).toHaveBeenCalledWith("p1");
  });
});

describe("MatrixView — the keyboard (an ARIA grid: one Tab stop, arrows between cells)", () => {
  it("is one Tab stop, and the arrow keys move between cells", () => {
    render(<Harness ws={fixture()} />);
    const stops = Array.from(entities().querySelectorAll<HTMLElement>("[tabindex='0']"));
    expect(stops).toHaveLength(1);
    act(() => stops[0]!.focus());
    expect(document.activeElement?.textContent).toBe("Name");
    fireEvent.keyDown(document.activeElement!, { key: "ArrowDown" });
    expect(document.activeElement?.textContent).toBe("ADEYEMI, Tola");
    fireEvent.keyDown(document.activeElement!, { key: "ArrowDown" });
    expect(document.activeElement?.textContent).toBe("BRENNAN");
    fireEvent.keyDown(document.activeElement!, { key: "ArrowRight" });
    expect(document.activeElement?.textContent).toContain("Person");
    fireEvent.keyDown(document.activeElement!, { key: "End" });
    expect(document.activeElement?.getAttribute("aria-label")).toBe("Show BRENNAN on the graph");
    fireEvent.keyDown(document.activeElement!, { key: "Home" });
    expect(document.activeElement?.textContent).toBe("BRENNAN");
    // Exactly one Tab stop still, and it follows focus.
    expect(entities().querySelectorAll("[tabindex='0']")).toHaveLength(1);
  });

  it("Enter selects the focused row; Space adds it to or takes it out of the selection", () => {
    render(<Harness ws={fixture()} initial={["p1"]} />);
    const brennan = within(rowOf(entities(), /BRENNAN/)).getByRole("rowheader");
    act(() => brennan.focus());
    fireEvent.keyDown(brennan, { key: " " });
    expect(rowOf(entities(), /BRENNAN/).getAttribute("aria-selected")).toBe("true");
    expect(rowOf(entities(), /OKAFOR/).getAttribute("aria-selected")).toBe("true");
    fireEvent.keyDown(document.activeElement!, { key: "Enter" });
    expect(rowOf(entities(), /BRENNAN/).getAttribute("aria-selected")).toBe("true");
    expect(rowOf(entities(), /OKAFOR/).getAttribute("aria-selected")).toBe("false");
  });

  it("PageDown and PageUp turn the page", () => {
    render(<Harness ws={fixture(250)} />);
    const first = within(entities()).getAllByRole("rowheader")[0]!;
    act(() => first.focus());
    fireEvent.keyDown(first, { key: "PageDown" });
    expect(entities().querySelector("caption")?.textContent).toContain("Rows 101 to 200 of 253.");
    fireEvent.keyDown(document.activeElement!, { key: "PageUp" });
    expect(entities().querySelector("caption")?.textContent).toContain("Rows 1 to 100 of 253.");
  });
});

// Build order step 15 (the 2 November rehearsal, open question 20): on the principal's star the
// Strength and Rarity columns read "Not worked out" and "None" on every row while the Inspector showed
// a strength. Measured on the GOV.UK deployment: the strengths came back in 2 s and the rarity of the
// star's 79 pairs in 10.5 s, and the Matrix waited for both before showing either, saying "Not worked
// out" (a verdict, not "still asking") meanwhile; a refused rarity would have blanked the strengths too.
describe("MatrixView — connection strength and rarity (ADR-139; user guide §5.11, §5.12)", () => {
  const STRENGTH_PROPS = { apiBaseUrl: "http://conduit", bearerToken: "t", investigationId: "case-1" };

  function reply(body: unknown, status = 200): Response {
    return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
  }

  /** The Conduit's two routes, as the fake answers them: `strength` and `rarity` are each a promise
   * of the response, so a test decides when (and whether) each arrives. */
  function conduit(strength: Promise<Response>, rarity: Promise<Response>) {
    const fetchMock = vi.fn((url: string) => {
      if (url.endsWith("/connection-strength")) return strength;
      if (url.endsWith("/rarity")) return rarity;
      return Promise.reject(new Error(`unexpected ${url}`));
    });
    vi.stubGlobal("fetch", fetchMock);
    return fetchMock;
  }

  afterEach(() => vi.unstubAllGlobals());

  const strengthOf = (row: HTMLElement) => [...row.querySelectorAll("td")].at(-2)!.textContent;
  const rarityOf = (row: HTMLElement) => [...row.querySelectorAll("td")].at(-1)!.textContent;
  const linkRow = (name: RegExp) =>
    within(links()).getAllByRole("row").find((r) => within(r).queryByRole("rowheader", { name }))!;

  // The reader may see l1 only: the Conduit leaves l2 out of its answer (worked out in the adapter as
  // the reader, rule 3) and gives its pair no score.
  const STRENGTHS = { links: [{ edge_id: "l1", edge_type: "ASSOCIATE_OF", base_weight: 0.4, strength: 0.62 }], legend: {} };
  const RARITY = { scope: "dataset", node_values: {}, pairs: [{ a: "p1", b: "p2", score: 0.91 }, { a: "p1", b: "p3", score: null }] };

  it("shows each link's strength as soon as it arrives, without waiting for the rarity", async () => {
    conduit(Promise.resolve(reply(STRENGTHS)), new Promise<Response>(() => {}));
    render(<Harness ws={fixture()} strength={STRENGTH_PROPS} />);
    await vi.waitFor(() => expect(strengthOf(linkRow(/Associate of/))).toBe("0.62"));
    // Still being asked, and said so: never "None", which reads as an answer.
    expect(rarityOf(linkRow(/Associate of/))).toBe("Working out…");
  });

  it("says a value is being worked out while it is, not that it was not worked out", async () => {
    conduit(new Promise<Response>(() => {}), new Promise<Response>(() => {}));
    render(<Harness ws={fixture()} strength={STRENGTH_PROPS} />);
    expect(strengthOf(linkRow(/Associate of/))).toBe("Working out…");
    expect(rarityOf(linkRow(/Associate of/))).toBe("Working out…");
  });

  it("keeps the strengths when the rarity is refused, and says why the rarity is missing", async () => {
    conduit(
      Promise.resolve(reply(STRENGTHS)),
      Promise.resolve(reply({ detail: { error: "limit_exceeded", cap_kind: "pairs", cap: 10, would_be: 20 } }, 422)),
    );
    render(<Harness ws={fixture()} strength={STRENGTH_PROPS} />);
    await vi.waitFor(() => expect(strengthOf(linkRow(/Associate of/))).toBe("0.62"));
    expect(rarityOf(linkRow(/Associate of/))).toBe("Not worked out");
    expect(screen.getByText(/too many pairs in this view to work out rarity/)).toBeTruthy();
  });

  it("shows what the Conduit gave for the reader, and nothing for a link it left out (rule 3)", async () => {
    conduit(Promise.resolve(reply(STRENGTHS)), Promise.resolve(reply(RARITY)));
    render(<Harness ws={fixture()} strength={STRENGTH_PROPS} />);
    await vi.waitFor(() => expect(rarityOf(linkRow(/Associate of/))).toBe("0.91"));
    expect(strengthOf(linkRow(/Associate of/))).toBe("0.62");
    // Not in the reader's answer: no strength, and no rarity for its pair; no count of anything.
    expect(strengthOf(linkRow(/^Uses/))).toBe("Not worked out");
    expect(rarityOf(linkRow(/^Uses/))).toBe("None");
  });
});
