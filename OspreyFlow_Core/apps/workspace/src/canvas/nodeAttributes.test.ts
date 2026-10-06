import { describe, expect, it } from "vitest";

import { activePalette } from "../color/palette";
import { makeEdge, makeNode } from "../testing/fixtures";
import {
  computeClusterGraphAttributes,
  computeEdgeAttributes,
  computeNodeFrameAttributes,
  computeNodeGraphAttributes,
  edgeProgramFor,
  effectiveBasis,
  type NodeVisualState,
  SMALL_VIEW_LABEL_LIMIT,
} from "./nodeAttributes";

const PERSON_VISUAL = { channel: "indigo", shape: "circle" } as const;

/** `image` is a `data:image/svg+xml` URI — decode before asserting on its
 * markup rather than matching against the percent-encoded form. */
function decodeSvg(dataUri: string): string {
  return decodeURIComponent(dataUri.replace(/^data:image\/svg\+xml;utf8,/, ""));
}

function baseState(overrides: Partial<NodeVisualState> = {}): NodeVisualState {
  return {
    dimmed: false,
    filteredOut: false,
    hovered: false,
    selected: false,
    onPath: false,
    ...overrides,
  };
}

describe("computeNodeGraphAttributes", () => {
  it("an asserted node's fill is the plain channel colour, undimmed", () => {
    const attrs = computeNodeGraphAttributes(
      makeNode("n1"),
      PERSON_VISUAL,
      baseState(),
    );

    expect(attrs.color.toLowerCase()).toBe("#677bd6"); // indigo
    expect(decodeSvg(attrs.image)).not.toContain("stroke-dasharray"); // asserted => solid
  });

  it("colour never changes for interaction state — only the border ring does", () => {
    const asserted = computeNodeGraphAttributes(
      makeNode("n1"),
      PERSON_VISUAL,
      baseState(),
    );
    const selected = computeNodeGraphAttributes(
      makeNode("n1"),
      PERSON_VISUAL,
      baseState({ selected: true }),
    );
    // Colour (entity type) is untouched by interaction state — only the
    // border ring changes (spec/design/tokens.css: hue is entity type
    // only, never a state or metric).
    expect(selected.color).toBe(asserted.color);
    // Selection's ring is a layer of its own (`selectionRing*`), not the interaction ring.
    expect(selected.selectionRingColor).not.toBe(asserted.selectionRingColor);
  });

  it("dimmed mixes 32% channel toward the panel surface", () => {
    const attrs = computeNodeGraphAttributes(
      makeNode("n1"),
      PERSON_VISUAL,
      baseState({ dimmed: true }),
    );
    expect(attrs.color.toLowerCase()).not.toBe("#677bd6");
  });

  it("filtered-out and dimmed produce different fills (12% vs 32%)", () => {
    const dimmed = computeNodeGraphAttributes(
      makeNode("n1"),
      PERSON_VISUAL,
      baseState({ dimmed: true }),
    );
    const filteredOut = computeNodeGraphAttributes(
      makeNode("n1"),
      PERSON_VISUAL,
      baseState({ filteredOut: true }),
    );
    expect(dimmed.color).not.toBe(filteredOut.color);
  });

  it("inferred provenance renders a dashed stroke", () => {
    const node = makeNode("n1", {
      provenance: {
        state: "inferred",
        sources: [],
        first_seen: "2026-01-01T00:00:00Z",
      },
    });
    const attrs = computeNodeGraphAttributes(node, PERSON_VISUAL, baseState());
    expect(decodeSvg(attrs.image)).toContain('stroke-dasharray="4 2"');
  });

  it("unresolved provenance renders a dotted stroke, distinct from dashed", () => {
    const node = makeNode("n1", {
      provenance: {
        state: "unresolved",
        sources: [],
        first_seen: "2026-01-01T00:00:00Z",
      },
    });
    const attrs = computeNodeGraphAttributes(node, PERSON_VISUAL, baseState());
    expect(decodeSvg(attrs.image)).not.toContain('stroke-dasharray="4 2"');
    expect(decodeSvg(attrs.image)).toContain("stroke-dasharray");
  });

  // The owner, 4 October 2026: "the nodes do not get highlighted when I select them". The brass
  // ring was 2 pixels drawn inside a node a few pixels wide, so it was not seen. A selected node now
  // has a ring and a dark gap of its own, sized by the node's radius, and is drawn larger.
  it("a selected node has a brass ring and a dark gap, sized by its radius; others have none", () => {
    const selected = computeNodeGraphAttributes(makeNode("n1"), PERSON_VISUAL, baseState({ selected: true }));
    expect(selected.selectionRingColor).toBe(activePalette().brass);
    expect(selected.selectionRingSize).toBeGreaterThanOrEqual(0.2);
    expect(selected.selectionGapColor).toBe(activePalette().surfaceApp);
    expect(selected.selectionGapSize).toBeGreaterThan(0);
    expect(selected.selected).toBe(true);
    expect(selected.emphasised).toBe(true);

    const plain = computeNodeGraphAttributes(makeNode("n1"), PERSON_VISUAL, baseState());
    expect(plain.selectionRingSize).toBe(0);
    expect(plain.selectionGapSize).toBe(0);
    expect(plain.selected).toBe(false);
  });

  it("on-path takes priority over selected, which takes priority over hover", () => {
    const onPath = computeNodeGraphAttributes(
      makeNode("n1"),
      PERSON_VISUAL,
      baseState({ onPath: true, selected: true, hovered: true }),
    );
    expect(onPath.borderSize).toBe(2);

    // Selection has rings of its own now (below); the interaction ring is hover's.
    const selected = computeNodeGraphAttributes(
      makeNode("n1"),
      PERSON_VISUAL,
      baseState({ selected: true, hovered: true }),
    );
    expect(selected.borderSize).toBe(1.5);

    const hovered = computeNodeGraphAttributes(
      makeNode("n1"),
      PERSON_VISUAL,
      baseState({ hovered: true }),
    );
    expect(hovered.borderSize).toBe(1.5);

    const none = computeNodeGraphAttributes(
      makeNode("n1"),
      PERSON_VISUAL,
      baseState(),
    );
    expect(none.borderSize).toBe(0);
  });
});

