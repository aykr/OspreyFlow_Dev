// The canvas-look comparison's harness (ADR-152 decision 9; slice WS4a): the real `GlassCanvas`, drawing one fixed
// synthetic scene at a time, so `canvas-compare.spec.ts` can compare the whole painted canvas against a reference
// image kept in the repository. Not part of the shipped app.
//
// `?scene=<name>` chooses the scene (`SCENES` below); none draws the plain-links scene. Each scene is the same every
// time: the nodes, links and their places are written here, and the layout's own result never reaches the picture.
// The canvas arranges what it is given as it always does; once that has settled, the spec calls `__COMPARE__.pin()`,
// which puts every node at its place below, and fits the view to them (`F`, as a person fits it). The renderer scales
// the graph's extent into the canvas, so after the fit the picture depends only on these places and the canvas's size.
//
// The faces are the product's own (`src/design/fonts`), and `__COMPARE__.facesLoaded` says whether they loaded: a
// picture drawn in a fallback face is not compared, since it is not the look.
import { createRoot } from "react-dom/client";
import { createRef } from "react";

import "../../../packages/design/tokens.css";
import "../../../packages/design/primitives.css";
import { applyHarnessBrand } from "./brandHarness";
import { loadLookFaces } from "./lookFaces";
import { applyTheme, createWorkingSet, OntologyRegistry } from "@ospreyflow/glass-shared";
import { GlassCanvas, type GlassCanvasHandle } from "../src/canvas/GlassCanvas";
import { NODE_LABEL_FONT } from "../src/canvas/nodeLabel";
import type { Edge, Node, OntologySchema } from "../../../packages/schemas/generated";

declare global {
  interface Window {
    __COMPARE__?: {
      scene: string;
      /** Every node id the scene draws, for the spec to wait on. */
      nodeIds: string[];
      /** The product's label face loaded (false: the picture would be drawn in a fallback). */
      facesLoaded: boolean;
      /** Puts each node at its fixed place; the spec then fits the view. */
      pin: () => void;
    };
    __CANVAS__?: Pick<GlassCanvasHandle, "viewportPositionOf" | "cameraState" | "zoomTo" | "exportImage">;
  }
}

const SCHEMA: OntologySchema = {
  version: 1,
  entity_types: [
    {
      name: "Person",
      pole_class: "person",
      channel: "indigo",
      shape: "circle",
      icon: "person",
      identifiers: [],
      properties: [{ name: "family_name", type: "string", indexed: true }],
    },
    {
      name: "Endpoint",
      pole_class: "object",
      channel: "cyan",
      shape: "hexagon",
      icon: "device",
      icon_by_value: { property: "endpoint_kind", icons: { msisdn: "phone", handle: "keypad", account: "account" } },
      identifiers: [],
    },
    { name: "Organisation", pole_class: "organisation", channel: "azure", shape: "square", identifiers: [] },
    { name: "Location", pole_class: "location", channel: "ochre", shape: "pin", identifiers: [] },
  ],
  edge_types: [
    { name: "KNOWS", from: ["Person"], to: ["Person"], directed: false, basis: "direct" },
    { name: "OWNS", from: ["Person"], to: ["Person"], directed: true, basis: "direct" },
    { name: "LIKELY_KNOWS", from: ["Person"], to: ["Person"], directed: false, basis: "probabilistic", colour: "jade" },
    { name: "LIKELY_OWNS", from: ["Person"], to: ["Person"], directed: true, basis: "probabilistic" },
    { name: "KNOWS_WELL", from: ["Person"], to: ["Person"], directed: false, basis: "direct", thickness: 5, colour: "rose" },
    { name: "USES", from: ["Person"], to: ["Endpoint"], directed: true },
  ],
};

const PROVENANCE = {
  state: "asserted" as const,
  sources: [{ document_id: "fixture-doc", locator: "p.1", excerpt_hash: "a".repeat(64) }],
  first_seen: "2026-01-01T00:00:00Z",
};
const HANDLING = { classification: "OFFICIAL", handling_code: "P", originator: "unit-1", owning_unit: "unit-1" };
const AUDIT = { created_at: "2026-01-01T00:00:00Z", created_by: "fixture" };

function node(id: string, overrides: Partial<Node> = {}): Node {
  return { id, type: "Person", properties: { family_name: id }, provenance: PROVENANCE, handling: HANDLING, audit: AUDIT, ...overrides };
}

