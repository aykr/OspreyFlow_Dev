// Keyboard-only walkthrough harness — `spec/02_GLASS_FRONTEND.md` §6's
// accessibility floor ("Every canvas action reachable by keyboard"),
// This phase's exit criterion ("Keyboard navigation
// reaches every canvas action"). A small, real graph (not the 50k perf
// fixture — this test is about reachability, not scale) rendered with
// `GlassCanvas` alone, exposing `window.__KEYBOARD__` so
// `keyboard.spec.ts` can observe focus/selection state it has no other
// way to reach, and a real `expand` network call `keyboard.spec.ts`
// intercepts via `page.route` rather than this harness faking it.
import { createRoot } from "react-dom/client";
import { createRef, useEffect, useState } from "react";

import "../src/design/tokens.css";
import { applyTheme } from "../src/theme/theme";
import "../src/design/primitives.css";
import { GlassCanvas, type GlassCanvasHandle } from "../src/canvas/GlassCanvas";
import { SelectionList } from "../src/inspector/SelectionList";
import { createCrossFilterStore } from "../src/crossfilter/store";
import { OntologyRegistry } from "../src/ontology/schema";
import { Timeline } from "../src/timeline/Timeline";
import { createWorkingSet } from "../src/workingset/store";
import type { OntologySchema, Node, Edge } from "../../../packages/schemas/generated";

declare global {
  interface Window {
    __KEYBOARD__?: {
      focused: string | null;
      selection: string[];
      viewMessagesNodeId: string | null;
      selectedEdge: string | null;
      /** The last link-menu entry that hands over to the Inspector (ADR-080): which link and what. */
      linkAction: { edgeId: string; action: string } | null;
      /** The case the canvas was told a branch of the selection was made as (ADR-084). */
      branchedTo: string | null;
      /** The case the selection was branched to so the model could be asked about it (ADR-098). */
      askedIn: string | null;
      /** The Document the canvas asked to open to read (ADR-092). */
      openedDocument: string | null;
      /** The node whose menu asked for the Inspector's Picture part (ADR-105 Amendment 1). */
      pictureRequested?: string | null;
    };
    __CANVAS__?: {
      viewportPositionOf: (nodeId: string) => { x: number; y: number } | null;
      cameraState: () => { x: number; y: number; ratio: number } | null;
      zoomTo: (ratio: number) => void;
      /** Pans to a node and focuses it (ADR-093). */
      centreOn: (nodeId: string) => void;
      expandFrom: (nodeId: string, depth: number) => void;
      expandNode: (nodeId: string) => void;
      /** The name the canvas draws beside a node now; empty when it draws none. */
      labelOf: (nodeId: string) => string | null;
      /** Whether the canvas draws a link now (ADR-117: a type left out from the legend is not). */
      linkDrawn: (edgeId: string) => boolean | null;
      /** The fill colour stored on a node now, which is what the canvas paints it with. */
      nodeColour: (nodeId: string) => string | null;
      setTheme: (theme: "dark" | "light") => void;
      /** The picture stored on a node now (a data address of its shape and icon), which is what the canvas draws. */
      nodeImage: (nodeId: string) => string | null;
      /** Whether the working set holds this node now (ADR-092: an email put on the canvas). */
      hasNode: (nodeId: string) => boolean;
      /** Land a `reproject` delta, as the server sends when the resolution slider moves: each node
       * named takes the cluster id given. */
      reproject: (clusterIds: Record<string, string>) => void;
      /** The cluster id the working set holds on a node now (ADR-124: what a manual link's answer
       * moved), or `null` when it holds none. */
      clusterOf: (nodeId: string) => string | null;
    };
    /** How many nodes are folded into Group Nodes now (ADR-066). */
    __GROUPED__?: number;
  }
}

const BASE_SCHEMA: OntologySchema = {
  version: 1,
  entity_types: [
    {
      name: "Person",
      pole_class: "person",
      channel: "indigo",
      shape: "circle",
      icon: "person",
      identifiers: [],
      // What the Labels control (ADR-076) offers for a person in the fixture.
      properties: [
        { name: "family_name", type: "string", indexed: true },
        { name: "given_names", type: "string", indexed: true },
      ],
    },
    // Phase 6a Stage 4 (B6): the only fixture data the "View messages" radial-menu item needs —
    // it is offered on `Endpoint`-type nodes specifically (`GlassCanvas.tsx`'s own condition).
    { name: "Endpoint", pole_class: "object", channel: "cyan", shape: "hexagon", icon: "phone", identifiers: [] },
  ],
  edge_types: [
    { name: "ASSOCIATE_OF", from: ["Person"], to: ["Person"], directed: false },
    { name: "USES", from: ["Person"], to: ["Endpoint"], directed: true },
    // ADR-105 Amendment 1: a Person may have a picture, so its menu offers Set picture….
    { name: "DEPICTS", from: ["Document"], to: ["Person"], directed: true },
  ],
};