describe("computeNodeFrameAttributes", () => {
  it("label is only eligible above the overview band", () => {
    const overview = computeNodeFrameAttributes(makeNode("n1"), {
      cameraRatio: 5,
      degree: 0,
    });
    expect(overview.label).toBe("");

    const linkDetail = computeNodeFrameAttributes(
      makeNode("n1", { properties: { family_name: "Smith" } }),
      { cameraRatio: 0.05, degree: 0 },
    );
    expect(linkDetail.label).toBe("Smith");
  });

  it("structure band shows labels only above the degree threshold", () => {
    const lowDegree = computeNodeFrameAttributes(
      makeNode("n1", { properties: { family_name: "Smith" } }),
      { cameraRatio: 1, degree: 2 },
    );
    expect(lowDegree.label).toBe("");

    const highDegree = computeNodeFrameAttributes(
      makeNode("n1", { properties: { family_name: "Smith" } }),
      { cameraRatio: 1, degree: 20 },
    );
    expect(highDegree.label).toBe("Smith");
  });

  it("node is never hidden by zoom, only shrunk (nodes always exist)", () => {
    for (const cameraRatio of [0.05, 0.3, 1, 5]) {
      const attrs = computeNodeFrameAttributes(makeNode("n1"), {
        cameraRatio,
        degree: 0,
      });
      expect(attrs.hidden).toBe(false);
    }
  });

  it("node size grows from overview to link-detail", () => {
    const overview = computeNodeFrameAttributes(makeNode("n1"), {
      cameraRatio: 5,
      degree: 0,
    });
    const linkDetail = computeNodeFrameAttributes(makeNode("n1"), {
      cameraRatio: 0.05,
      degree: 0,
    });
    expect(linkDetail.size).toBeGreaterThan(overview.size);
  });
});

