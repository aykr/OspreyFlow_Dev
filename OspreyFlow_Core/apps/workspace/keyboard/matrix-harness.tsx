// The Matrix view harness (`02_GLASS_FRONTEND.md` §6; GDS remediation plan A1), for
// `matrix.spec.ts` and the axe scans of `a11y/every-harness.spec.ts`.
//
// The real top bar's view switch, the real canvas and the real Matrix view over one working set,
// wired as `App.tsx` wires them: one selection both report to, the canvas opened with it
// (`initialSelectedNodeIds`), and a row's Expand and Show done by the canvas once the Graph is
// drawn. `App.matrix.test.tsx` holds `App.tsx` itself to the same wiring. `window.__MATRIX__` lets
// the spec read the selection; what the canvas holds is read from the page (its selection bar).
//
// It opens on the Matrix, so the axe scans of the page scan the Matrix; `?view=graph` opens on the
// canvas (the keyboard spec's start). `?many=1` holds 250 more people, so the Matrix pages (rule 2:
// it says which rows are shown); `?select=p2,p4` opens with those selected.
import { useEffect, useRef, useState } from "react";
import { createRoot } from "react-dom/client";

import "../src/design/tokens.css";
import "../src/design/primitives.css";
import { applyHarnessBrand } from "./brandHarness";
import { GlassCanvas, type GlassCanvasHandle } from "../src/canvas/GlassCanvas";
import { MatrixView } from "../src/matrix/MatrixView";
import { OntologyRegistry } from "../src/ontology/schema";
import { TopBar } from "../src/shell/TopBar";
import { createWorkingSet } from "../src/workingset/store";
import type { Edge, Node, OntologySchema } from "../../../packages/schemas/generated";

declare global {
  interface Window {
    __MATRIX__?: { view: "graph" | "matrix"; selection: string[]; selectedEdge: string | null };
  }
}

await applyHarnessBrand();

const SCHEMA: OntologySchema = {
  version: 1,
  entity_types: [
    { name: "Person", pole_class: "person", channel: "indigo", shape: "circle", icon: "person", identifiers: [] },
    { name: "Endpoint", pole_class: "object", channel: "cyan", shape: "hexagon", icon: "device", identifiers: [] },
  ],
  edge_types: [
    { name: "ASSOCIATE_OF", from: ["Person"], to: ["Person"], directed: false },
    { name: "USES", from: ["Person"], to: ["Endpoint"], directed: true, label: "Uses" },
  ],
};

function node(id: string, overrides: Partial<Node> = {}): Node {
  return {
    id,
    type: "Person",
    properties: {},
    provenance: {
      state: "asserted",
      sources: [{ document_id: "fixture-doc", locator: "p.1", excerpt_hash: "a".repeat(64) }],
      first_seen: "2026-01-01T00:00:00Z",
    },
    handling: { classification: "OFFICIAL", handling_code: "P", originator: "unit-1", owning_unit: "unit-1" },
    audit: { created_at: "2026-01-01T00:00:00Z", created_by: "fixture" },
    ...overrides,
  };
}

function edge(id: string, source: string, target: string, type = "ASSOCIATE_OF", overrides: Partial<Edge> = {}): Edge {
  return {
    id,
    type,
    source,
    target,
    provenance: {
      state: "asserted",
      sources: [{ document_id: "fixture-doc", locator: "p.1", excerpt_hash: "a".repeat(64) }],
      first_seen: "2026-01-01T00:00:00Z",
    },
    handling: { classification: "OFFICIAL", handling_code: "P", originator: "unit-1", owning_unit: "unit-1" },
    audit: { created_at: "2026-01-01T00:00:00Z", created_by: "fixture" },
    ...overrides,
  };
}

const params = new URLSearchParams(window.location.search);
const many = params.get("many") === "1";
const startView = params.get("view") === "graph" ? "graph" : "matrix";
const startSelection = (params.get("select") ?? "").split(",").filter(Boolean);
const INFERRED = { state: "inferred" as const, sources: [], first_seen: "2026-01-01T00:00:00Z" };
const nodes: Node[] = [
  node("p1", { properties: { family_name: "OKAFOR", given_names: "Callum" } }),
  node("p2", { properties: { family_name: "ADEYEMI", given_names: "Tola" } }),
  node("p3", { properties: { family_name: "BRENNAN", given_names: "Siobhan" }, provenance: INFERRED }),
  node("p4", {
    properties: { family_name: "DUCHESNE", given_names: "Marc" },
    handling: { classification: "SECRET", handling_code: "P", originator: "unit-1", owning_unit: "unit-1" },
  }),
  node("e1", { type: "Endpoint", properties: { value_normalised: "+447700900123" } }),
  ...(many
    ? Array.from({ length: 250 }, (_, i) =>
        node(`m${i}`, { properties: { family_name: `MEMBER${String(i).padStart(3, "0")}` } }),
      )
    : []),
];
const edges: Edge[] = [
  edge("l1", "p1", "p2"),
  edge("l2", "p1", "p3"),
  edge("l3", "p1", "e1", "USES", { provenance: INFERRED }),
  edge("l4", "p2", "p4"),
];

