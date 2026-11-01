// The Matrix view's rows (`02_GLASS_FRONTEND.md` §6, §2 rule 1; GDS remediation plan item A1): the
// working set as the canvas holds it, one row per node and one per link, read from the same
// graphology instance and nothing else.
import { describe, expect, it } from "vitest";

import { makeEdge, makeNode } from "../testing/fixtures";
import { createWorkingSet } from "../workingset/store";
import {
  PAGE_SIZE,
  entityRows,
  linkRows,
  pageContaining,
  pageOf,
  provenanceText,
  sortRows,
} from "./matrixRows";
import { nodeLabel } from "../canvas/nodeAttributes";

function fixture() {
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
      makeNode("e1", { type: "Endpoint", properties: { value_normalised: "+447700900123" } }),
    ],
    edges: [
      makeEdge("l1", "p1", "p2"),
      makeEdge("l2", "p1", "e1", {
        type: "USES",
        provenance: { state: "inferred", sources: [], first_seen: "2026-01-01T00:00:00Z" },
      }),
      makeEdge("l3", "p1", "p3"),
    ],
  });
  return ws;
}

describe("the Matrix view's entity rows", () => {
  it("has one row per node in the working set, named as the canvas names it", () => {
    const ws = fixture();
    const rows = entityRows(ws.graph);
    expect(rows.map((r) => r.id).sort()).toEqual(["e1", "p1", "p2", "p3"]);
    for (const row of rows) {
      expect(row.name).toBe(nodeLabel(ws.graph.getNodeAttribute(row.id, "data")));
    }
    expect(rows.find((r) => r.id === "p1")?.name).toBe("OKAFOR, Callum");
  });

  it("gives each its type, its own marking, its provenance and its links in view", () => {
    const rows = entityRows(fixture().graph);
    const okafor = rows.find((r) => r.id === "p1")!;
    expect(okafor).toMatchObject({ type: "Person", marking: "OFFICIAL", provenance: "asserted", links: 3 });
    const brennan = rows.find((r) => r.id === "p3")!;
    expect(brennan).toMatchObject({ marking: "SECRET", provenance: "inferred", links: 1 });
  });

  it("says inferred in words, never only by a stroke (rule 5)", () => {
    expect(provenanceText("inferred")).toBe("Inferred");
    expect(provenanceText("asserted")).toBe("Asserted");
    expect(provenanceText("unresolved")).toBe("Unresolved");
  });

  it("marks a node the cross-filter dims, and keeps it (§2 rule 2: filters dim, they do not remove)", () => {
    const rows = entityRows(fixture().graph, new Set(["p2"]));
    expect(rows).toHaveLength(4);
    expect(rows.find((r) => r.id === "p2")?.dimmed).toBe(true);
    expect(rows.find((r) => r.id === "p1")?.dimmed).toBe(false);
  });

  it("never shows a node the working set does not hold: removed, it is gone from the rows", () => {
    const ws = fixture();
    ws.store.getState().applyDelta({ seq: 2, op: "remove", node_ids: ["p3"] });
    const rows = entityRows(ws.graph);
    expect(rows.map((r) => r.id)).not.toContain("p3");
    // Its link went with it, and the count of links in view says so.
    expect(rows.find((r) => r.id === "p1")?.links).toBe(2);
    expect(linkRows(ws.graph, []).map((r) => r.id)).not.toContain("l3");
  });

  it("carries no number about what is withheld: a row is only what the reader's view holds", () => {
    const ws = fixture();
    expect(ws.store.getState().withheld).toBe(true);
    const rows = entityRows(ws.graph);
    expect(rows).toHaveLength(ws.graph.order);
    for (const row of rows) {
      expect(Object.keys(row).sort()).toEqual(["dimmed", "id", "links", "marking", "name", "provenance", "type"]);
    }
  });
});

describe("the Matrix view's link rows", () => {
  it("has one row per link, read by its type's label and its ends' names", () => {
    const rows = linkRows(fixture().graph, [{ name: "USES", label: "Uses" }]);
    expect(rows).toHaveLength(3);
    const uses = rows.find((r) => r.id === "l2")!;
    expect(uses).toMatchObject({
      type: "Uses",
      from: "OKAFOR, Callum",
      fromId: "p1",
      to: "+447700900123",
      toId: "e1",
      provenance: "inferred",
      marking: "OFFICIAL",
      dimmed: false,
    });
    expect(rows.find((r) => r.id === "l1")?.type).toBe("Associate of");
  });

  it("marks a link the cross-filter dims", () => {
    const rows = linkRows(fixture().graph, [], new Set(["l1"]));
    expect(rows.find((r) => r.id === "l1")?.dimmed).toBe(true);
  });
});

describe("sorting and paging", () => {
  it("sorts by a column either way, numbers as numbers, names as a person reads them", () => {
    const rows = entityRows(fixture().graph);
    expect(sortRows(rows, "name", "ascending").map((r) => r.id)).toEqual(["e1", "p2", "p3", "p1"]);
    expect(sortRows(rows, "name", "descending").map((r) => r.id)).toEqual(["p1", "p3", "p2", "e1"]);
    expect(sortRows(rows, "links", "descending")[0]?.id).toBe("p1");
    // Ties keep a fixed order (by name), so a re-sort never shuffles rows.
    expect(sortRows(rows, "links", "ascending").map((r) => r.id)).toEqual(["e1", "p2", "p3", "p1"]);
  });

  it("pages a long view and says which rows are shown — never a silent cut (rule 2)", () => {
    const rows = Array.from({ length: 250 }, (_, i) => ({ id: `n${i}` }));
    const first = pageOf(rows, 0);
    expect(PAGE_SIZE).toBe(100);
    expect(first).toMatchObject({ page: 0, pages: 3, first: 1, last: 100, total: 250 });
    expect(first.rows).toHaveLength(100);
    const last = pageOf(rows, 2);
    expect(last).toMatchObject({ first: 201, last: 250, total: 250 });
    expect(last.rows).toHaveLength(50);
    // Every row is on exactly one page.
    const seen = [0, 1, 2].flatMap((p) => pageOf(rows, p).rows.map((r) => r.id));
    expect(new Set(seen).size).toBe(250);
    // A page past the end shows the last one.
    expect(pageOf(rows, 9).page).toBe(2);
    expect(pageOf([], 0)).toMatchObject({ page: 0, pages: 1, first: 0, last: 0, total: 0 });
  });

  it("finds the page a row is on, so a selection made on the canvas is shown", () => {
    const rows = Array.from({ length: 250 }, (_, i) => ({ id: `n${i}` }));
    expect(pageContaining(rows, "n0")).toBe(0);
    expect(pageContaining(rows, "n150")).toBe(1);
    expect(pageContaining(rows, "missing")).toBeNull();
  });
});