describe("node size at 100% (ADR-097 step 2, design review item 9)", () => {
  it("is 20px across (a radius of 10) at a camera ratio of 1 in an uncrowded view", () => {
    const frame = computeNodeFrameAttributes(makeNode("n1"), { cameraRatio: 1, degree: 1, viewNodeCount: 20 });
    expect(frame.size).toBe(10);
  });
});

describe("computeEdgeAttributes", () => {
  it("hides only edges below the strength filter, only at the overview band", () => {
    const weak = makeEdge("e1", "a", "b", { weight: 0.1 });
    const overview = computeEdgeAttributes(weak, {
      cameraRatio: 5,
      strengthFilterFloor: 0.5,
      onPath: false,
    });
    expect(overview.hidden).toBe(true);

    const structure = computeEdgeAttributes(weak, {
      cameraRatio: 1,
      strengthFilterFloor: 0.5,
      onPath: false,
    });
    expect(structure.hidden).toBe(false); // "All edges, width by weight" at Structure
  });

  it("edge labels are only eligible at link-detail", () => {
    const edge = makeEdge("e1", "a", "b");
    expect(
      computeEdgeAttributes(edge, {
        cameraRatio: 1,
        strengthFilterFloor: 0,
        onPath: false,
      }).label,
    ).toBe("");
    expect(
      computeEdgeAttributes(edge, {
        cameraRatio: 0.05,
        strengthFilterFloor: 0,
        onPath: false,
      }).label,
    ).not.toBe("");
  });

  it("on-path overrides the strength filter — a found path is never hidden by an unrelated filter", () => {
    const weak = makeEdge("e1", "a", "b", { weight: 0.01 });
    const onPath = computeEdgeAttributes(weak, {
      cameraRatio: 5,
      strengthFilterFloor: 0.5,
      onPath: true,
    });
    expect(onPath.hidden).toBe(false);
    expect(onPath.size).toBeGreaterThan(4); // thickened past the ordinary weight-based ceiling
  });
});

describe("computeClusterGraphAttributes", () => {
  it("a singleton cluster gets no ring at all", () => {
    expect(computeClusterGraphAttributes(1)).toEqual({
      clusterBorderColor: "transparent",
      clusterBorderSize: 0,
    });
  });

  it("a cluster of more than one member gets a quiet, non-interaction ring", () => {
    const attrs = computeClusterGraphAttributes(3);
    expect(attrs.clusterBorderSize).toBeGreaterThan(0);
    expect(attrs.clusterBorderColor).not.toBe("transparent");
    expect(attrs.clusterBorderColor.toLowerCase()).not.toBe("#c08a34"); // never the selection brass
  });
});

describe("edge labels beside a hovered node", () => {
  const edge = makeEdge("e1", "a", "b");
  const base = { strengthFilterFloor: 0, onPath: false };

  it("are shown for an edge touching the hovered node, at any zoom", () => {
    for (const cameraRatio of [0.05, 1, 5]) {
      const attrs = computeEdgeAttributes(edge, {
        ...base,
        cameraRatio,
        touchesHoveredNode: true,
      });
      expect(attrs.label).not.toBe("");
    }
  });

  it("stay hidden for an edge that does not touch it, at ordinary zoom", () => {
    expect(
      computeEdgeAttributes(edge, {
        ...base,
        cameraRatio: 1,
        touchesHoveredNode: false,
      }).label,
    ).toBe("");
  });

  it("do not bring back an edge the strength filter hid", () => {
    const weak = makeEdge("e2", "a", "b", { weight: 0.1 });
    const attrs = computeEdgeAttributes(weak, {
      cameraRatio: 5,
      strengthFilterFloor: 0.5,
      onPath: false,
      touchesHoveredNode: true,
    });
    expect(attrs.hidden).toBe(true);
  });
});