const workingSet = createWorkingSet();
// The reader's view, as the stream delivers it: the case holds more than this reader may see, and
// nothing of it is here (rule 3: the adapter leaves it out).
workingSet.store.getState().applyDelta({ seq: 1, op: "snapshot", nodes, edges, withheld: true });
const ontology = new OntologyRegistry(SCHEMA);
// The cross-filter dims one person: dimmed on the canvas, kept and said in the Matrix.
const DIMMED: ReadonlySet<string> = new Set(["p4"]);
const NO_LINKS: ReadonlySet<string> = new Set();

window.__MATRIX__ = { view: startView, selection: startSelection, selectedEdge: null };

function Harness() {
  const [view, setView] = useState<"graph" | "matrix">(startView);
  const [selection, setSelection] = useState<string[]>(startSelection);
  const [selectedEdge, setSelectedEdge] = useState<string | null>(null);
  const canvas = useRef<GlassCanvasHandle>(null);
  const pending = useRef<{ kind: "expand" | "show"; nodeId: string } | null>(null);
  window.__MATRIX__ = { view, selection, selectedEdge };

  useEffect(() => {
    if (view !== "graph" || !pending.current) return;
    const { kind, nodeId } = pending.current;
    pending.current = null;
    const frame = requestAnimationFrame(() => {
      if (kind === "expand") canvas.current?.expandNode(nodeId);
      else canvas.current?.focusOnNode(nodeId);
    });
    return () => cancelAnimationFrame(frame);
  }, [view]);

  const selectNodes = (ids: string[]) => {
    setSelection(ids);
    setSelectedEdge(null);
  };
  const onGraph = (kind: "expand" | "show") => (nodeId: string) => {
    selectNodes([nodeId]);
    pending.current = { kind, nodeId };
    setView("graph");
  };

  return (
    <>
      <TopBar
        app="glass"
        caseSwitcher={<span>Case: Matrix fixture</span>}
        account={null}
        views={[
          { id: "graph", label: "Graph", pressed: view === "graph", onSelect: () => setView("graph") },
          { id: "matrix", label: "Matrix", pressed: view === "matrix", onSelect: () => setView("matrix") },
        ]}
      />
      <main style={{ position: "relative", height: "calc(100vh - 48px)" }}>
        {view === "graph" ? (
          <GlassCanvas
            ref={canvas}
            graph={workingSet.graph}
            store={workingSet.store}
            ontology={ontology}
            edgeTypes={SCHEMA.edge_types}
            entityTypes={SCHEMA.entity_types}
            investigationId="matrix-fixture"
            apiBaseUrl="http://keyboard-test.invalid"
            bearerToken="unused"
            dimmedNodeIds={DIMMED}
            onSelectionChange={(ids) => {
              setSelection(ids);
              if (ids.length > 0) setSelectedEdge(null);
            }}
            onEdgeSelect={(e) => setSelectedEdge(e?.id ?? null)}
            initialSelectedNodeIds={selection}
            initialSelectedEdgeId={selectedEdge}
          />
        ) : (
          <MatrixView
            graph={workingSet.graph}
            store={workingSet.store}
            edgeTypes={SCHEMA.edge_types}
            visualFor={(type) => ontology.visualFor(type)}
            dimmedNodeIds={DIMMED}
            dimmedEdgeIds={NO_LINKS}
            selectedNodeIds={selection}
            selectedEdgeId={selectedEdge}
            onSelectNodes={selectNodes}
            onSelectLink={(id) => {
              setSelection([]);
              setSelectedEdge(id);
            }}
            onExpand={onGraph("expand")}
            onShowOnGraph={onGraph("show")}
          />
        )}
      </main>
    </>
  );
}

const container = document.getElementById("root");
if (!container) throw new Error("#root not found");
createRoot(container).render(<Harness />);