function node(id: string, overrides: Partial<Node> = {}): Node {
  return {
    id,
    type: "Person",
    properties: { family_name: id },
    provenance: {
      state: "asserted",
      sources: [{ document_id: "fixture-doc", locator: "p.1", excerpt_hash: "a".repeat(64) }],
      first_seen: "2026-01-01T00:00:00Z",
    },
    handling: {
      classification: "OFFICIAL",
      handling_code: "P",
      originator: "unit-1",
      owning_unit: "unit-1",
    },
    audit: { created_at: "2026-01-01T00:00:00Z", created_by: "fixture" },
    ...overrides,
  };
}

function edge(id: string, source: string, target: string, type = "ASSOCIATE_OF"): Edge {
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
    handling: {
      classification: "OFFICIAL",
      handling_code: "P",
      originator: "unit-1",
      owning_unit: "unit-1",
    },
    audit: { created_at: "2026-01-01T00:00:00Z", created_by: "fixture" },
  };
}

const canvasHandle = createRef<GlassCanvasHandle>();
window.__CANVAS__ = {
  viewportPositionOf: (id) => canvasHandle.current?.viewportPositionOf(id) ?? null,
  cameraState: () => canvasHandle.current?.cameraState() ?? null,
  zoomTo: (ratio) => canvasHandle.current?.zoomTo(ratio),
  centreOn: (id) => canvasHandle.current?.centreOn(id),
  expandFrom: (id, depth) => canvasHandle.current?.expandFrom(id, depth),
  expandNode: (id) => canvasHandle.current?.expandNode(id),
  labelOf: (id) => canvasHandle.current?.labelOf(id) ?? null,
  linkDrawn: (id) => canvasHandle.current?.linkDrawn(id) ?? null,
  nodeColour: (id) => (workingSet.graph.hasNode(id) ? (workingSet.graph.getNodeAttribute(id, "color") as string) : null),
  setTheme: (theme) => applyTheme(theme),
  nodeImage: (id) => (workingSet.graph.hasNode(id) ? (workingSet.graph.getNodeAttribute(id, "image") as string) : null),
  hasNode: (id) => workingSet.graph.hasNode(id),
  reproject: (clusterIds) =>
    workingSet.store.getState().applyDelta({
      seq: workingSet.store.getState().seq + 1,
      op: "reproject",
      reason: "keyboard fixture",
      affected_cluster_ids: clusterIds,
    }),
  clusterOf: (id) =>
    workingSet.graph.hasNode(id)
      ? (workingSet.graph.getNodeAttribute(id, "data").resolution?.cluster_id ?? null)
      : null,
};

window.__KEYBOARD__ = {
  focused: null,
  selection: [],
  viewMessagesNodeId: null,
  selectedEdge: null,
  linkAction: null,
  branchedTo: null,
  askedIn: null,
  openedDocument: null,
};

// `?fixture=same-as` is the link menu's fixture (ADR-080); every other fixture leaves `SAME_AS` out
// of the schema, so the node menu's items — and the Tab counts the walkthroughs rely on — stay put.
const wantsSameAs = new URLSearchParams(window.location.search).get("fixture") === "same-as";
const sameOrigin = new URLSearchParams(window.location.search).get("api") === "same-origin";
// `?fixture=link-style` is how links are drawn by basis (ADR-081): five pairs of people, each pair
// joined by one link of a type that is drawn a different way.
const wantsLinkStyle = new URLSearchParams(window.location.search).get("fixture") === "link-style";
/** `?last-change=…`: the toolbar's note, as App passes it (ADR-115 E6). */
const lastChange = new URLSearchParams(window.location.search).get("last-change");
const LINK_STYLE_TYPES: OntologySchema["edge_types"] = [
  { name: "KNOWS", from: ["Person"], to: ["Person"], directed: false, basis: "direct" },
  { name: "OWNS", from: ["Person"], to: ["Person"], directed: true, basis: "direct" },
  { name: "LIKELY_KNOWS", from: ["Person"], to: ["Person"], directed: false, basis: "probabilistic", colour: "jade" },
  { name: "LIKELY_OWNS", from: ["Person"], to: ["Person"], directed: true, basis: "probabilistic" },
  { name: "KNOWS_WELL", from: ["Person"], to: ["Person"], directed: false, basis: "direct", thickness: 5, colour: "rose" },
];
const SCHEMA: OntologySchema = wantsSameAs
  ? {
      ...BASE_SCHEMA,
      edge_types: [
        ...BASE_SCHEMA.edge_types,
        { name: "SAME_AS", from: ["Person"], to: ["Person"], directed: false },
      ],
    }
  : wantsLinkStyle
    ? { ...BASE_SCHEMA, edge_types: [...BASE_SCHEMA.edge_types, ...LINK_STYLE_TYPES] }
    : new URLSearchParams(window.location.search).get("fixture") === "emails"
      ? {
          // ADR-094: an address can hold content, so its menu offers Add files held by this….
          ...BASE_SCHEMA,
          edge_types: [
            ...BASE_SCHEMA.edge_types,
            { name: "HOLDS", from: ["Endpoint"], to: ["Document"], directed: true, basis: "direct" },
          ],
        }
      : BASE_SCHEMA;

