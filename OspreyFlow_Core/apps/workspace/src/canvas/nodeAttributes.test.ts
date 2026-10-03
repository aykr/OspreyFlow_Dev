import { describe, expect, it } from "vitest";

import { makeEdge, makeNode } from "../testing/fixtures";
import {
  computeClusterGraphAttributes,
  computeEdgeAttributes,
  computeNodeFrameAttributes,
  computeNodeGraphAttributes,
  edgeProgramFor,
  type NodeVisualState,
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
    expect(selected.borderColor).not.toBe(asserted.borderColor);
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

  it("on-path takes priority over selected, which takes priority over hover", () => {
    const onPath = computeNodeGraphAttributes(
      makeNode("n1"),
      PERSON_VISUAL,
      baseState({ onPath: true, selected: true, hovered: true }),
    );
    expect(onPath.borderSize).toBe(2);

    const selected = computeNodeGraphAttributes(
      makeNode("n1"),
      PERSON_VISUAL,
      baseState({ selected: true, hovered: true }),
    );
    expect(selected.borderSize).toBe(2);

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
