// @vitest-environment jsdom
// The Matrix view at §5's scale (`02_GLASS_FRONTEND.md` §5: "Initial working-set render < 2.5 s to
// first interactive frame", measured against a 50k-node / 250k-edge working set): opening it over
// that working set — every row worked out and sorted, one page drawn — stays inside 2.5 s here, in
// jsdom, which draws more slowly than a browser. What keeps it there is structural, and asserted as
// well as timed: a page is a hundred rows, whatever the working set holds, and the caption says so.
import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { FIXTURE_EDGE_COUNT, FIXTURE_NODE_COUNT, generateFixture } from "../../perf/fixture";
import { createWorkingSet } from "../workingset/store";
import { MatrixView } from "./MatrixView";
import { PAGE_SIZE } from "./matrixRows";

afterEach(cleanup);

/** §5's first-interactive-frame budget. */
const BUDGET_MS = 2_500;

describe("MatrixView at 50,000 nodes and 250,000 links", () => {
  it("opens inside §5's first-frame budget, drawing one page of each table and saying so", () => {
    const ws = createWorkingSet();
    const { nodes, edges } = generateFixture();
    ws.store.getState().applyDelta({ seq: 1, op: "snapshot", nodes, edges });
    expect(ws.graph.order).toBe(FIXTURE_NODE_COUNT);
    expect(ws.graph.size).toBe(FIXTURE_EDGE_COUNT);

    const started = performance.now();
    render(
      <MatrixView
        graph={ws.graph}
        store={ws.store}
        edgeTypes={[]}
        selectedNodeIds={[]}
        selectedEdgeId={null}
        onSelectNodes={vi.fn()}
        onSelectLink={vi.fn()}
        onExpand={vi.fn()}
        onShowOnGraph={vi.fn()}
      />,
    );
    const elapsed = performance.now() - started;

    const entities = screen.getByRole("grid", { name: /^Entities in this view/ });
    const links = screen.getByRole("grid", { name: /^Links in this view/ });
    expect(within(entities).getAllByRole("rowheader")).toHaveLength(PAGE_SIZE);
    expect(within(links).getAllByRole("rowheader")).toHaveLength(PAGE_SIZE);
    expect(entities.querySelector("caption")?.textContent).toContain("Rows 1 to 100 of 50,000.");
    expect(links.querySelector("caption")?.textContent).toContain("Rows 1 to 100 of 250,000.");
    expect(elapsed, `opened in ${Math.round(elapsed)} ms`).toBeLessThan(BUDGET_MS);
  }, 60_000);
});