const workingSet = createWorkingSet();
const ontology = new OntologyRegistry(SCHEMA);

// A chain n0—n1—n2—n3: `graph.nodes()[0]` (Tab's keyboard entry point) is
// deterministically "n0", and it has exactly one neighbour ("n1"), so the
// arrow-walk assertion has one unambiguous correct answer.
//
// `n2`/`n3` additionally share a `resolution.cluster_id` (Phase 6a Stage 3) — the only fixture
// data needed for the radial menu's "Explain cluster" item to appear at all; it does not depend
// on a `SAME_AS`/`NOT_SAME_AS` edge existing, since `keyboard.spec.ts` mocks the `explain` network
// call rather than exercising a real backend, the same way the existing Enter/Space tests mock
// `expand`/`resolution/link`.
// `n4` is an `Endpoint`, reachable by walking one hop past `n3` (`USES`) — the only fixture data
// the "View messages" item needs to actually be reachable by keyboard, not merely present.
const nodes = [
  node("n0"),
  node("n1"),
  node("n2", { resolution: { cluster_id: "n2" } }),
  node("n3", { resolution: { cluster_id: "n2" } }),
  node("n4", { type: "Endpoint", properties: { value_normalised: "n4" } }),
  // **`n5` is deliberately disconnected — it has no edge to anything, ever.** Round 12d: every
  // other node here is on one chain, so arrow-walk (which follows `graph.neighbors`) can reach
  // all of them, and a walkthrough over this fixture could not tell whether the canvas had a
  // keyboard route to a *non-adjacent* node or merely to an adjacent one. It did not — which is
  // why `Explain cluster` and `Find paths to`, both gated on a two-node selection, were
  // mouse-only in practice for the case that actually matters: two entities found by identifier,
  // which is how an analyst reaches them and which leaves them unconnected until something is
  // expanded. `n5` is the fixture datum that makes that reachable-or-not question answerable.
  // Has given names, so a person's default label ("n5, Zed") differs from the one chosen in the
  // Labels control's keyboard case (ADR-076); every other fixture person has only a family name.
  node("n5", { properties: { family_name: "n5", given_names: "Zed" } }),
];
const edges = [
  edge("e0", "n0", "n1"),
  edge("e1", "n1", "n2"),
  edge("e2", "n2", "n3"),
  edge("e3", "n3", "n4", "USES"),
];
// `?fixture=communities` swaps the chain for two groups of five people, each a hub (`a0`, `b0`)
// with four others round it, joined by one link (a0—b0): what Communities (ADR-066) has to find,
// fold and open. A group is a wheel rather than every-person-to-every-person on purpose: a fully
// linked group of five is pulled into one point by the organic layout, which makes a test of where
// things are drawn meaningless.
const wantsCommunities = new URLSearchParams(window.location.search).get("fixture") === "communities";
if (wantsCommunities) {
  nodes.length = 0;
  edges.length = 0;
  for (const prefix of ["a", "b"]) {
    for (let i = 0; i < 5; i++) nodes.push(node(`${prefix}${i}`));
    for (let i = 1; i < 5; i++) edges.push(edge(`${prefix}0-${prefix}${i}`, `${prefix}0`, `${prefix}${i}`));
    for (let i = 1; i < 5; i++) {
      const next = i === 4 ? 1 : i + 1;
      edges.push(edge(`${prefix}${i}-${prefix}${next}`, `${prefix}${i}`, `${prefix}${next}`));
    }
  }
  edges.push(edge("bridge", "a0", "b0"));
}
// `?fixture=same-as` swaps the chain for three people the engine has matched as one (s0—s1—s2, both
// links SAME_AS, one cluster `s0`) and a fourth, `p0`, tied to s2 by an ordinary link: a same-as link
// to fold, and a link of another type to change.
if (wantsSameAs) {
  nodes.length = 0;
  edges.length = 0;
  for (const id of ["s0", "s1", "s2"]) nodes.push(node(id, { resolution: { cluster_id: "s0" } }));
  nodes.push(node("p0"));
  edges.push(edge("sa0", "s0", "s1", "SAME_AS"));
  edges.push(edge("sa1", "s1", "s2", "SAME_AS"));
  edges.push(edge("ln0", "s2", "p0"));
}
// `?fixture=emails` is ADR-092's: two email addresses, shaped as the Enron loader writes them
// (`endpoint_kind: "email"`), joined by one `COMMUNICATED_WITH` link `em0` that stands for two emails.
const wantsEmails = new URLSearchParams(window.location.search).get("fixture") === "emails";
if (wantsEmails) {
  nodes.length = 0;
  edges.length = 0;
  for (const id of ["ea", "eb"]) {
    nodes.push(
      node(id, {
        type: "Endpoint",
        properties: { value_raw: `${id}@enron.com`, value_normalised: `${id}@enron.com`, endpoint_kind: "email" },
      }),
    );
  }
  edges.push({ ...edge("em0", "ea", "eb", "COMMUNICATED_WITH"), occurrences: 2 });
  // One email already on the canvas as a Document (ADR-092), linked to its sender.
  nodes.push(node("email:ev-1", { type: "Document", properties: { title: "Dabhol" } }));
  edges.push(edge("email:ev-1:mentions:ea", "ea", "email:ev-1", "MENTIONED_IN"));
}
if (wantsLinkStyle) {
  nodes.length = 0;
  edges.length = 0;
  // One pair for each way a link is drawn; each pair is a link `<kind>-link` between `<kind>-a` and `<kind>-b`.
  // `marked` is a link of a Direct type (KNOWS) that carries its own probabilistic basis (ADR-081
  // step B): the link, not its type, decides that it is dotted.
  // ADR-097 step 2: `inferred` and `unresolved` are links of a Direct type whose provenance says so
  // (dashed, dotted); `light` and `heavy` differ only in weight.
  const kinds: Array<[string, string, "probabilistic" | undefined, Partial<Edge>?]> = [
    ["solid", "KNOWS", undefined],
    ["arrow", "OWNS", undefined],
    ["dotted", "LIKELY_KNOWS", undefined],
    ["dotted-arrow", "LIKELY_OWNS", undefined],
    ["thick", "KNOWS_WELL", undefined],
    ["marked", "KNOWS", "probabilistic"],
    ["inferred", "KNOWS", undefined, { provenance: { state: "inferred", sources: [], first_seen: "2026-01-01T00:00:00Z" } }],
    ["unresolved", "KNOWS", undefined, { provenance: { state: "unresolved", sources: [], first_seen: "2026-01-01T00:00:00Z" } }],
    ["light", "KNOWS", undefined, { weight: 0.05 }],
    ["heavy", "KNOWS", undefined, { weight: 0.95 }],
  ];
  // `&kind=dotted` loads that pair alone, which the canvas then fits to the whole screen, so its link is
  // long enough to read pixel by pixel.
  const only = new URLSearchParams(window.location.search).get("kind");
  for (const [kind, type, basis, extra] of kinds) {
    if (only && only !== kind) continue;
    nodes.push(node(`${kind}-a`), node(`${kind}-b`));
    const link = { ...edge(`${kind}-link`, `${kind}-a`, `${kind}-b`, type), ...extra };
    edges.push(basis ? { ...link, basis } : link);
  }
}
workingSet.store.getState().applyDelta({ seq: 1, op: "snapshot", nodes, edges });

