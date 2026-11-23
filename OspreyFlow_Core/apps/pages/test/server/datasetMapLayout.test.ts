/**
 * The dataset map's stage order is held to the canvas's layout (slice IS3).
 *
 * `server/views/datasetMapWords.ts` writes the canvas's layout once more (`stageIds`), because the table needs the order and
 * not the drawing, and a server file cannot import the workspace's `pipelineLayout.ts`. This test is what keeps the copy honest:
 * both are run on the same graphs, and the page's order must be the layout's own (a stage by its column, then its row). The
 * canvas's words (`KIND_NAMES`) are held to the page's by `tests/glass_trees/test_dataset_map_scenario.py`.
 *
 * Which test fails if the copy drifts (rule 12): `stageIds`, on each graph below; the planted case at the end shows the
 * comparison itself can fail (rule 15).
 */
import { beforeAll, describe, expect, it } from "vitest";

import { stageIds } from "../../server/views/datasetMapWords.js";

interface Graph {
  nodes: { id: string; kind: string; label: string; config: Record<string, unknown> }[];
  edges: { source: string; target: string }[];
}
interface Placed {
  id: string;
  column: number;
  row: number;
}

/** The workspace's own file, loaded when the test runs and named by a variable, so that the compiler does not read it. */
const LAYOUT = new URL("../../../workspace/src/ingest/dag/pipelineLayout.ts", import.meta.url).href;
let canvas: (graph: Graph) => Placed[];
beforeAll(async () => {
  canvas = ((await import(/* @vite-ignore */ LAYOUT)) as { pipelineLayout: (graph: Graph) => Placed[] }).pipelineLayout;
});

const n = (id: string, kind = "source") => ({ id, kind, label: id, config: {} });
const e = (source: string, target: string) => ({ source, target });
const order = (placed: Placed[]): string[] => [...placed].sort((a, b) => a.column - b.column || a.row - b.row).map((p) => p.id);

const GRAPHS: Record<string, Graph> = {
  empty: { nodes: [], edges: [] },
  one: { nodes: [n("a")], edges: [] },
  chain: { nodes: [n("l", "load"), n("m", "map"), n("s")], edges: [e("s", "m"), e("m", "l")] },
  "two sources into one map": { nodes: [n("m", "map"), n("b"), n("a"), n("d", "domain_model")], edges: [e("a", "m"), e("b", "m"), e("d", "m")] },
  diamond: { nodes: [n("z"), n("y"), n("x"), n("w")], edges: [e("w", "x"), e("w", "y"), e("x", "z"), e("y", "z")] },
  "a long way round": { nodes: [n("end", "load"), n("a"), n("b"), n("c"), n("s")], edges: [e("s", "a"), e("a", "b"), e("b", "c"), e("c", "end"), e("s", "end")] },
  "an edge to a stage that is not there": { nodes: [n("a"), n("b")], edges: [e("ghost", "b")] },
  "a cycle, which a saved graph never has": { nodes: [n("a"), n("b")], edges: [e("a", "b"), e("b", "a")] },
};

describe("the dataset map's stage order is the canvas's layout", () => {
  for (const [name, graph] of Object.entries(GRAPHS)) {
    it(`${name}`, () => {
      expect(stageIds(graph)).toEqual(order(canvas(graph)));
    });
  }

  it("a drift in the copy is seen: the same graphs in list order are not the canvas's order", () => {
    const graph = GRAPHS["chain"] as Graph;
    expect(order(canvas(graph))).toEqual(["s", "m", "l"]);
    const listOrder = graph.nodes.map((node) => node.id);
    expect(listOrder).not.toEqual(order(canvas(graph)));
    expect(stageIds(graph)).not.toEqual(listOrder);
  });
});