describe("edgeProgramFor", () => {
  const types = [
    { name: "TRANSACTED", directed: true },
    { name: "SAME_AS", directed: false },
  ];

  it("draws an arrowhead only for an edge type the ontology declares directed", () => {
    expect(edgeProgramFor("TRANSACTED", types)).toBe("glass-arrow");
    expect(edgeProgramFor("SAME_AS", types)).toBe("glass-edge");
  });

  it("claims no direction for an edge type the ontology does not know", () => {
    expect(edgeProgramFor("MYSTERY", types)).toBe("glass-edge");
  });
});

// ADR-081: the line style follows the type's basis and is never authored. A Direct link is solid, a
// Probabilistic one is dotted, whatever colour or thickness its type declares.
describe("edgeProgramFor and the basis of a type (ADR-081)", () => {
  const types = [
    { name: "OWNS", directed: true, basis: "direct" as const },
    { name: "KNOWS", directed: false, basis: "direct" as const },
    { name: "LIKELY_OWNS", directed: true, basis: "probabilistic" as const },
    { name: "SAME_AS", directed: false, basis: "probabilistic" as const },
    { name: "NOT_SAME_AS", directed: false, basis: null },
    { name: "THICK", directed: false, basis: "direct" as const, thickness: 3 },
    { name: "THICK_DOTTED", directed: false, basis: "probabilistic" as const, thickness: 3, colour: "jade" },
  ];

  it("draws a probabilistic type dotted, with an arrowhead only where it is directed", () => {
    expect(edgeProgramFor("SAME_AS", types)).toBe("glass-edge-dotted");
    expect(edgeProgramFor("LIKELY_OWNS", types)).toBe("glass-arrow-dotted");
  });

  it("draws a direct type solid, never dotted", () => {
    expect(edgeProgramFor("OWNS", types)).toBe("glass-arrow");
    expect(edgeProgramFor("KNOWS", types)).toBe("glass-edge");
  });

  it("draws a type with no basis (NOT_SAME_AS) as it always was", () => {
    expect(edgeProgramFor("NOT_SAME_AS", types)).toBe("glass-edge");
  });

  it("uses a program that honours width for a solid type that declares a thickness", () => {
    expect(edgeProgramFor("THICK", types)).toBe("glass-edge-thick");
  });

  it("is dotted whatever colour and thickness a probabilistic type declares", () => {
    expect(edgeProgramFor("THICK_DOTTED", types)).toBe("glass-edge-dotted");
  });
});

// ADR-081 step B: a link may carry a basis of its own. A link of a Direct type marked probabilistic
// is drawn dotted; a link of a Probabilistic type is dotted whatever is stored on it.
describe("edgeProgramFor and the link's own basis (ADR-081 step B)", () => {
  const types = [
    { name: "OWNS", directed: true, basis: "direct" as const },
    { name: "KNOWS", directed: false, basis: "direct" as const, thickness: 3 },
    { name: "SAME_AS", directed: false, basis: "probabilistic" as const },
    { name: "NOT_SAME_AS", directed: false, basis: null },
  ];

  it("draws a link of a Direct type dotted when the link itself is marked probabilistic", () => {
    expect(edgeProgramFor("OWNS", types, "probabilistic")).toBe("glass-arrow-dotted");
    expect(edgeProgramFor("KNOWS", types, "probabilistic")).toBe("glass-edge-dotted");
  });

  it("draws a link of a Direct type solid when it carries no mark or says direct", () => {
    expect(edgeProgramFor("OWNS", types, null)).toBe("glass-arrow");
    expect(edgeProgramFor("OWNS", types, undefined)).toBe("glass-arrow");
    expect(edgeProgramFor("KNOWS", types, "direct")).toBe("glass-edge-thick");
  });

  it("never lets a stored mark make a Probabilistic type solid", () => {
    expect(edgeProgramFor("SAME_AS", types, "direct")).toBe("glass-edge-dotted");
  });

  it("reads what stands behind a link from the link and its type together", () => {
    expect(effectiveBasis(undefined, types[0])).toBe("direct");
    expect(effectiveBasis("probabilistic", types[0])).toBe("probabilistic");
    expect(effectiveBasis("direct", types[2])).toBe("probabilistic");
    expect(effectiveBasis(undefined, types[3])).toBeNull();
    expect(effectiveBasis(undefined, undefined)).toBeNull();
  });
});