const container = document.getElementById("root");
if (!container) throw new Error("#root not found");

// `?fixture=lit` is ADR-128's (B3, select what is lit): the chain above with the real timeline under
// it, so a keyboard walkthrough can set a window by Set exact dates, run Select what is lit, and
// branch what it selected, as App does. The timeline's own reads are answered by the spec.
const wantsLit = new URLSearchParams(window.location.search).get("fixture") === "lit";
const litStore = createCrossFilterStore("http://keyboard-test.invalid", "unused", "keyboard-fixture");

// `?judged=n1:2,n2:1` gives those nodes that many judgements, for the count drawn beside a node
// (ADR-070).
// `?degrees=n0:0,n1:1` marks those nodes with their degree from From (ADR-116), as Find connections does.
const degrees = new Map<string, number>(
  (new URLSearchParams(window.location.search).get("degrees") ?? "")
    .split(",")
    .filter(Boolean)
    .map((pair) => {
      const [id = "", degree = "0"] = pair.split(":");
      return [id, Number(degree)] as [string, number];
    }),
);
const judged = new Map<string, number>(
  (new URLSearchParams(window.location.search).get("judged") ?? "")
    .split(",")
    .filter(Boolean)
    .map((pair) => {
      const [id = "", count = "0"] = pair.split(":");
      return [id, Number(count)] as [string, number];
    }),
);

