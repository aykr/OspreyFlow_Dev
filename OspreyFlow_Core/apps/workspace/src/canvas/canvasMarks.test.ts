// @vitest-environment jsdom
// The canvas's own marks (`canvasMarks.ts`, WS4a), without a browser: what the budget gate, the comparison and the
// specs wait for and find the layers by. The renderer here is only what the marks read of Sigma 3's: its canvases
// under the ids its constructor and the community links' layer give them, and its events, on Node's `EventEmitter`,
// which Sigma's own emitter extends.
import { EventEmitter } from "node:events";

import type Sigma from "sigma";
import { describe, expect, it } from "vitest";

import { CANVAS_LAYER, CANVAS_STATE, markRenderer } from "./canvasMarks";

const SIGMA_3_LAYERS = ["edges", "edgeLabels", "nodes", "labels", "hovers", "hoverNodes", "mouse", "communityLinks"];

class Renderer extends EventEmitter {
  readonly canvases = Object.fromEntries(SIGMA_3_LAYERS.map((id) => [id, document.createElement("canvas")]));

  getCanvases() {
    return this.canvases;
  }
}

function mounted() {
  const element = document.createElement("div");
  const renderer = new Renderer();
  const takeDown = markRenderer(element, renderer as unknown as Sigma);
  return { element, renderer, takeDown, state: () => element.getAttribute(CANVAS_STATE) };
}

describe("the canvas's marks", () => {
  it("names every layer the renderer draws on", () => {
    const { renderer } = mounted();
    expect(Object.values(renderer.canvases).map((canvas) => canvas.getAttribute(CANVAS_LAYER))).toEqual([
      "links",
      "link-labels",
      "nodes",
      "labels",
      "hovers",
      "hover-nodes",
      "pointer",
      "community-links",
    ]);
  });

  it("says mounted at once, and drawn only once the renderer has finished a frame", () => {
    const { renderer, state } = mounted();
    expect(state()).toBe("mounted");
    renderer.emit("beforeRender");
    expect(state()).toBe("mounted");
    renderer.emit("afterRender");
    expect(state()).toBe("drawn");
    expect(renderer.listenerCount("afterRender"), "it stops listening after the first").toBe(0);
  });

  it("takes the state off when the renderer is taken down", () => {
    const { element, renderer, takeDown } = mounted();
    renderer.emit("afterRender");
    takeDown();
    expect(element.hasAttribute(CANVAS_STATE)).toBe(false);
  });

  it("stays unmarked when a renderer taken down before its frame finishes one afterwards", () => {
    const { element, renderer, takeDown } = mounted();
    takeDown();
    expect(element.hasAttribute(CANVAS_STATE)).toBe(false);
    expect(renderer.listenerCount("afterRender")).toBe(0);
    renderer.emit("afterRender");
    expect(element.hasAttribute(CANVAS_STATE)).toBe(false);
  });
});