// ADR-087: a link with no event in the brush window, or not yet reached by the playhead, is dimmed
// as a node is: its colour mixed towards the panel surface and its label dropped.
describe("computeEdgeAttributes and a dimmed link (ADR-087)", () => {
  const edge = makeEdge("e1", "a", "b", { weight: 1, occurrences: 4 });
  const context = { cameraRatio: 0.3, strengthFilterFloor: 0, onPath: false };

  it("mixes a dimmed link's colour towards the panel and drops its label", () => {
    const plain = computeEdgeAttributes(edge, context);
    const dimmed = computeEdgeAttributes(edge, { ...context, dimmed: true });
    expect(dimmed.color).not.toBe(plain.color);
    expect(dimmed.label).toBe("");
    expect(dimmed.hidden).toBe(false); // dimmed, never removed (spec 02 §2 rule 2)
    expect(dimmed.size).toBe(plain.size);
  });

  it("lets a found path win over dimming", () => {
    const onPath = computeEdgeAttributes(edge, { ...context, dimmed: true, onPath: true });
    const plainPath = computeEdgeAttributes(edge, { ...context, onPath: true });
    expect(onPath.color).toBe(plainPath.color);
  });
});

// ADR-091: a link reads by its type's name in sentence case and a named count, never in capitals
// with a bare number ("COMMUNICATED_WITH (3)", which the owner found strange).
describe("computeEdgeAttributes and the link's caption (ADR-091)", () => {
  const edge = makeEdge("e1", "a", "b", { type: "COMMUNICATED_WITH", weight: 1, occurrences: 3 });
  // Link-detail zoom, where every link is labelled.
  const context = { cameraRatio: 0.1, strengthFilterFloor: 0, onPath: false };

  it("derives the caption from the type when none is given, in every labelled state", () => {
    const states = [
      computeEdgeAttributes(edge, context),
      computeEdgeAttributes(edge, { ...context, onPath: true }),
      computeEdgeAttributes(edge, { ...context, cameraRatio: 5, touchesHoveredNode: true }),
    ];
    for (const state of states) expect(state.label).toBe("Communicated with · 3 records");
  });

  it("uses the caption it is given, and builds none for a link it does not label", () => {
    const caption = "Emailed · 3 emails";
    expect(computeEdgeAttributes(edge, { ...context, caption: () => caption }).label).toBe(caption);
    let built = 0;
    const counting = () => {
      built += 1;
      return caption;
    };
    computeEdgeAttributes(edge, { ...context, cameraRatio: 5, caption: counting });
    expect(built).toBe(0);
  });
});