function edge(id: string, source: string, target: string, type: string, extra: Partial<Edge> = {}): Edge {
  return { id, type, source, target, provenance: PROVENANCE, handling: HANDLING, audit: AUDIT, ...extra };
}

interface Scene {
  nodes: Node[];
  edges: Edge[];
  /** Each node's fixed place, in the graph's own units (y grows downwards on the canvas). */
  at: Record<string, [number, number]>;
  selectedNodeIds?: string[];
  selectedEdgeId?: string;
}

/** One pair a row for each way a link is drawn (ADR-081, ADR-097 step 2), as `harness.tsx`'s `link-style` fixture. */
function linksScene(): Scene {
  const kinds: Array<[string, string, Partial<Edge>]> = [
    ["solid", "KNOWS", {}],
    ["arrow", "OWNS", {}],
    ["dotted", "LIKELY_KNOWS", {}],
    ["dotted-arrow", "LIKELY_OWNS", {}],
    ["thick", "KNOWS_WELL", {}],
    ["marked", "KNOWS", { basis: "probabilistic" }],
    ["inferred", "KNOWS", { provenance: { state: "inferred", sources: [], first_seen: "2026-01-01T00:00:00Z" } }],
    ["unresolved", "KNOWS", { provenance: { state: "unresolved", sources: [], first_seen: "2026-01-01T00:00:00Z" } }],
    ["light", "KNOWS", { weight: 0.05 }],
    ["heavy", "KNOWS", { weight: 0.95 }],
  ];
  const scene: Scene = { nodes: [], edges: [], at: {} };
  kinds.forEach(([kind, type, extra], row) => {
    scene.nodes.push(node(`${kind}-a`), node(`${kind}-b`));
    scene.edges.push(edge(`${kind}-link`, `${kind}-a`, `${kind}-b`, type, extra));
    scene.at[`${kind}-a`] = [0, row * 10];
    scene.at[`${kind}-b`] = [100, row * 10];
  });
  return scene;
}

/** A node of each shape and drawing (`@sigma/node-image`'s icons in their shapes), on a ring of plain links. */
function nodesScene(): Scene {
  const nodes = [
    node("person"),
    node("phone", { type: "Endpoint", properties: { endpoint_kind: "msisdn" } }),
    node("keypad", { type: "Endpoint", properties: { endpoint_kind: "handle" } }),
    node("account", { type: "Endpoint", properties: { endpoint_kind: "account" } }),
    node("device", { type: "Endpoint", properties: {} }),
    node("organisation", { type: "Organisation", properties: {} }),
    node("place", { type: "Location", properties: {} }),
    node("inferred-person", { provenance: { state: "inferred", sources: [], first_seen: "2026-01-01T00:00:00Z" } }),
  ];
  const at: Scene["at"] = {};
  nodes.forEach((n, i) => (at[n.id] = [(i % 4) * 40, Math.floor(i / 4) * 40]));
  const edges = [
    edge("uses-1", "person", "phone", "USES"),
    edge("uses-2", "person", "keypad", "USES"),
    edge("uses-3", "inferred-person", "account", "USES"),
  ];
  return { nodes, edges, at };
}

/** Labels: short, long enough to be cut in the middle (over 28 characters), and at the canvas's right edge. */
function labelsScene(): Scene {
  const names = ["Ash", "Birch Hollowmere", "Corriander-Westbrook Fennimore Halloway", "Dunmore", "Elmstead Vale"];
  const nodes = names.map((name, i) => node(`label-${i}`, { properties: { family_name: name } }));
  const at: Scene["at"] = {};
  nodes.forEach((n, i) => (at[n.id] = [i * 30, (i % 2) * 25]));
  const edges = [edge("label-link-0", "label-0", "label-1", "KNOWS"), edge("label-link-1", "label-2", "label-3", "KNOWS")];
  return { nodes, edges, at };
}

/** A small chain to select in: a node selected, or a link. */
function chainScene(): Scene {
  const ids = ["c0", "c1", "c2", "c3"];
  const nodes = ids.map((id) => node(id));
  const at: Scene["at"] = { c0: [0, 0], c1: [50, 20], c2: [100, 0], c3: [150, 20] };
  const edges = [edge("c-link-0", "c0", "c1", "KNOWS"), edge("c-link-1", "c1", "c2", "OWNS"), edge("c-link-2", "c2", "c3", "LIKELY_KNOWS")];
  return { nodes, edges, at };
}