// ADR-093: the Inspector's selected list, wired to the canvas as App wires it.
function HarnessSelectionList() {
  const [ids, setIds] = useState<string[]>([]);
  useEffect(() => {
    selectionListeners.add(setIds);
    return () => {
      selectionListeners.delete(setIds);
    };
  }, []);
  return (
    <SelectionList
      nodes={ids.filter((id) => workingSet.graph.hasNode(id)).map((id) => workingSet.graph.getNodeAttribute(id, "data"))}
      onCentre={(id) => canvasHandle.current?.centreOn(id)}
      onRemove={(id) => canvasHandle.current?.deselect(id)}
    />
  );
}
const selectionListeners = new Set<(ids: string[]) => void>();

createRoot(container).render(
  <>
    <GlassCanvas
      lastChange={lastChange}
      ref={canvasHandle}
      judgementCounts={judged}
      degreeMarks={degrees}
      graph={workingSet.graph}
      store={workingSet.store}
      ontology={ontology}
      edgeTypes={SCHEMA.edge_types}
      entityTypes={SCHEMA.entity_types}
      investigationId="keyboard-fixture"
      // `?api=same-origin` is the shape the deployed image builds with (`VITE_API_BASE_URL=""`,
      // nginx proxying `/v1`): an empty address meaning this origin, not a missing one.
      apiBaseUrl={sameOrigin ? "" : "http://keyboard-test.invalid"}
      bearerToken="unused"
      onFocusChange={(nodeId) => {
        window.__KEYBOARD__!.focused = nodeId;
      }}
      onSetPicture={(nodeId) => {
        window.__KEYBOARD__!.pictureRequested = nodeId;
      }}
      onSelectionChange={(ids) => {
        window.__KEYBOARD__!.selection = ids;
        for (const listener of selectionListeners) listener(ids);
      }}
      onEdgeSelect={(edge) => {
        window.__KEYBOARD__!.selectedEdge = edge ? edge.id : null;
      }}
      getEventsWindow={() =>
        wantsLit
          ? litStore.store.getState().window
          : wantsEmails
            ? { validFrom: "2001-05-01T00:00:00Z", validTo: "2001-05-31T00:00:00Z" }
            : null
      }
      onOpenDocument={(nodeId) => {
        window.__KEYBOARD__!.openedDocument = nodeId;
      }}
      onLinkAction={(edge, action) => {
        window.__KEYBOARD__!.linkAction = { edgeId: edge.id, action };
      }}
      onViewMessages={(nodeId) => {
        window.__KEYBOARD__!.viewMessagesNodeId = nodeId;
      }}
      onBranchCreated={(id) => {
        window.__KEYBOARD__!.branchedTo = id;
      }}
      onAskAboutDocuments={(id) => {
        window.__KEYBOARD__!.askedIn = id;
      }}
      onGroupedCountChange={(count) => {
        window.__GROUPED__ = count;
      }}
    />
    {/* The Tab-trap fix's own proof needs a real next tab-stop after the canvas — nothing here
        before Phase 7 Stage 4, since the canvas's own onKeyDown used to intercept every Tab
        press regardless. */}
    <button id="after-canvas" data-harness-only="">After canvas</button>
    {wantsLit && (
      <div style={{ width: 900, height: 260 }}>
        <Timeline
          apiBaseUrl="http://keyboard-test.invalid"
          bearerToken="unused"
          investigationScope="keyboard-fixture"
          crossFilterStore={litStore}
          getNodeIds={() => workingSet.graph.nodes()}
          getEdgeIds={() => workingSet.graph.edges()}
          onSelectLit={() => {
            const window = litStore.store.getState().window;
            if (window) void canvasHandle.current?.selectLit(window);
          }}
        />
      </div>
    )}
    <HarnessSelectionList />
  </>,
);