// ADR-081, Amendment 1: a declared colour is one of the nine channel names; a declared thickness is
// the base width and the link's weight scales it, between half and one and a half times.
describe("computeEdgeAttributes with a declaration (ADR-081)", () => {
  const ctx = { cameraRatio: 1, strengthFilterFloor: 0, onPath: false };

  it("keeps today's colour and weight-based width when the type declares nothing", () => {
    const edge = makeEdge("e1", "a", "b", { weight: 1 });
    const plain = computeEdgeAttributes(edge, ctx);
    const none = computeEdgeAttributes(edge, { ...ctx, declared: {} });
    expect(none).toEqual(plain);
  });

  it("draws in the declared channel colour", () => {
    const edge = makeEdge("e1", "a", "b");
    const drawn = computeEdgeAttributes(edge, { ...ctx, declared: { colour: "jade" } });
    expect(drawn.color.toLowerCase()).toBe("#72b99a");
    expect(drawn.color).not.toBe(computeEdgeAttributes(edge, ctx).color);
  });

  it("falls back to the ordinary colour for a name that is not a channel", () => {
    const edge = makeEdge("e1", "a", "b");
    const drawn = computeEdgeAttributes(edge, { ...ctx, declared: { colour: "chartreuse" } });
    expect(drawn.color).toBe(computeEdgeAttributes(edge, ctx).color);
  });

  it("draws the declared thickness at the default weight", () => {
    for (const thickness of [1, 2, 3, 4, 5]) {
      const edge = makeEdge("e1", "a", "b", { weight: 1 });
      expect(computeEdgeAttributes(edge, { ...ctx, declared: { thickness } }).size).toBe(thickness);
    }
  });

  it("lets the weight scale the declared thickness, between half and one and a half times", () => {
    const at = (weight: number) =>
      computeEdgeAttributes(makeEdge("e1", "a", "b", { weight }), {
        ...ctx,
        declared: { thickness: 3 },
      }).size;
    expect(at(0.5)).toBe(1.5);
    expect(at(1.5)).toBe(4.5);
    expect(at(1.5)).toBeGreaterThan(at(0.5));
    expect(at(0.01)).toBe(1.5); // held at half
    expect(at(9)).toBe(4.5); // held at one and a half times
  });

  it("still scales a declared thickness down in a crowded view", () => {
    const edge = makeEdge("e1", "a", "b", { weight: 1 });
    const open = computeEdgeAttributes(edge, { ...ctx, declared: { thickness: 5 } });
    const crowded = computeEdgeAttributes(edge, { ...ctx, viewEdgeCount: 100000, declared: { thickness: 5 } });
    expect(crowded.size).toBeLessThan(open.size);
  });

  it("a found path is still thickened and still the ordinary colour, whatever is declared", () => {
    const edge = makeEdge("e1", "a", "b");
    const onPath = computeEdgeAttributes(edge, {
      ...ctx,
      onPath: true,
      declared: { colour: "jade", thickness: 1 },
    });
    expect(onPath.size).toBeGreaterThan(4);
    expect(onPath.color).not.toBe("#72b99a");
  });
});

// Seen 3 October 2026 in the running Glass, on the Enron case: two addresses found by search were
// drawn as two unlabelled squares, and the node menu did not say whose it was, so the analyst could
// not tell which node was which. The zoom rule labelled a node only above a degree of 10 (or when
// zoomed right in), which is right for a thousand nodes and wrong for two.
describe("telling nodes apart", () => {
  const address = makeNode("n1", { properties: { value_normalised: "someone@example.test" } });

  it("a small view labels every node whatever the zoom, even one with no links", () => {
    const attrs = computeNodeFrameAttributes(address, {
      cameraRatio: 5,
      degree: 0,
      viewNodeCount: 2,
    });
    expect(attrs.label).toBe("someone@example.test");
  });

  it("a view at the limit is still labelled, and one node over it falls back to the zoom rule", () => {
    const at = computeNodeFrameAttributes(address, {
      cameraRatio: 1,
      degree: 0,
      viewNodeCount: SMALL_VIEW_LABEL_LIMIT,
    });
    expect(at.label).toBe("someone@example.test");
    const over = computeNodeFrameAttributes(address, {
      cameraRatio: 1,
      degree: 0,
      viewNodeCount: SMALL_VIEW_LABEL_LIMIT + 1,
    });
    expect(over.label).toBe("");
  });

  it("a node that is selected, hovered or on a path is labelled even in a crowded view", () => {
    const attrs = computeNodeFrameAttributes(address, {
      cameraRatio: 5,
      degree: 0,
      viewNodeCount: 5000,
      emphasised: true,
    });
    expect(attrs.label).toBe("someone@example.test");
  });

  it("the graph attributes say which nodes are emphasised", () => {
    const node = makeNode("n1");
    const emphasised = (state: Partial<NodeVisualState>) =>
      computeNodeGraphAttributes(node, PERSON_VISUAL, baseState(state)).emphasised;
    expect(emphasised({ selected: true })).toBe(true);
    expect(emphasised({ hovered: true })).toBe(true);
    expect(emphasised({ onPath: true })).toBe(true);
    expect(emphasised({})).toBe(false);
  });
});