/** ADR-119: over 10,000 links, so the canvas groups by community and, at the fitted view, draws one link between each
 * pair of communities (`communityLinkLayer.ts`) in place of every link. Eight communities of 60, each fully linked
 * within (8 × 1,770 = 14,160 links), and community `i` linked to the next by `i + 1` links, so the links between
 * communities differ in width. Each community sits on a small ring of its own, the eight on a large one. The
 * communities are found by the canvas's own seeded Louvain (`communities.ts`), so they are the same every time. */
function communitiesScene(): Scene {
  const scene: Scene = { nodes: [], edges: [], at: {} };
  const COMMUNITIES = 8;
  const SIZE = 60;
  const id = (c: number, n: number) => `k${c}-${n}`;
  for (let c = 0; c < COMMUNITIES; c++) {
    const cx = 400 * Math.cos((2 * Math.PI * c) / COMMUNITIES);
    const cy = 400 * Math.sin((2 * Math.PI * c) / COMMUNITIES);
    for (let n = 0; n < SIZE; n++) {
      scene.nodes.push(node(id(c, n)));
      scene.at[id(c, n)] = [cx + 60 * Math.cos((2 * Math.PI * n) / SIZE), cy + 60 * Math.sin((2 * Math.PI * n) / SIZE)];
      for (let m = 0; m < n; m++) scene.edges.push(edge(`k${c}-${m}-${n}`, id(c, m), id(c, n), "KNOWS"));
    }
  }
  for (let c = 0; c < COMMUNITIES; c++) {
    const next = (c + 1) % COMMUNITIES;
    for (let k = 0; k <= c; k++) scene.edges.push(edge(`between-${c}-${k}`, id(c, k), id(next, k), "KNOWS"));
  }
  return scene;
}

export const SCENES: Record<string, () => Scene> = {
  communities: communitiesScene,
  links: linksScene,
  nodes: nodesScene,
  labels: labelsScene,
  chain: chainScene,
  "selected-node": () => ({ ...chainScene(), selectedNodeIds: ["c1"] }),
  "selected-link": () => ({ ...chainScene(), selectedEdgeId: "c-link-1" }),
};

const sceneName = new URLSearchParams(window.location.search).get("scene") ?? "links";
const make = SCENES[sceneName];
if (!make) throw new Error(`no scene ${sceneName}; the scenes are ${Object.keys(SCENES).join(", ")}`);
const scene = make();

const workingSet = createWorkingSet();
const ontology = new OntologyRegistry(SCHEMA);
workingSet.store.getState().applyDelta({ seq: 1, op: "snapshot", nodes: scene.nodes, edges: scene.edges });

await applyHarnessBrand();
applyTheme("dark");
await import("../src/design/fonts");
await loadLookFaces(["400", "600"], [`400 11px ${NODE_LABEL_FONT}`]);
const facesLoaded = document.fonts.check(`400 11px 'Atkinson Hyperlegible Next'`);


const canvasHandle = createRef<GlassCanvasHandle>();
window.__CANVAS__ = {
  viewportPositionOf: (id) => canvasHandle.current?.viewportPositionOf(id) ?? null,
  cameraState: () => canvasHandle.current?.cameraState() ?? null,
  zoomTo: (ratio) => canvasHandle.current?.zoomTo(ratio),
  exportImage: (mark) => canvasHandle.current!.exportImage(mark),
};
window.__COMPARE__ = {
  scene: sceneName,
  nodeIds: scene.nodes.map((n) => n.id),
  facesLoaded,
  pin: () => {
    for (const [id, [x, y]] of Object.entries(scene.at)) {
      // Sigma's y grows upwards; the places above are written as the canvas shows them.
      workingSet.graph.mergeNodeAttributes(id, { x, y: -y });
    }
  },
};

const container = document.getElementById("root");
if (!container) throw new Error("#root not found");
createRoot(container).render(
  <GlassCanvas
    ref={canvasHandle}
    graph={workingSet.graph}
    store={workingSet.store}
    ontology={ontology}
    edgeTypes={SCHEMA.edge_types}
    entityTypes={SCHEMA.entity_types}
    investigationId="canvas-compare"
    apiBaseUrl="http://canvas-compare.invalid"
    bearerToken="unused"
    toolbarHidden
    initialSelectedNodeIds={scene.selectedNodeIds}
    initialSelectedEdgeId={scene.selectedEdgeId ?? null}
  />,
);
